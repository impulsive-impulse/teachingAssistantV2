"""Pinned model identity and durable setup coordination tests."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from textbook_chat.config import AppSettings
from textbook_chat.database import Database, SCHEMA_VERSION
from textbook_chat.models.embedding import EmbeddingArtifact, EmbeddingArtifactRegistry
from textbook_chat.repositories import ModelSetupRepository
from textbook_chat.services.model_setup import ModelSetupCoordinator
from test_textbook_chat_app import ROOT


def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        root=ROOT, data_dir=tmp_path, database_path=tmp_path / "app.db",
        host="127.0.0.1", port=8765, max_upload_bytes=1024,
        max_pdf_pages=100, openai_api_key_present=False,
    )


class FakeRegistry:
    def __init__(self, artifact: EmbeddingArtifact):
        self.artifact = artifact

    def discover(self) -> EmbeddingArtifact:
        return self.artifact


class FakeIngestion:
    def __init__(self):
        self.resume_calls = 0

    def resume_waiting(self) -> None:
        self.resume_calls += 1


def test_setup_reuses_verified_snapshot_without_download(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    repository = ModelSetupRepository(database)
    artifact = EmbeddingArtifact(tmp_path / "snapshot", "frozen", 11, 134_505_940)
    artifact.path.mkdir()
    ingestion = FakeIngestion()
    coordinator = ModelSetupCoordinator(repository, FakeRegistry(artifact), ingestion)  # type: ignore[arg-type]
    try:
        job = coordinator.begin_embedding_setup()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            current = repository.get(job["id"])
            if current and current["state"] == "completed":
                break
            time.sleep(0.02)
    finally:
        coordinator.shutdown()

    assert current is not None
    assert current["state"] == "completed"
    assert current["stage"] == "verified"
    assert current["downloaded_bytes"] == 0
    assert current["total_bytes"] == 134_505_940
    assert ingestion.resume_calls == 1
    with database.connect() as connection:
        versions = {row["version"] for row in connection.execute("SELECT version FROM schema_migrations")}
    assert versions == set(range(1, SCHEMA_VERSION + 1))


FROZEN_SNAPSHOT = (
    Path.home() / ".cache" / "huggingface" / "hub" /
    "models--BAAI--bge-small-en-v1.5" / "snapshots" /
    "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
)


@pytest.mark.skipif(not FROZEN_SNAPSHOT.is_dir(), reason="frozen model snapshot is not cached")
def test_existing_snapshot_matches_frozen_manifest_identity(tmp_path: Path) -> None:
    registry = EmbeddingArtifactRegistry(settings(tmp_path))
    artifact = registry.discover()

    assert artifact is not None
    assert artifact.path == FROZEN_SNAPSHOT.resolve()
    assert artifact.identity_sha256 == "a76ed7f34fddfec52b0d6f9829f767fb2bcf1a05540e272b4ceb2e0081d846b4"
    assert artifact.file_count == 11
    assert artifact.size_bytes == 134_505_940
