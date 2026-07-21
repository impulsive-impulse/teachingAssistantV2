"""Safe upload staging and duplicate resolution.

This service only accepts and stages the file.  The ingestion coordinator owns
all expensive parsing and indexing so an HTTP disconnect cannot abandon work.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from ..config import AppSettings
from ..domain import BookStatus
from ..repositories import BookRepository


PDF_MAGIC = b"%PDF-"
SAFE_TITLE_RE = re.compile(r"[_\-]+")


class UploadRejected(ValueError):
    """A safe validation failure suitable for a 4xx response."""


@dataclass(frozen=True)
class UploadResult:
    disposition: str
    book: dict
    job: dict | None


class UploadService:
    """Stream one PDF into a job directory without trusting its filename."""

    def __init__(self, settings: AppSettings, books: BookRepository):
        self.settings = settings
        self.books = books

    async def accept(self, upload: UploadFile) -> UploadResult:
        filename = Path(upload.filename or "upload.pdf").name
        if Path(filename).suffix.lower() != ".pdf":
            raise UploadRejected("Only PDF textbook files are supported.")

        # A random job-scoped name prevents two simultaneous uploads with the
        # same browser filename from sharing a write target.
        temporary = self.settings.data_dir / "jobs" / f"incoming-{uuid4()}.partial"
        digest = hashlib.sha256()
        total = 0
        header = b""
        try:
            with temporary.open("wb") as handle:
                while chunk := await upload.read(1024 * 1024):
                    if not header:
                        header = chunk[:5]
                    total += len(chunk)
                    if total > self.settings.max_upload_bytes:
                        raise UploadRejected("This PDF exceeds the configured local upload limit.")
                    digest.update(chunk)
                    handle.write(chunk)
            if total == 0 or header != PDF_MAGIC:
                raise UploadRejected("The selected file is not a valid PDF document.")
            checksum = digest.hexdigest()
            existing = self.books.get_by_checksum(checksum)
            if existing:
                active = self.books.find_active_job_by_checksum(checksum)
                if existing["status"] == BookStatus.FAILED.value and not active:
                    raise UploadRejected(
                        "This upload previously failed validation. Remove the failed upload before retrying it."
                    )
                return UploadResult(
                    "duplicate_active" if active else "duplicate_ready", existing, active
                )

            title = _title_from_filename(filename)
            book, job = self.books.create_pending(checksum, filename, title)
            job_dir = self.settings.data_dir / "jobs" / job["id"]
            job_dir.mkdir(parents=True, exist_ok=False)
            staged = job_dir / "upload.partial"
            temporary.replace(staged)
            return UploadResult("created", book, job)
        finally:
            await upload.close()
            temporary.unlink(missing_ok=True)


def _title_from_filename(filename: str) -> str:
    title = SAFE_TITLE_RE.sub(" ", Path(filename).stem)
    title = re.sub(r"\s+", " ", title).strip()
    return title[:200] or "Untitled textbook"
