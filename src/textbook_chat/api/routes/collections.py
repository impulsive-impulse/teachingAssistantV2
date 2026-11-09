"""Collection management, independent questions and exact original-source navigation."""

from pathlib import Path
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from textbook_audit.assessment_assets import FileIdentity, child_path, verify_file
from textbook_audit.assessment_ingestion import import_pdf_source
from ...domain import Backend
from ...repositories import BookRepository, CollectionQueryRepository, CollectionRepository
from ...services.collections import public_query


router = APIRouter(tags=["collections"])


class CollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    document_ids: list[str] = Field(min_length=1, max_length=100)


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    backend: Backend = Backend.OFFLINE
    online_disclosure_acknowledged: bool = False


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_indexing_authorized: bool = False


def repository(request: Request) -> CollectionRepository:
    return CollectionRepository(request.app.state.database)


@router.get("/sources")
def sources(request: Request) -> list[dict]:
    return repository(request).list_documents()


@router.post("/sources/from-book/{book_id}", status_code=201)
def from_book(book_id: str, payload: ImportRequest, request: Request) -> dict:
    book = BookRepository(request.app.state.database).get(book_id)
    if not book or book["status"] != "ready":
        raise HTTPException(409, "Select a ready library textbook.")
    if not payload.local_indexing_authorized:
        raise HTTPException(409, "Local PDF indexing permission is required.")
    store, settings = repository(request), request.app.state.settings
    identity = "pdf:" + book["sha256"]
    existing = next((item for item in store.list_documents() if item["id"] == identity), None)
    if existing is not None:
        return existing
    source = child_path(settings.data_dir, book["source_path"])
    verify_file(source, FileIdentity(source.stat().st_size, book["sha256"]))
    document = import_pdf_source(
        settings.data_dir, request.app.state.database, source, authorized=True,
        title=Path(book["original_filename"]).stem,
    )
    return next(item for item in store.list_documents() if item["id"] == document.document_id)


@router.get("/sources/{document_id}/file")
def source_file(document_id: str, request: Request) -> FileResponse:
    store = repository(request)
    try:
        document = store.document(document_id)
    except LookupError as error:
        raise HTTPException(404, "Source not found.") from error
    if document.kind != "pdf":
        raise HTTPException(409, "This source has original sentence units, not a PDF file.")
    with store.database.connect() as connection:
        row = connection.execute("SELECT artifact_path FROM source_documents WHERE id=?", (document_id,)).fetchone()
    try:
        path = child_path(request.app.state.settings.data_dir, row["artifact_path"])
        verify_file(path, FileIdentity(path.stat().st_size, document.source_sha256))
    except (OSError, ValueError) as error:
        raise HTTPException(409, "Original PDF is missing or its verified identity changed.") from error
    return FileResponse(path, media_type="application/pdf")


@router.get("/sources/{document_id}/units/{unit_id}")
def source_unit(document_id: str, unit_id: str, request: Request) -> dict:
    try:
        document = repository(request).document(document_id)
        unit = document.unit(unit_id)
    except (LookupError, ValueError) as error:
        raise HTTPException(404, "Source unit not found.") from error
    return {"document_id": document_id, "document_title": document.title, "unit": asdict(unit)}


@router.get("/collections")
def collections(request: Request) -> list[dict]:
    return repository(request).list()


@router.post("/collections", status_code=201)
def create_collection(payload: CollectionRequest, request: Request) -> dict:
    try:
        return repository(request).create(payload.title, payload.document_ids)
    except (LookupError, ValueError) as error:
        raise HTTPException(422, str(error)) from error


@router.get("/collections/{collection_id}/queries")
def queries(collection_id: str, request: Request) -> list[dict]:
    if repository(request).get(collection_id) is None:
        raise HTTPException(404, "Collection not found.")
    return [public_query(row) for row in CollectionQueryRepository(request.app.state.database).list_public(collection_id)]


@router.post("/collections/{collection_id}/queries", status_code=201)
def ask(collection_id: str, payload: QueryRequest, request: Request) -> dict:
    try:
        return request.app.state.collection_service.ask(
            collection_id, payload.question, payload.backend,
            acknowledged=payload.online_disclosure_acknowledged,
        )
    except LookupError as error:
        raise HTTPException(404, "Collection not found.") from error
    except (PermissionError, RuntimeError, ValueError) as error:
        raise HTTPException(409, str(error)) from error


@router.get("/collection-queries/{query_id}/diagnostics")
def query_diagnostics(query_id: str, request: Request) -> dict:
    try:
        return CollectionQueryRepository(request.app.state.database).get(query_id)
    except LookupError as error:
        raise HTTPException(404, "Collection query not found.") from error


@router.post("/collection-queries/{query_id}/replay", status_code=201)
def replay_query(query_id: str, request: Request) -> dict:
    try:
        return request.app.state.collection_service.replay_pdf_query(query_id)
    except LookupError as error:
        raise HTTPException(404, "Collection query not found.") from error
    except (RuntimeError, ValueError) as error:
        raise HTTPException(409, str(error)) from error
