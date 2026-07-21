"""Validation, artifact, and durable-worker tests for uploaded textbooks."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from textbook_chat.app import create_app
from textbook_chat.config import AppSettings
from textbook_chat.ingestion.artifacts import ArtifactBuilder
from textbook_chat.ingestion.models import ChapterRecord, ValidationResult
from textbook_chat.ingestion.policy import IngestionPolicy
from textbook_chat.ingestion.validator import TextbookValidationError, TextbookValidator
from test_textbook_chat_app import ROOT, pdf_bytes


def app_settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        root=ROOT,
        data_dir=tmp_path / "app_data",
        database_path=tmp_path / "app_data" / "app.db",
        host="127.0.0.1",
        port=8765,
        max_upload_bytes=50 * 1024 * 1024,
        max_pdf_pages=1500,
        openai_api_key_present=False,
    )


def page_records() -> tuple[list[dict], list[ChapterRecord]]:
    chapters = [
        ChapterRecord(1, "Foundations", 1, 3, 14, ["test"], "high"),
        ChapterRecord(2, "Applications", 13, 15, 26, ["test"], "high"),
    ]
    pages = []
    for pdf_page in range(1, 27):
        chapter = chapters[0] if 3 <= pdf_page <= 14 else chapters[1] if pdf_page >= 15 else None
        text = " ".join(f"concept{number % 19}" for number in range(180)) if chapter else "front matter"
        pages.append({
            "book_id": "uploaded_test",
            "source_file": "Synthetic Textbook.pdf",
            "pdf_page_number": pdf_page,
            "textbook_page_number": pdf_page - 2 if chapter else None,
            "chapter_number": chapter.chapter_number if chapter else None,
            "chapter_title": chapter.chapter_title if chapter else None,
            "section_title": None,
            "raw_text": text,
            "cleaned_text": text,
            "text_length": len(text),
            "has_image": False,
            "has_table": False,
            "has_equation_like_text": False,
            "extraction_notes": [],
        })
    return pages, chapters


def test_non_model_artifacts_preserve_frozen_chunking_and_allow_empty_specialists(tmp_path: Path) -> None:
    pages, chapters = page_records()
    result = ValidationResult(
        accepted=True,
        error_code=None,
        user_message=None,
        title="Synthetic Textbook",
        page_count=len(pages),
        searchable_page_count=24,
        content_pdf_offset=2,
        page_mapping_method="test_constant_offset",
        page_mapping_confidence="high",
        chapters=chapters,
        pages=pages,
        metrics={},
        signals=[],
    )
    staging = tmp_path / "staging"
    manifest = ArtifactBuilder(IngestionPolicy()).build_non_model_artifacts(
        result, staging, "a" * 64
    )

    chunks = [json.loads(line) for line in (staging / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(chunks) >= 5
    assert all(chunk["chunking_strategy"] == "fixed" for chunk in chunks)
    assert all(len({pages[pdf_page - 1]["chapter_number"] for pdf_page in chunk["pdf_pages"]}) == 1 for chunk in chunks)
    assert manifest["retrieval_compatibility"]["benchmark_validated"] is False
    assert manifest["retrieval_compatibility"]["chunk_target_tokens"] == 600
    assert manifest["book_specific_vocabulary"]["state"] == "not_available"
    assert (staging / "specialists" / "formula.jsonl").read_text(encoding="utf-8") == ""
    bm25 = json.loads((staging / "indexes" / "bm25_manifest.json").read_text(encoding="utf-8"))
    assert bm25["chunks"]["reconstruction_verified"] is True
    assert bm25["formula"]["documents"] == 0


def test_text_gate_distinguishes_scanned_content() -> None:
    validator = TextbookValidator(IngestionPolicy(), maximum_pages=100)
    with pytest.raises(TextbookValidationError) as caught:
        validator._require_text_layer({
            "text_page_ratio": 0.2,
            "median_text_characters": 0,
            "replacement_character_ratio": 0,
            "alphabetic_character_ratio": 0,
        })
    assert caught.value.code == "scanned_or_image_only"
    assert caught.value.user_message == "This PDF appears to be scanned. OCR is not supported."


def test_background_worker_durably_rejects_too_short_pdf(tmp_path: Path) -> None:
    configured = app_settings(tmp_path)
    with TestClient(create_app(configured)) as client:
        uploaded = client.post(
            "/api/books/upload",
            files={"upload": ("one-page.pdf", pdf_bytes(), "application/pdf")},
        ).json()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get(f"/api/ingestion/{uploaded['job']['id']}").json()
            if job["state"] == "failed":
                break
            time.sleep(0.05)
        book = client.get(f"/api/books/{uploaded['book']['id']}").json()

    assert job["state"] == "failed"
    assert job["error_code"] == "pdf_too_short"
    assert book["status"] == "failed"
    assert "reliable textbook structure" in book["status_reason"]


BIOLOGY_PDF = ROOT / "books" / "X Biology EM 2025-26.pdf"


@pytest.mark.skipif(not BIOLOGY_PDF.is_file(), reason="frozen source PDF is not in this checkout")
def test_dynamic_validator_recovers_frozen_biology_structure() -> None:
    result = TextbookValidator(IngestionPolicy(), maximum_pages=1500).validate(
        BIOLOGY_PDF, "uploaded_biology", BIOLOGY_PDF.name
    )

    assert result.accepted is True
    assert result.content_pdf_offset == 9
    assert len(result.chapters) == 10
    assert result.chapters[0].textbook_page_start == 1
    assert result.searchable_page_count >= 240
    assert result.metrics["text_page_ratio"] >= 0.90
    assert result.metrics["latin_letter_ratio"] >= 0.90
