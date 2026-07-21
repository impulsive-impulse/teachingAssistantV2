"""FastAPI application factory and local development entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api.routes import books, chats, system
from .config import AppSettings, validate_frozen_configs
from .database import Database
from .models.embedding import EmbeddingArtifactRegistry
from .models.offline import OfflineArtifactRegistry
from .generation.offline import OfflineRuntimeManager
from .repositories import BookRepository, ChatRepository, ModelSetupRepository
from .retrieval.registry import RetrievalRuntimeRegistry
from .services.chat import ChatCoordinator, GenerationProviderRegistry
from .services.ingestion import IngestionCoordinator
from .services.model_setup import ModelSetupCoordinator


def create_app(settings: AppSettings | None = None, *, run_workers: bool = True) -> FastAPI:
    """Build an isolated app instance, which also makes integration tests cheap."""

    configured = settings or AppSettings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configured.ensure_directories()
        validate_frozen_configs(configured)
        database = Database(configured.database_path)
        database.initialize()
        ingestion = IngestionCoordinator(configured, BookRepository(database))
        embedding_registry = EmbeddingArtifactRegistry(configured)
        offline_registry = OfflineArtifactRegistry(configured)
        offline_runtime = OfflineRuntimeManager(configured, offline_registry)
        retrieval_registry = RetrievalRuntimeRegistry(configured, embedding_registry)
        generation_providers = GenerationProviderRegistry(configured.root, offline_runtime)
        chat_coordinator = ChatCoordinator(
            ChatRepository(database), retrieval_registry.for_book, generation_providers.resolve
        )
        model_setup = ModelSetupCoordinator(
            ModelSetupRepository(database), embedding_registry, ingestion, offline_registry
        )
        app.state.settings = configured
        app.state.database = database
        app.state.ingestion = ingestion
        app.state.embedding_registry = embedding_registry
        app.state.offline_registry = offline_registry
        app.state.offline_runtime = offline_runtime
        app.state.retrieval_registry = retrieval_registry
        app.state.generation_providers = generation_providers
        app.state.chat_coordinator = chat_coordinator
        app.state.model_setup = model_setup
        app.state.run_workers = run_workers
        if run_workers:
            ingestion.start()
            model_setup.start()
            chat_coordinator.start()
        try:
            yield
        finally:
            chat_coordinator.shutdown()
            offline_runtime.shutdown()
            model_setup.shutdown()
            ingestion.shutdown()

    app = FastAPI(
        title="Local Textbook Chat API",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.include_router(system.router, prefix="/api")
    app.include_router(books.router, prefix="/api")
    app.include_router(chats.router, prefix="/api")

    frontend = configured.root / "frontend" / "dist"
    if frontend.is_dir():
        assets = frontend / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

        @app.get("/{path:path}", include_in_schema=False)
        def react_application(path: str) -> FileResponse:
            """Use the SPA shell for client-side routes after API routes are matched."""

            candidate = (frontend / path).resolve()
            if candidate.is_file() and frontend.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(frontend / "index.html")

    return app


def run() -> None:
    """Run the loopback-only API entry point installed by the app extra."""

    settings = AppSettings.load()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


app = create_app()
