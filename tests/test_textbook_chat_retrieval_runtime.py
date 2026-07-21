"""Book-scoped retrieval adapter tests using deterministic local vectors."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from textbook_chat.ingestion.artifacts import ArtifactBuilder
from textbook_chat.ingestion.models import ChapterRecord, ValidationResult
from textbook_chat.ingestion.policy import IngestionPolicy
from textbook_chat.retrieval.runtime import UploadedBookRetrievalRuntime
from test_textbook_chat_app import ROOT
from test_textbook_chat_ingestion import page_records


class FakeEncoder:
    """Minimal SentenceTransformer-compatible query encoder for rank tests."""

    def encode(self, texts, **_kwargs):
        matrix = np.zeros((len(texts), 384), dtype=np.float32)
        matrix[:, 0] = 1.0
        return matrix


class FakeLoadedModel:
    def __init__(self):
        self.model = FakeEncoder()


def prepared_book(tmp_path: Path) -> Path:
    pages, chapters = page_records()
    result = ValidationResult(
        accepted=True, error_code=None, user_message=None,
        title="Synthetic Textbook", page_count=len(pages), searchable_page_count=24,
        content_pdf_offset=2, page_mapping_method="test", page_mapping_confidence="high",
        chapters=chapters, pages=pages, metrics={}, signals=[],
    )
    book_dir = tmp_path / "book"
    builder = ArtifactBuilder(IngestionPolicy())
    builder.build_non_model_artifacts(result, book_dir, "a" * 64)
    chunks = [json.loads(line) for line in (book_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    baseline = yaml.safe_load((ROOT / "config" / "retrieval_baseline_v1.yaml").read_text(encoding="utf-8"))
    revision = baseline["embedding"]["revision"]
    indexes = book_dir / "indexes"
    for branch, rows in (
        ("chunks", len(chunks)), ("formula", 0), ("table", 0), ("visual", 0)
    ):
        matrix = np.zeros((rows, 384), dtype=np.float32)
        if rows:
            # Dense order alone is deterministic; BM25 remains an equal source.
            matrix[:, 0] = np.linspace(1.0, 0.1, rows)
        np.savez_compressed(
            indexes / f"{branch}.npz", embeddings=matrix,
            corpus_fingerprint=np.asarray("fixture"),
            model_revision=np.asarray(revision), dimensions=np.asarray(384),
        )
    (book_dir / "source.pdf").write_bytes(b"synthetic source")
    builder.finalize_manifest(book_dir)
    return book_dir


def test_uploaded_runtime_returns_exactly_five_book_scoped_evidence_units(tmp_path: Path) -> None:
    runtime = UploadedBookRetrievalRuntime.load(
        prepared_book(tmp_path), FakeLoadedModel(), ROOT,
        expected_source_checksum="a" * 64,
    )

    result = runtime.retrieve("How does concept1 relate to concept2?")

    assert result.baseline_name == "Retrieval Baseline v1"
    assert result.baseline_version == "1.0.0"
    assert result.runtime_profile == "retrieval-v1-derived-v1"
    assert len(result.evidence) == 5
    assert [item["rank"] for item in result.evidence] == [1, 2, 3, 4, 5]
    assert {item["book_id"] for item in result.evidence} == {"uploaded_test"}
    assert all(item["evidence_text"] for item in result.evidence)
    assert result.assembled_context
    assert len(result.checksum) == 64
    assert len(result.book_fingerprint) == 64
    assert len(result.profile_fingerprint) == 64


def test_runtime_rejects_empty_question_and_wrong_book_checksum(tmp_path: Path) -> None:
    book_dir = prepared_book(tmp_path)
    with pytest.raises(RuntimeError, match="source checksum"):
        UploadedBookRetrievalRuntime.load(
            book_dir, FakeLoadedModel(), ROOT, expected_source_checksum="b" * 64
        )
    runtime = UploadedBookRetrievalRuntime.load(
        book_dir, FakeLoadedModel(), ROOT, expected_source_checksum="a" * 64
    )
    with pytest.raises(ValueError, match="must not be empty"):
        runtime.retrieve("   ")


def test_runtime_detects_post_publication_artifact_tampering(tmp_path: Path) -> None:
    book_dir = prepared_book(tmp_path)
    with (book_dir / "chunks.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{}\n")

    with pytest.raises(RuntimeError, match="checksum verification"):
        UploadedBookRetrievalRuntime.load(book_dir, FakeLoadedModel(), ROOT)
