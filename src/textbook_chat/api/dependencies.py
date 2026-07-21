"""FastAPI dependency accessors backed by application state."""

from __future__ import annotations

from fastapi import Request

from ..config import AppSettings
from ..database import Database
from ..repositories import BookRepository, ChatRepository, ModelSetupRepository
from ..models.embedding import EmbeddingArtifactRegistry
from ..services.system import SystemStatusService
from ..services.ingestion import IngestionCoordinator
from ..services.uploads import UploadService
from ..services.deletion import BookDeletionService


def settings(request: Request) -> AppSettings:
    return request.app.state.settings


def database(request: Request) -> Database:
    return request.app.state.database


def books(request: Request) -> BookRepository:
    return BookRepository(database(request))


def chats(request: Request) -> ChatRepository:
    return ChatRepository(database(request))


def system_service(request: Request) -> SystemStatusService:
    return SystemStatusService(
        settings(request), database(request), request.app.state.embedding_registry,
        request.app.state.offline_registry,
    )


def upload_service(request: Request) -> UploadService:
    return UploadService(settings(request), books(request))


def ingestion_coordinator(request: Request) -> IngestionCoordinator:
    return request.app.state.ingestion


def model_setups(request: Request) -> ModelSetupRepository:
    return ModelSetupRepository(database(request))


def model_setup_coordinator(request: Request):
    return request.app.state.model_setup


def chat_coordinator(request: Request):
    return request.app.state.chat_coordinator


def offline_runtime(request: Request):
    return request.app.state.offline_runtime


def book_deletion(request: Request) -> BookDeletionService:
    return BookDeletionService(
        settings(request), books(request), request.app.state.retrieval_registry.evict
    )
