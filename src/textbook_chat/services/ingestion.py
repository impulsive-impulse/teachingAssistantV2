"""Durable single-worker ingestion coordinator.

CPU-heavy validation and indexing never runs on FastAPI's event loop. Durable
SQLite state is updated throughout the job, so browser refreshes and backend
restarts do not lose progress or expose half-published books.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from ..config import AppSettings
from ..domain import JobState
from ..ingestion.artifacts import ArtifactBuilder
from ..ingestion.policy import IngestionPolicy
from ..ingestion.validator import TextbookValidationError, TextbookValidator
from ..repositories import BookRepository


class IngestionCoordinator:
    """Serialize ingestion jobs and resume interrupted work safely."""

    def __init__(self, settings: AppSettings, books: BookRepository):
        self.settings = settings
        self.books = books
        self.policy = IngestionPolicy()
        self.validator = TextbookValidator(self.policy, settings.max_pdf_pages)
        self.artifacts = ArtifactBuilder(self.policy)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="textbook-ingestion")
        self._lock = threading.Lock()
        self._active: dict[str, Future[None]] = {}
        self._closed = False

    def start(self) -> None:
        """Recover jobs whose process ended before an atomic publication."""

        self.books.interrupt_running_jobs()
        for job in self.books.list_resumable_jobs():
            self.submit(job["id"])

    def submit(self, job_uuid: str) -> None:
        with self._lock:
            if self._closed or job_uuid in self._active:
                return
            future = self._executor.submit(self._run, job_uuid)
            self._active[job_uuid] = future
            future.add_done_callback(lambda _future, job=job_uuid: self._finished(job))

    def resume_waiting(self) -> None:
        """Resume model-blocked jobs only when artifacts and runtime are ready."""

        if not self._embedding_ready():
            return
        for job in self.books.list_waiting_jobs("waiting_for_embedding_model"):
            self.submit(job["id"])

    def shutdown(self) -> None:
        """Stop accepting jobs and let the current safe operation wind down."""

        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _finished(self, job_uuid: str) -> None:
        with self._lock:
            self._active.pop(job_uuid, None)

    def _run(self, job_uuid: str) -> None:
        job = self.books.get_job(job_uuid)
        if not job or not job.get("book_id"):
            return
        book = self.books.get(job["book_id"])
        if not book:
            return
        job_root = (self.settings.data_dir / "jobs" / job_uuid).resolve()
        source = job_root / "upload.partial"
        staging = job_root / "staging"
        try:
            self._prepare_staging(job_root, staging)
            self.books.update_job(
                job_uuid, state=JobState.RUNNING, stage="validating_pdf",
                stage_progress=0, overall_progress=0.06,
            )
            last_reported = 0

            def progress(_stage: str, current: int, total: int) -> None:
                nonlocal last_reported
                if current == total or current - last_reported >= max(1, total // 40):
                    last_reported = current
                    self.books.update_job(
                        job_uuid, state=JobState.RUNNING, stage="extracting_pages",
                        stage_progress=current / total,
                        overall_progress=0.10 + 0.25 * current / total,
                    )

            result = self.validator.validate(
                source, book["book_id"], book["original_filename"], progress
            )
            self.books.update_book_validation(
                book["id"], title=result.title, page_count=result.page_count,
                searchable_page_count=result.searchable_page_count,
                chapter_count=len(result.chapters),
            )
            self.books.update_job(
                job_uuid, state=JobState.RUNNING, stage="building_corpora",
                stage_progress=0, overall_progress=0.40,
            )
            self.artifacts.build_non_model_artifacts(result, staging, book["sha256"])
            self.books.update_job(
                job_uuid, state=JobState.RUNNING, stage="building_bm25_indexes",
                stage_progress=1, overall_progress=0.58,
            )
            if not self._embedding_ready():
                self.books.update_job(
                    job_uuid, state=JobState.WAITING, stage="waiting_for_embedding_model",
                    stage_progress=0, overall_progress=0.60,
                    user_message="Pinned BGE embedding model setup is required before indexing can continue.",
                )
                return
            self.books.update_job(
                job_uuid, state=JobState.RUNNING, stage="building_dense_indexes",
                stage_progress=0, overall_progress=0.64,
            )
            self.artifacts.build_dense_indexes(
                staging, self.settings.data_dir / "models" / "embeddings", self.settings.root
            )
            self.books.update_job(
                job_uuid, state=JobState.RUNNING, stage="verifying_artifacts",
                stage_progress=0, overall_progress=0.92,
            )
            # Copy first so a failed verification leaves the job's original
            # upload available for a clean retry.
            shutil.copy2(source, staging / "source.pdf")
            self.artifacts.finalize_manifest(staging)
            final = (self.settings.data_dir / "books" / book["id"]).resolve()
            if final.exists():
                raise RuntimeError("final book directory already exists")
            staging.replace(final)
            source.unlink(missing_ok=True)
            self.books.complete_ingestion(
                book["id"], job_uuid,
                str((final / "source.pdf").relative_to(self.settings.data_dir)),
                str(final.relative_to(self.settings.data_dir)),
            )
        except TextbookValidationError as exc:
            self.books.fail_ingestion(book["id"], job_uuid, exc.code, exc.user_message, repr(exc))
        except Exception as exc:
            self.books.fail_ingestion(
                book["id"], job_uuid, "ingestion_failed",
                "Textbook processing failed. Open diagnostics for details.",
                "".join(traceback.format_exception_only(type(exc), exc)).strip(),
            )

    def _prepare_staging(self, job_root: Path, staging: Path) -> None:
        expected_root = (self.settings.data_dir / "jobs").resolve()
        if expected_root not in job_root.parents:
            raise RuntimeError("ingestion job path escaped the configured jobs directory")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=False)

    def _embedding_ready(self) -> bool:
        if importlib.util.find_spec("sentence_transformers") is None:
            return False
        from ..models.embedding import EmbeddingArtifactRegistry

        return EmbeddingArtifactRegistry(self.settings).discover() is not None
