"""Book-scoped chats, independent questions, attempts, and live events."""

import json

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse

from ...domain import Backend, BookStatus
from ...generation.prompt import build_prompt
from ...repositories import BookRepository, ChatRepository
from ...schemas import (
    AttemptResponse,
    ChatCreateRequest,
    ChatResponse,
    ChatUpdateRequest,
    MessageAcceptedResponse,
    MessageCreateRequest,
    RegenerateRequest,
)
from ...services.chat import ChatCoordinator
from ..dependencies import books, chat_coordinator, chats


router = APIRouter(tags=["chats"])


@router.get("/books/{book_uuid}/chats", response_model=list[ChatResponse])
def list_chats(book_uuid: str, repository: ChatRepository = Depends(chats)) -> list[dict]:
    return repository.list_for_book(book_uuid)


@router.post(
    "/books/{book_uuid}/chats", response_model=ChatResponse, status_code=status.HTTP_201_CREATED
)
def create_chat(
    book_uuid: str,
    payload: ChatCreateRequest,
    book_repository: BookRepository = Depends(books),
    chat_repository: ChatRepository = Depends(chats),
) -> dict:
    book = book_repository.get(book_uuid)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found.")
    if book["status"] != BookStatus.READY.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chat becomes available only after this book finishes indexing.",
        )
    return chat_repository.create(book_uuid, payload.title.strip(), payload.default_backend)


@router.get("/chats/{chat_uuid}")
def get_chat(chat_uuid: str, repository: ChatRepository = Depends(chats)) -> dict:
    transcript = repository.transcript(chat_uuid)
    if not transcript:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found.")
    return transcript


@router.patch("/chats/{chat_uuid}", response_model=ChatResponse)
def update_chat(
    chat_uuid: str,
    payload: ChatUpdateRequest,
    repository: ChatRepository = Depends(chats),
) -> dict:
    try:
        chat = repository.update(
            chat_uuid, title=payload.title, backend=payload.default_backend
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found.")
    return chat


@router.delete("/chats/{chat_uuid}")
def delete_chat(
    chat_uuid: str, repository: ChatRepository = Depends(chats)
) -> dict:
    try:
        deleted = repository.delete(chat_uuid)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"id": deleted["id"], "deleted": True}


@router.post(
    "/chats/{chat_uuid}/messages",
    response_model=MessageAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_message(
    chat_uuid: str,
    payload: MessageCreateRequest,
    coordinator: ChatCoordinator = Depends(chat_coordinator),
    repository: ChatRepository = Depends(chats),
) -> dict:
    chat = repository.get(chat_uuid)
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found.")
    selected_backend = payload.backend or Backend(chat["default_backend"])
    if selected_backend is Backend.ONLINE and not payload.online_disclosure_acknowledged:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Acknowledge that the question and retrieved excerpts will be sent to OpenAI.",
        )
    try:
        message, attempt = coordinator.submit_message(
            chat_uuid, payload.question, payload.backend
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found.") from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"message": message, "attempt": attempt}


@router.get("/attempts/{attempt_uuid}", response_model=AttemptResponse)
def get_attempt(
    attempt_uuid: str, repository: ChatRepository = Depends(chats)
) -> dict:
    attempt = repository.get_attempt(attempt_uuid)
    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found.")
    return attempt


@router.get("/attempts/{attempt_uuid}/events")
def attempt_events(
    attempt_uuid: str,
    last_event_id: int = Header(0, alias="Last-Event-ID"),
    repository: ChatRepository = Depends(chats),
    coordinator: ChatCoordinator = Depends(chat_coordinator),
) -> StreamingResponse:
    initial_attempt = repository.get_attempt(attempt_uuid)
    if not initial_attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found.")

    def body():
        if initial_attempt["state"] in {"completed", "failed", "cancelled"}:
            data = json.dumps(
                {"state": initial_attempt["state"], "output": initial_attempt.get("output")},
                ensure_ascii=False, separators=(",", ":"),
            )
            yield f"id: 1\nevent: {initial_attempt['state']}\ndata: {data}\n\n"
            return
        for event in coordinator.events.stream(attempt_uuid, last_event_id):
            if event is None:
                yield ": keep-alive\n\n"
                continue
            data = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
            yield f"id: {event.sequence}\nevent: {event.type}\ndata: {data}\n\n"

    return StreamingResponse(
        body(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/attempts/{attempt_uuid}/cancel", response_model=AttemptResponse)
def cancel_attempt(
    attempt_uuid: str,
    coordinator: ChatCoordinator = Depends(chat_coordinator),
    repository: ChatRepository = Depends(chats),
) -> dict:
    if not coordinator.cancel(attempt_uuid):
        if not repository.get_attempt(attempt_uuid):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Attempt is no longer active.")
    return repository.get_attempt(attempt_uuid) or {}


@router.post(
    "/messages/{message_uuid}/regenerate",
    response_model=AttemptResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def regenerate(
    message_uuid: str,
    payload: RegenerateRequest,
    coordinator: ChatCoordinator = Depends(chat_coordinator),
) -> dict:
    if payload.backend is Backend.ONLINE and not payload.online_disclosure_acknowledged:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Acknowledge that the question and retrieved excerpts will be sent to OpenAI.",
        )
    try:
        return coordinator.regenerate(message_uuid, payload.backend)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/attempts/{attempt_uuid}/sources")
def attempt_sources(
    attempt_uuid: str, repository: ChatRepository = Depends(chats)
) -> dict:
    attempt = repository.get_attempt(attempt_uuid)
    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found.")
    snapshot = repository.get_snapshot_for_attempt(attempt_uuid)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Retrieval is not complete.")
    package = build_prompt(snapshot)
    return {
        "attempt_id": attempt_uuid,
        "snapshot_checksum": snapshot["checksum"],
        "sources": package.evidence_items,
    }


@router.get("/attempts/{attempt_uuid}/diagnostics")
def attempt_diagnostics(
    attempt_uuid: str, repository: ChatRepository = Depends(chats)
) -> dict:
    """Expose frozen identities and ranks locally, but not provider credentials."""

    attempt = repository.get_attempt(attempt_uuid)
    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found.")
    snapshot = repository.get_snapshot_for_attempt(attempt_uuid)
    return {
        "attempt": {
            key: attempt.get(key) for key in (
                "id", "message_id", "backend", "state", "prompt_checksum",
                "provider_identity", "usage", "timing", "validation", "error_code",
                "error_message", "created_at", "completed_at",
            )
        },
        "retrieval": None if snapshot is None else {
            "snapshot_id": snapshot["id"],
            "checksum": snapshot["checksum"],
            "original_query": snapshot["original_query"],
            "processed_query": snapshot["processed_query"],
            "book_fingerprint": snapshot["book_fingerprint"],
            "profile_fingerprint": snapshot["profile_fingerprint"],
            "activated_specialist_signals": snapshot["activated_specialist_signals"],
            "retrieval_latency_ms": snapshot["retrieval_latency_ms"],
            "component_diagnostics": snapshot["component_diagnostics"],
            "evidence": snapshot["evidence"],
        },
    }
