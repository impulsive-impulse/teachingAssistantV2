"""Durability and scope invariants for book-bound chat questions."""

from __future__ import annotations

from pathlib import Path

import pytest

from textbook_chat.database import Database, SCHEMA_VERSION
from textbook_chat.domain import AttemptState, Backend
from textbook_chat.repositories import ChatRepository, utc_now
from textbook_chat.repositories import BookRepository
from textbook_chat.services.deletion import BookDeletionService
from test_textbook_chat_app import settings as app_settings


def _ready_book(database: Database, book_uuid: str = "book-1") -> None:
    now = utc_now()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO books(id, book_id, sha256, original_filename, title, status, "
            "artifact_path, ingestion_policy_version, runtime_profile_version, created_at) "
            "VALUES (?, ?, ?, 'book.pdf', 'Biology', 'ready', 'books/book-1', "
            "'upload-policy-v1', 'retrieval-v1-derived-v1', ?)",
            (book_uuid, "uploaded_book_1", "a" * 64, now),
        )


def _snapshot(question: str) -> dict:
    return {
        "book_fingerprint": "book-fingerprint",
        "profile_fingerprint": "profile-fingerprint",
        "question": question,
        "processed_query": question.lower(),
        "activated_specialist_signals": ["visual_caption_context"],
        "evidence": [{"rank": index, "evidence_id": f"chunk-{index}"} for index in range(1, 6)],
        "assembled_context": [{"text": "context"}],
        "component_diagnostics": {"dense": "recorded"},
        "retrieval_latency_ms": 12.5,
        "checksum": "b" * 64,
    }


def test_schema_migrates_to_current_version(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    with database.connect() as connection:
        versions = [row["version"] for row in connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )]
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(answer_attempts)")}

    assert versions == list(range(1, SCHEMA_VERSION + 1))
    assert {"prompt_checksum", "raw_output_text"} <= columns


def test_messages_are_independent_and_regeneration_reuses_snapshot(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    _ready_book(database)
    repository = ChatRepository(database)
    chat = repository.create("book-1", backend=Backend.ONLINE)

    first_message, first_attempt = repository.create_message_attempt(
        chat["id"], "Explain photosynthesis."
    )
    second_message, second_attempt = repository.create_message_attempt(
        chat["id"], "Define an electric circuit.", Backend.OFFLINE
    )

    assert first_message["question"] == "Explain photosynthesis."
    assert second_message["question"] == "Define an electric circuit."
    assert first_attempt["backend"] == "online"
    assert second_attempt["backend"] == "offline"
    assert first_attempt["message_id"] != second_attempt["message_id"]

    repository.set_attempt_state(first_attempt["id"], AttemptState.RETRIEVING)
    snapshot_id = repository.persist_retrieval_snapshot(
        first_attempt["id"], _snapshot(first_message["question"])
    )
    repository.set_attempt_state(first_attempt["id"], AttemptState.VALIDATING)
    repository.complete_attempt(
        first_attempt["id"], raw_output="{}", output={}, provider_identity="test-provider",
        usage={}, timing={}, validation={"valid": True},
    )
    regeneration = repository.create_regeneration(first_message["id"], Backend.OFFLINE)

    assert regeneration["retrieval_snapshot_id"] == snapshot_id
    persisted = repository.get_snapshot_for_attempt(regeneration["id"])
    assert persisted is not None
    assert persisted["question"] == first_message["question"]
    assert persisted["checksum"] == "b" * 64


def test_chat_title_can_be_renamed_and_persists(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    _ready_book(database)
    repository = ChatRepository(database)
    chat = repository.create("book-1")

    renamed = repository.update(chat["id"], title="  Photosynthesis review  ")

    assert renamed is not None
    assert renamed["title"] == "Photosynthesis review"
    assert repository.get(chat["id"])["title"] == "Photosynthesis review"
    with pytest.raises(ValueError, match="must not be empty"):
        repository.update(chat["id"], title="   ")


def test_only_one_active_attempt_per_message(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    _ready_book(database)
    repository = ChatRepository(database)
    chat = repository.create("book-1")
    message, attempt = repository.create_message_attempt(chat["id"], "A question")
    repository.set_attempt_state(attempt["id"], AttemptState.RETRIEVING)
    repository.persist_retrieval_snapshot(attempt["id"], _snapshot(message["question"]))

    with pytest.raises(Exception, match="UNIQUE constraint failed"):
        repository.create_regeneration(message["id"], Backend.OFFLINE)


def test_book_deletion_removes_only_owned_content_and_cascades_transcript(tmp_path: Path) -> None:
    settings = app_settings(tmp_path)
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()
    _ready_book(database)
    chats = ChatRepository(database)
    chat = chats.create("book-1")
    artifact = settings.data_dir / "books" / "book-1"
    artifact.mkdir()
    (artifact / "source.pdf").write_bytes(b"%PDF-test")
    unrelated = settings.data_dir / "models" / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")
    evicted: list[str] = []

    result = BookDeletionService(
        settings, BookRepository(database), evicted.append
    ).delete("book-1")

    assert result == {"id": "book-1", "deleted": True}
    assert evicted == ["book-1"]
    assert not artifact.exists()
    assert unrelated.read_text("utf-8") == "keep"
    assert chats.get(chat["id"]) is None
