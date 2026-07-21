"""End-to-end worker checks without network or model dependencies."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from textbook_chat.database import Database
from textbook_chat.domain import Backend
from textbook_chat.generation.online import ProviderStreamEvent
from textbook_chat.repositories import ChatRepository, utc_now
from textbook_chat.services.chat import ChatCoordinator


def _ready_book(database: Database) -> None:
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO books(id, book_id, sha256, original_filename, title, status, "
            "artifact_path, ingestion_policy_version, runtime_profile_version, created_at) "
            "VALUES ('book-1', 'uploaded-book', ?, 'book.pdf', 'Book', 'ready', "
            "'books/book-1', 'upload-policy-v1', 'retrieval-v1-derived-v1', ?)",
            ("a" * 64, utc_now()),
        )


class FakeRuntime:
    def __init__(self):
        self.questions: list[str] = []

    def retrieve(self, question: str):
        self.questions.append(question)
        evidence = [{
            "rank": rank,
            "evidence_id": f"chunk-{rank}",
            "pdf_pages": [page],
            "textbook_pages": [page - 2],
            "evidence_text": f"Textbook evidence {rank}.",
        } for rank, page in enumerate((30, 10, 20, 40, 50), 1)]
        return SimpleNamespace(to_dict=lambda: {
            "book_fingerprint": "book-fingerprint",
            "profile_fingerprint": "profile-fingerprint",
            "question": question,
            "processed_query": question.lower(),
            "activated_specialist_signals": [],
            "evidence": evidence,
            "assembled_context": [{"text": "assembled"}],
            "component_diagnostics": {},
            "retrieval_latency_ms": 4.2,
            "checksum": "c" * 64,
        })


class FakeProvider:
    def __init__(self, model: str):
        self.model = model
        self.prompts: list[str] = []

    def stream(self, prompt: str, cancel=None):
        self.prompts.append(prompt)
        raw = json.dumps({
            "status": "answered",
            "answer": f"Answer from {self.model}.",
            "selected_evidence_ids": ["E1"],
            "citations": [{"evidence_id": "E1", "pdf_page": 10, "textbook_page": 8}],
            "missing_information": [],
        })
        yield ProviderStreamEvent("answer_delta", {"delta": "Answer"})
        yield ProviderStreamEvent("completed", {
            "raw_text": raw,
            "resolved_model": self.model,
            "usage": {"total_tokens": 25},
            "latency_seconds": 0.1,
            "time_to_first_token_seconds": 0.02,
        })


def _wait(repository: ChatRepository, attempt_uuid: str) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        attempt = repository.get_attempt(attempt_uuid)
        if attempt and attempt["state"] in {"completed", "failed", "cancelled"}:
            return attempt
        time.sleep(0.01)
    raise AssertionError("attempt did not finish")


def test_new_question_retrieves_once_and_regeneration_reuses_identical_prompt(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    _ready_book(database)
    repository = ChatRepository(database)
    chat = repository.create("book-1", backend=Backend.ONLINE)
    runtime = FakeRuntime()
    online, offline = FakeProvider("online-frozen"), FakeProvider("offline-frozen")
    providers = {Backend.ONLINE: online, Backend.OFFLINE: offline}
    coordinator = ChatCoordinator(repository, lambda _book: runtime, providers.__getitem__)
    try:
        message, initial = coordinator.submit_message(chat["id"], "Explain the topic.")
        finished = _wait(repository, initial["id"])

        regenerated = coordinator.regenerate(message["id"], Backend.OFFLINE)
        regenerated_finished = _wait(repository, regenerated["id"])
    finally:
        coordinator.shutdown()

    assert runtime.questions == ["Explain the topic."]
    assert online.prompts == offline.prompts
    assert finished["state"] == "completed"
    assert regenerated_finished["state"] == "completed"
    assert finished["retrieval_snapshot_id"] == regenerated_finished["retrieval_snapshot_id"]
    assert finished["prompt_checksum"] == regenerated_finished["prompt_checksum"]
    assert finished["provider_identity"] == "online-frozen"
    assert regenerated_finished["provider_identity"] == "offline-frozen"
