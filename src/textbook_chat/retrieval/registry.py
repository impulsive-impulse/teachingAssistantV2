"""Lazy, checksum-gated registry for uploaded-book retrieval runtimes."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import yaml

from textbook_audit.embedding_bakeoff import load_local_model

from ..config import AppSettings
from ..models.embedding import EmbeddingArtifactRegistry
from .runtime import UploadedBookRetrievalRuntime


class RetrievalRuntimeRegistry:
    """Load the exact CPU encoder once and cache isolated runtimes per book."""

    def __init__(self, settings: AppSettings, artifacts: EmbeddingArtifactRegistry):
        self.settings = settings
        self.artifacts = artifacts
        self._lock = threading.RLock()
        self._embedding: Any | None = None
        self._runtimes: dict[tuple[str, str], UploadedBookRetrievalRuntime] = {}

    def for_book(self, book: dict[str, Any]) -> UploadedBookRetrievalRuntime:
        """Return a runtime only for the database-bound, verified artifact directory."""

        artifact_relative = book.get("book_artifact_path")
        checksum = book.get("book_sha256")
        book_uuid = book.get("book_id")
        if not all(isinstance(value, str) and value for value in (artifact_relative, checksum, book_uuid)):
            raise RuntimeError("book does not have a complete indexed artifact identity")
        book_dir = (self.settings.data_dir / artifact_relative).resolve()
        if self.settings.data_dir.resolve() not in book_dir.parents:
            raise RuntimeError("book artifact path escaped application storage")
        key = (book_uuid, checksum)
        with self._lock:
            if key in self._runtimes:
                return self._runtimes[key]
            embedding = self._load_embedding()
            runtime = UploadedBookRetrievalRuntime.load(
                book_dir, embedding, self.settings.root, expected_source_checksum=checksum
            )
            if runtime.manifest.get("book_id") != book.get("retrieval_book_id"):
                raise RuntimeError("book artifact identity does not match its chat scope")
            self._runtimes[key] = runtime
            return runtime

    def evict(self, book_uuid: str) -> None:
        with self._lock:
            self._runtimes = {
                key: runtime for key, runtime in self._runtimes.items() if key[0] != book_uuid
            }

    def _load_embedding(self) -> Any:
        if self._embedding is not None:
            return self._embedding
        artifact = self.artifacts.discover()
        if artifact is None:
            raise RuntimeError("the pinned BGE embedding artifact is not installed")
        baseline = yaml.safe_load(
            (self.settings.root / "config" / "retrieval_baseline_v1.yaml").read_text("utf-8")
        )
        # snapshot/revision -> snapshots -> repository -> Hugging Face cache root
        cache_root = artifact.path.parents[2]
        self._embedding = load_local_model(
            baseline["embedding"], cache_root, "cpu", batch_size=16
        )
        return self._embedding
