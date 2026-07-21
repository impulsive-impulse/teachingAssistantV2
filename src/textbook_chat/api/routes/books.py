"""Persistent library and upload endpoints."""

import asyncio
import json

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from ...config import AppSettings
from ...repositories import BookRepository
from ...schemas import BookResponse, IngestionJobResponse, UploadResponse
from ...services.uploads import UploadRejected, UploadService
from ...services.ingestion import IngestionCoordinator
from ...services.deletion import BookDeletionService
from ..dependencies import book_deletion, books, ingestion_coordinator, settings, upload_service


router = APIRouter(tags=["library"])


@router.get("/books", response_model=list[BookResponse])
def list_books(repository: BookRepository = Depends(books)) -> list[dict]:
    return repository.list_books()


@router.get("/books/{book_uuid}", response_model=BookResponse)
def get_book(book_uuid: str, repository: BookRepository = Depends(books)) -> dict:
    book = repository.get(book_uuid)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found.")
    return book


@router.get("/books/{book_uuid}/source")
def get_book_source(
    book_uuid: str,
    repository: BookRepository = Depends(books),
    app_settings: AppSettings = Depends(settings),
) -> FileResponse:
    book = repository.get(book_uuid)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found.")
    if not book.get("source_path"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Book source is not available.")
    source = (app_settings.data_dir / book["source_path"]).resolve()
    if app_settings.data_dir.resolve() not in source.parents or not source.is_file():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Book source failed its local path check.")
    return FileResponse(source, media_type="application/pdf", filename=book["original_filename"])


@router.delete("/books/{book_uuid}")
def delete_book(
    book_uuid: str, service: BookDeletionService = Depends(book_deletion)
) -> dict:
    try:
        return service.delete(book_uuid)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/books/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_book(
    request: Request,
    upload: UploadFile = File(...),
    service: UploadService = Depends(upload_service),
    coordinator: IngestionCoordinator = Depends(ingestion_coordinator),
) -> UploadResponse:
    try:
        result = await service.accept(upload)
    except UploadRejected as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    if result.disposition == "created" and result.job and request.app.state.run_workers:
        coordinator.submit(result.job["id"])
    return UploadResponse(disposition=result.disposition, book=result.book, job=result.job)


@router.get("/ingestion/{job_uuid}", response_model=IngestionJobResponse)
def get_ingestion_job(job_uuid: str, repository: BookRepository = Depends(books)) -> dict:
    job = repository.get_job(job_uuid)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found.")
    return job


@router.get("/ingestion/{job_uuid}/events")
async def ingestion_events(
    job_uuid: str, repository: BookRepository = Depends(books)
) -> StreamingResponse:
    """Stream durable job snapshots; reconnecting clients can always use GET."""

    if not repository.get_job(job_uuid):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion job not found.")

    async def stream():
        previous = None
        while True:
            job = repository.get_job(job_uuid)
            if not job:
                yield "event: failed\ndata: {\"detail\":\"Ingestion job no longer exists.\"}\n\n"
                return
            public = IngestionJobResponse.model_validate(job).model_dump(mode="json")
            encoded = json.dumps(public, separators=(",", ":"))
            if encoded != previous:
                yield f"event: progress\ndata: {encoded}\n\n"
                previous = encoded
            if job["state"] in {"completed", "failed", "cancelled", "waiting"}:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
