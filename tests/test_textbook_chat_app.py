"""Integration checks for the production application's first vertical slice."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from textbook_chat.app import create_app
from textbook_chat.config import AppSettings


ROOT = Path(__file__).resolve().parents[1]


def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        root=ROOT,
        data_dir=tmp_path / "app_data",
        database_path=tmp_path / "app_data" / "app.db",
        host="127.0.0.1",
        port=8765,
        max_upload_bytes=10 * 1024 * 1024,
        max_pdf_pages=100,
        openai_api_key_present=False,
    )


def pdf_bytes() -> bytes:
    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(stream)
    return stream.getvalue()


def test_startup_initializes_database_and_reports_locked_profiles(tmp_path: Path) -> None:
    app_settings = settings(tmp_path)
    with TestClient(create_app(app_settings, run_workers=False)) as client:
        response = client.get("/api/system/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["database"]["state"] == "ready"
    assert payload["profiles"]["online_model"] == "gpt-4o-2024-08-06"
    assert payload["profiles"]["online_max_output_tokens"] == 768
    assert payload["profiles"]["offline_model"] == "Qwen3-8B-Q4_K_M.gguf"
    assert payload["profiles"]["offline_max_output_tokens"] == 384
    assert app_settings.database_path.is_file()


def test_upload_is_staged_and_byte_identical_duplicate_is_reused(tmp_path: Path) -> None:
    app_settings = settings(tmp_path)
    contents = pdf_bytes()
    with TestClient(create_app(app_settings, run_workers=False)) as client:
        first = client.post(
            "/api/books/upload", files={"upload": ("Physics_Textbook.pdf", contents, "application/pdf")}
        )
        second = client.post(
            "/api/books/upload", files={"upload": ("Renamed.pdf", contents, "application/pdf")}
        )
        books = client.get("/api/books")

    assert first.status_code == 202
    assert first.json()["disposition"] == "created"
    assert first.json()["book"]["title"] == "Physics Textbook"
    assert first.json()["book"]["status"] == "validating"
    assert second.status_code == 202
    assert second.json()["disposition"] == "duplicate_active"
    assert second.json()["book"]["id"] == first.json()["book"]["id"]
    assert len(books.json()) == 1
    staged = app_settings.data_dir / "jobs" / first.json()["job"]["id"] / "upload.partial"
    assert staged.read_bytes() == contents


def test_invalid_upload_is_rejected_without_persistent_records(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path), run_workers=False)) as client:
        response = client.post(
            "/api/books/upload", files={"upload": ("not-a-book.pdf", b"plain text", "application/pdf")}
        )
        books = client.get("/api/books")

    assert response.status_code == 422
    assert response.json()["detail"] == "The selected file is not a valid PDF document."
    assert books.json() == []


def test_chat_cannot_be_created_before_indexing_finishes(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path), run_workers=False)) as client:
        uploaded = client.post(
            "/api/books/upload", files={"upload": ("Biology.pdf", pdf_bytes(), "application/pdf")}
        ).json()
        response = client.post(
            f"/api/books/{uploaded['book']['id']}/chats",
            json={"title": "Chapter one", "default_backend": "offline"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Chat becomes available only after this book finishes indexing."
