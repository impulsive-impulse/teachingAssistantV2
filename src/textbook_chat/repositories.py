"""Persistence repositories containing all application SQL."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import PureWindowsPath
from typing import Any, Sequence
from uuid import uuid4

from textbook_audit.source_provenance import SourceDocument, document_set_fingerprint

from .database import Database
from .domain import AttemptState, Backend, BookStatus, JobState


def utc_now() -> str:
    """Return a stable, sortable UTC timestamp."""

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class BookRepository:
    """Queries and state transitions for library books and ingestion jobs."""

    def __init__(self, database: Database):
        self.database = database

    def list_books(self, include_failed: bool = True) -> list[dict[str, Any]]:
        where = "deleted_at IS NULL" if include_failed else "deleted_at IS NULL AND status != 'failed'"
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM books WHERE {where} "  # noqa: S608 - fixed internal clause
                "ORDER BY COALESCE(last_opened_at, created_at) DESC"
            ).fetchall()
        return [self._with_current_job(dict(row)) for row in rows]

    def get(self, book_uuid: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            book = _row(connection.execute(
                "SELECT * FROM books WHERE id = ? AND deleted_at IS NULL", (book_uuid,)
            ).fetchone())
        return self._with_current_job(book) if book else None

    def get_by_checksum(self, checksum: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            book = _row(connection.execute(
                "SELECT * FROM books WHERE sha256 = ? AND deleted_at IS NULL", (checksum,)
            ).fetchone())
        return self._with_current_job(book) if book else None

    def _with_current_job(self, book: dict[str, Any]) -> dict[str, Any]:
        with self.database.connect() as connection:
            job = connection.execute(
                "SELECT * FROM ingestion_jobs WHERE book_id = ? ORDER BY updated_at DESC LIMIT 1",
                (book["id"],),
            ).fetchone()
        return {**book, "current_job": dict(job) if job else None}

    def create_pending(self, checksum: str, filename: str, title: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Atomically publish the initial book and durable queued job records."""

        book_uuid, job_uuid = str(uuid4()), str(uuid4())
        now = utc_now()
        generated_book_id = f"uploaded_{book_uuid.replace('-', '')[:16]}"
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO books(id, book_id, sha256, original_filename, title, status, "
                "ingestion_policy_version, runtime_profile_version, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (book_uuid, generated_book_id, checksum, filename, title,
                 BookStatus.VALIDATING.value, "upload-policy-v1", "retrieval-v1-derived-v1", now),
            )
            connection.execute(
                "INSERT INTO ingestion_jobs(id, checksum, book_id, stage, state, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (job_uuid, checksum, book_uuid, "queued", JobState.QUEUED.value, now),
            )
        return self.get(book_uuid) or {}, self.get_job(job_uuid) or {}

    def get_job(self, job_uuid: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            return _row(connection.execute(
                "SELECT * FROM ingestion_jobs WHERE id = ?", (job_uuid,)
            ).fetchone())

    def find_active_job_by_checksum(self, checksum: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            return _row(connection.execute(
                "SELECT * FROM ingestion_jobs WHERE checksum = ? "
                "AND state IN ('queued', 'running', 'waiting', 'interrupted') ORDER BY updated_at DESC LIMIT 1",
                (checksum,),
            ).fetchone())

    def list_resumable_jobs(self) -> list[dict[str, Any]]:
        """Return work that is safe to resume after process startup."""

        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM ingestion_jobs WHERE state IN ('queued', 'interrupted') "
                "ORDER BY updated_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_waiting_jobs(self, stage: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM ingestion_jobs WHERE state='waiting' AND stage=? ORDER BY updated_at",
                (stage,),
            ).fetchall()
        return [dict(row) for row in rows]

    def interrupt_running_jobs(self) -> None:
        """Make an unclean prior shutdown explicit before recovery."""

        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE ingestion_jobs SET state = 'interrupted', stage = 'interrupted', updated_at = ? "
                "WHERE state = 'running'",
                (now,),
            )

    def update_job(
        self,
        job_uuid: str,
        *,
        state: JobState,
        stage: str,
        stage_progress: float,
        overall_progress: float,
        user_message: str | None = None,
        error_code: str | None = None,
        internal_detail: str | None = None,
        terminal: bool = False,
    ) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE ingestion_jobs SET state=?, stage=?, stage_progress=?, overall_progress=?, "
                "user_message=?, error_code=?, internal_detail=?, "
                "started_at=COALESCE(started_at, ?), updated_at=?, "
                "completed_at=CASE WHEN ? THEN ? ELSE completed_at END WHERE id=?",
                (state.value, stage, stage_progress, overall_progress, user_message, error_code,
                 internal_detail, now, now, terminal, now, job_uuid),
            )

    def update_book_validation(
        self,
        book_uuid: str,
        *,
        title: str,
        page_count: int,
        searchable_page_count: int,
        chapter_count: int,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE books SET title=?, status=?, page_count=?, searchable_page_count=?, "
                "chapter_count=?, status_reason=NULL WHERE id=?",
                (title, BookStatus.PROCESSING.value, page_count, searchable_page_count,
                 chapter_count, book_uuid),
            )

    def fail_ingestion(self, book_uuid: str, job_uuid: str, code: str, message: str, detail: str) -> None:
        """Fail the job and book together so the library cannot disagree."""

        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE books SET status='failed', status_reason=? WHERE id=?", (message, book_uuid)
            )
            connection.execute(
                "UPDATE ingestion_jobs SET state='failed', stage='failed', error_code=?, "
                "user_message=?, internal_detail=?, updated_at=?, completed_at=? WHERE id=?",
                (code, message, detail, now, now, job_uuid),
            )

    def complete_ingestion(
        self,
        book_uuid: str,
        job_uuid: str,
        source_path: str,
        artifact_path: str,
    ) -> None:
        """Atomically expose a fully verified book and finish its job."""

        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE books SET status='ready', status_reason=NULL, source_path=?, artifact_path=?, "
                "indexed_at=?, last_opened_at=? WHERE id=?",
                (source_path, artifact_path, now, now, book_uuid),
            )
            connection.execute(
                "UPDATE ingestion_jobs SET state='completed', stage='ready', stage_progress=1, "
                "overall_progress=1, user_message=NULL, error_code=NULL, internal_detail=NULL, "
                "updated_at=?, completed_at=? WHERE id=?",
                (now, now, job_uuid),
            )

    def begin_delete(self, book_uuid: str) -> dict[str, Any]:
        """Lock a book against new work and return only its owned deletion targets."""

        with self.database.connect() as connection:
            book = connection.execute(
                "SELECT * FROM books WHERE id=? AND deleted_at IS NULL", (book_uuid,)
            ).fetchone()
            if not book:
                raise LookupError("book not found")
            memberships = connection.execute(
                "SELECT COUNT(*) AS count FROM collection_documents cd "
                "JOIN source_documents d ON d.id=cd.document_id WHERE d.book_id=?",
                (book_uuid,),
            ).fetchone()["count"]
            if memberships:
                raise RuntimeError("Remove this textbook from collections before deleting it.")
            active_ingestion = connection.execute(
                "SELECT COUNT(*) AS count FROM ingestion_jobs WHERE book_id=? "
                "AND state IN ('queued','running','interrupted')", (book_uuid,),
            ).fetchone()["count"]
            active_attempts = connection.execute(
                "SELECT COUNT(*) AS count FROM answer_attempts a "
                "JOIN user_messages m ON m.id=a.message_id JOIN chats c ON c.id=m.chat_id "
                "WHERE c.book_id=? AND a.state IN ('queued','retrieving','generating','validating')",
                (book_uuid,),
            ).fetchone()["count"]
            if active_ingestion or active_attempts:
                raise RuntimeError("Stop active processing and answers before deleting this textbook.")
            connection.execute("UPDATE books SET status='deleting' WHERE id=?", (book_uuid,))
            jobs = [row["id"] for row in connection.execute(
                "SELECT id FROM ingestion_jobs WHERE book_id=?", (book_uuid,)
            )]
        return {**dict(book), "job_ids": jobs}

    def finish_delete(self, book_uuid: str) -> None:
        with self.database.connect() as connection:
            connection.execute("DELETE FROM books WHERE id=? AND status='deleting'", (book_uuid,))

    def restore_after_delete_failure(self, book_uuid: str, prior_status: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE books SET status=?, status_reason='Local deletion did not finish.' "
                "WHERE id=? AND status='deleting'", (prior_status, book_uuid),
            )


class CollectionRepository:
    """Immutable source records and transactionally versioned document membership."""

    def __init__(self, database: Database):
        self.database = database

    def register_document(
        self, document: SourceDocument, *, book_id: str | None = None,
        artifact_path: str | None = None,
    ) -> dict[str, Any]:
        if artifact_path is not None:
            path = PureWindowsPath(artifact_path)
            if not artifact_path or path.drive or path.root or ".." in path.parts or not path.parts:
                raise ValueError("source artifact path must stay relative to application storage")
        payload = document.to_dict()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if book_id is not None:
                book = connection.execute(
                    "SELECT * FROM books WHERE id=? AND deleted_at IS NULL", (book_id,),
                ).fetchone()
                if (
                    book is None or book["status"] != "ready" or document.kind != "pdf"
                    or book["sha256"] != document.source_sha256
                ):
                    raise ValueError("source document does not match a ready library book")
            existing = connection.execute(
                "SELECT * FROM source_documents WHERE id=?", (document.document_id,),
            ).fetchone()
            if existing:
                restored = self._document(existing)
                if (
                    restored.content_sha256 != document.content_sha256
                    or existing["book_id"] != book_id or existing["artifact_path"] != artifact_path
                ):
                    raise ValueError("registered source content or ownership differs")
                return {"id": restored.document_id, "content_sha256": restored.content_sha256}
            connection.execute(
                "INSERT INTO source_documents(id,kind,source_sha256,content_sha256,source_json,"
                "book_id,artifact_path,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (document.document_id, document.kind, document.source_sha256, document.content_sha256,
                 _json(payload), book_id, artifact_path, utc_now()),
            )
        return {"id": document.document_id, "content_sha256": document.content_sha256}

    @staticmethod
    def _document(row: Any) -> SourceDocument:
        document = SourceDocument.from_dict(json.loads(row["source_json"]))
        if (
            document.document_id != row["id"] or document.kind != row["kind"]
            or document.source_sha256 != row["source_sha256"]
            or document.content_sha256 != row["content_sha256"]
        ):
            raise RuntimeError("persisted source identity is inconsistent")
        return document

    def document(self, document_id: str) -> SourceDocument:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM source_documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise LookupError("source document not found")
        return self._document(row)

    def list_documents(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM source_documents ORDER BY id").fetchall()
        return [self._summary(row) for row in rows]

    def _summary(self, row: Any) -> dict[str, Any]:
        document = self._document(row)
        return {
            "id": document.document_id, "kind": document.kind, "title": document.title,
            "source_sha256": document.source_sha256, "content_sha256": document.content_sha256,
            "book_id": row["book_id"], "unit_count": len(document.units),
        }

    def _sources(self, connection: Any, document_ids: Sequence[str]) -> list[SourceDocument]:
        if (
            not isinstance(document_ids, (list, tuple)) or not document_ids
            or any(not isinstance(document_id, str) or not document_id for document_id in document_ids)
            or len(set(document_ids)) != len(document_ids)
        ):
            raise ValueError("collection requires distinct non-empty document IDs")
        placeholders = ",".join("?" for _ in document_ids)
        rows = connection.execute(
            f"SELECT * FROM source_documents WHERE id IN ({placeholders}) ORDER BY id", tuple(document_ids),
        ).fetchall()
        if len(rows) != len(document_ids):
            raise LookupError("collection contains an unknown source document")
        return [self._document(row) for row in rows]

    def create(self, title: str, document_ids: Sequence[str]) -> dict[str, Any]:
        title = self._title(title)
        collection_id, now = str(uuid4()), utc_now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            documents = self._sources(connection, document_ids)
            connection.execute(
                "INSERT INTO collections(id,title,fingerprint,created_at,updated_at) VALUES (?,?,?,?,?)",
                (collection_id, title, document_set_fingerprint(documents), now, now),
            )
            connection.executemany(
                "INSERT INTO collection_documents(collection_id,document_id) VALUES (?,?)",
                [(collection_id, document.document_id) for document in documents],
            )
        result = self.get(collection_id)
        if result is None:
            raise RuntimeError("created collection could not be read")
        return result

    @staticmethod
    def _title(title: str) -> str:
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
            raise ValueError("collection title must contain 1-120 characters")
        return title.strip()

    def get(self, collection_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            connection.execute("BEGIN")
            row = connection.execute("SELECT * FROM collections WHERE id=?", (collection_id,)).fetchone()
            if row is None:
                return None
            members = connection.execute(
                "SELECT d.* FROM source_documents d JOIN collection_documents cd ON cd.document_id=d.id "
                "WHERE cd.collection_id=? ORDER BY d.id", (collection_id,),
            ).fetchall()
            documents = [self._document(member) for member in members]
            if not documents or row["fingerprint"] != document_set_fingerprint(documents):
                raise RuntimeError("collection membership fingerprint is inconsistent")
            return {
                **dict(row), "document_ids": [document.document_id for document in documents],
                "documents": [self._summary(member) for member in members],
            }

    def list(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            ids = [row["id"] for row in connection.execute("SELECT id FROM collections ORDER BY updated_at DESC,id")]
        result = []
        for collection_id in ids:
            collection = self.get(collection_id)
            if collection is not None:
                result.append(collection)
        return result

    def sources(self, collection_id: str, expected_fingerprint: str) -> list[SourceDocument]:
        with self.database.connect() as connection:
            connection.execute("BEGIN")
            row = connection.execute("SELECT * FROM collections WHERE id=?", (collection_id,)).fetchone()
            if row is None:
                raise LookupError("collection not found")
            documents = [self._document(member) for member in connection.execute(
                "SELECT d.* FROM source_documents d JOIN collection_documents cd ON cd.document_id=d.id "
                "WHERE cd.collection_id=? ORDER BY d.id", (collection_id,),
            )]
            if (
                not documents or row["fingerprint"] != expected_fingerprint
                or document_set_fingerprint(documents) != expected_fingerprint
            ):
                raise RuntimeError("collection changed; reload before querying")
            return documents

    def replace_documents(
        self, collection_id: str, document_ids: Sequence[str], expected_fingerprint: str,
    ) -> dict[str, Any]:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM collections WHERE id=?", (collection_id,)).fetchone()
            if row is None:
                raise LookupError("collection not found")
            if row["fingerprint"] != expected_fingerprint:
                raise RuntimeError("collection changed; reload before updating")
            documents = self._sources(connection, document_ids)
            connection.execute("DELETE FROM collection_documents WHERE collection_id=?", (collection_id,))
            connection.executemany(
                "INSERT INTO collection_documents(collection_id,document_id) VALUES (?,?)",
                [(collection_id, document.document_id) for document in documents],
            )
            connection.execute(
                "UPDATE collections SET fingerprint=?,updated_at=? WHERE id=?",
                (document_set_fingerprint(documents), utc_now(), collection_id),
            )
        result = self.get(collection_id)
        if result is None:
            raise RuntimeError("updated collection could not be read")
        return result

    def rename(self, collection_id: str, title: str) -> dict[str, Any]:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE collections SET title=?,updated_at=? WHERE id=?",
                (self._title(title), utc_now(), collection_id),
            )
            if cursor.rowcount != 1:
                raise LookupError("collection not found")
        result = self.get(collection_id)
        if result is None:
            raise LookupError("collection not found")
        return result

    def delete(self, collection_id: str) -> None:
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM collections WHERE id=?", (collection_id,))
            if cursor.rowcount != 1:
                raise LookupError("collection not found")


class ChatRepository:
    """Book-scoped transcript persistence; model history is never constructed here."""

    def __init__(self, database: Database):
        self.database = database

    def list_for_book(self, book_uuid: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM chats WHERE book_id = ? AND deleted_at IS NULL ORDER BY updated_at DESC",
                (book_uuid,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create(self, book_uuid: str, title: str = "New chat", backend: Backend = Backend.ONLINE) -> dict[str, Any]:
        chat_uuid, now = str(uuid4()), utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO chats(id, book_id, title, default_backend, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (chat_uuid, book_uuid, title, backend.value, now, now),
            )
            row = connection.execute("SELECT * FROM chats WHERE id = ?", (chat_uuid,)).fetchone()
        return dict(row)

    def get(self, chat_uuid: str) -> dict[str, Any] | None:
        """Return a live chat together with its immutable book identity/state."""

        with self.database.connect() as connection:
            return _row(connection.execute(
                "SELECT c.*, b.book_id AS retrieval_book_id, b.sha256 AS book_sha256, "
                "b.status AS book_status, b.artifact_path AS book_artifact_path "
                "FROM chats c JOIN books b ON b.id=c.book_id "
                "WHERE c.id=? AND c.deleted_at IS NULL AND b.deleted_at IS NULL",
                (chat_uuid,),
            ).fetchone())

    def update(
        self, chat_uuid: str, *, title: str | None = None, backend: Backend | None = None
    ) -> dict[str, Any] | None:
        """Rename a chat and/or change only its future default provider."""

        if title is None and backend is None:
            return self.get(chat_uuid)
        assignments, values = ["updated_at=?"], [utc_now()]
        if title is not None:
            cleaned = title.strip()
            if not cleaned:
                raise ValueError("chat title must not be empty")
            assignments.append("title=?")
            values.append(cleaned)
        if backend is not None:
            assignments.append("default_backend=?")
            values.append(backend.value)
        values.append(chat_uuid)
        with self.database.connect() as connection:
            connection.execute(
                f"UPDATE chats SET {', '.join(assignments)} WHERE id=? AND deleted_at IS NULL",
                values,
            )
        return self.get(chat_uuid)

    def delete(self, chat_uuid: str) -> dict[str, Any]:
        """Delete one transcript only when no worker can still write into it."""

        with self.database.connect() as connection:
            chat = connection.execute(
                "SELECT * FROM chats WHERE id=? AND deleted_at IS NULL", (chat_uuid,)
            ).fetchone()
            if not chat:
                raise LookupError("chat not found")
            active = connection.execute(
                "SELECT COUNT(*) AS count FROM answer_attempts a JOIN user_messages m "
                "ON m.id=a.message_id WHERE m.chat_id=? AND a.state IN "
                "('queued','retrieving','generating','validating')", (chat_uuid,),
            ).fetchone()["count"]
            if active:
                raise RuntimeError("Stop the active answer before deleting this chat.")
            connection.execute("DELETE FROM chats WHERE id=?", (chat_uuid,))
        return dict(chat)

    def transcript(self, chat_uuid: str) -> dict[str, Any] | None:
        """Return chronological messages and attempts without constructing model history."""

        chat = self.get(chat_uuid)
        if not chat:
            return None
        with self.database.connect() as connection:
            messages = [dict(row) for row in connection.execute(
                "SELECT * FROM user_messages WHERE chat_id=? ORDER BY created_at, id", (chat_uuid,)
            )]
            attempts = [dict(row) for row in connection.execute(
                "SELECT a.* FROM answer_attempts a JOIN user_messages m ON m.id=a.message_id "
                "WHERE m.chat_id=? ORDER BY a.created_at, a.id", (chat_uuid,)
            )]
        by_message: dict[str, list[dict[str, Any]]] = {}
        for attempt in attempts:
            _decode_attempt_json(attempt)
            by_message.setdefault(attempt["message_id"], []).append(attempt)
        for message in messages:
            message["attempts"] = by_message.get(message["id"], [])
        return {"chat": chat, "messages": messages}

    def create_message_attempt(
        self, chat_uuid: str, question: str, backend: Backend | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Atomically bind one exact question and queued attempt to its chat book."""

        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        message_uuid, attempt_uuid, now = str(uuid4()), str(uuid4()), utc_now()
        with self.database.connect() as connection:
            chat = connection.execute(
                "SELECT c.*, b.status AS book_status FROM chats c "
                "JOIN books b ON b.id=c.book_id WHERE c.id=? AND c.deleted_at IS NULL "
                "AND b.deleted_at IS NULL",
                (chat_uuid,),
            ).fetchone()
            if not chat:
                raise LookupError("chat not found")
            if chat["book_status"] != BookStatus.READY.value:
                raise RuntimeError("chat book is not ready")
            selected = backend or Backend(chat["default_backend"])
            connection.execute(
                "INSERT INTO user_messages(id, chat_id, question, created_at) VALUES (?, ?, ?, ?)",
                (message_uuid, chat_uuid, question, now),
            )
            connection.execute(
                "INSERT INTO answer_attempts(id, message_id, backend, state, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (attempt_uuid, message_uuid, selected.value, AttemptState.QUEUED.value, now),
            )
            connection.execute("UPDATE chats SET updated_at=? WHERE id=?", (now, chat_uuid))
            message = dict(connection.execute(
                "SELECT * FROM user_messages WHERE id=?", (message_uuid,)
            ).fetchone())
            attempt = dict(connection.execute(
                "SELECT * FROM answer_attempts WHERE id=?", (attempt_uuid,)
            ).fetchone())
        return message, attempt

    def get_attempt(self, attempt_uuid: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            attempt = _row(connection.execute(
                "SELECT a.*, m.question, m.chat_id, c.book_id, b.book_id AS retrieval_book_id, "
                "b.sha256 AS book_sha256, b.status AS book_status, "
                "b.artifact_path AS book_artifact_path "
                "FROM answer_attempts a JOIN user_messages m ON m.id=a.message_id "
                "JOIN chats c ON c.id=m.chat_id JOIN books b ON b.id=c.book_id WHERE a.id=?",
                (attempt_uuid,),
            ).fetchone())
        if attempt:
            _decode_attempt_json(attempt)
        return attempt

    def set_attempt_state(self, attempt_uuid: str, state: AttemptState) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE answer_attempts SET state=? WHERE id=? AND state NOT IN "
                "('completed','failed','cancelled')",
                (state.value, attempt_uuid),
            )
        return cursor.rowcount == 1

    def interrupt_active_attempts(self) -> None:
        """Make attempts abandoned by a prior process exit terminal and explicit."""

        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE answer_attempts SET state='failed', error_code='application_restarted', "
                "error_message='The application stopped before this answer finished.', "
                "completed_at=? WHERE state IN ('queued','retrieving','generating','validating')",
                (now,),
            )

    def persist_retrieval_snapshot(self, attempt_uuid: str, snapshot: dict[str, Any]) -> str:
        """Persist the immutable snapshot once and advance its attempt to generation."""

        attempt = self.get_attempt(attempt_uuid)
        if not attempt:
            raise LookupError("attempt not found")
        snapshot_uuid, now = str(uuid4()), utc_now()
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM retrieval_snapshots WHERE message_id=?", (attempt["message_id"],)
            ).fetchone()
            if existing:
                snapshot_uuid = existing["id"]
            else:
                connection.execute(
                    "INSERT INTO retrieval_snapshots(id, message_id, book_fingerprint, "
                    "profile_fingerprint, original_query, processed_query, activated_signals_json, "
                    "evidence_json, context_json, diagnostics_json, retrieval_latency_ms, checksum, "
                    "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        snapshot_uuid, attempt["message_id"], snapshot["book_fingerprint"],
                        snapshot["profile_fingerprint"], snapshot["question"],
                        snapshot["processed_query"], _json(snapshot["activated_specialist_signals"]),
                        _json(snapshot["evidence"]), _json(snapshot["assembled_context"]),
                        _json(snapshot["component_diagnostics"]), snapshot["retrieval_latency_ms"],
                        snapshot["checksum"], now,
                    ),
                )
            cursor = connection.execute(
                "UPDATE answer_attempts SET retrieval_snapshot_id=?, state=? WHERE id=? "
                "AND state='retrieving'",
                (snapshot_uuid, AttemptState.GENERATING.value, attempt_uuid),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("attempt is no longer active")
        return snapshot_uuid

    def get_snapshot_for_attempt(self, attempt_uuid: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT s.* FROM retrieval_snapshots s JOIN answer_attempts a "
                "ON a.retrieval_snapshot_id=s.id WHERE a.id=?", (attempt_uuid,)
            ).fetchone()
        return _decode_snapshot(dict(row)) if row else None

    def create_regeneration(self, message_uuid: str, backend: Backend) -> dict[str, Any]:
        """Queue another provider attempt against the existing snapshot byte-for-byte."""

        attempt_uuid, now = str(uuid4()), utc_now()
        with self.database.connect() as connection:
            snapshot = connection.execute(
                "SELECT id FROM retrieval_snapshots WHERE message_id=?", (message_uuid,)
            ).fetchone()
            if not snapshot:
                raise RuntimeError("message does not have a completed retrieval snapshot")
            message = connection.execute(
                "SELECT m.id FROM user_messages m JOIN chats c ON c.id=m.chat_id "
                "JOIN books b ON b.id=c.book_id WHERE m.id=? AND c.deleted_at IS NULL "
                "AND b.deleted_at IS NULL AND b.status='ready'", (message_uuid,),
            ).fetchone()
            if not message:
                raise LookupError("message not found or book is unavailable")
            connection.execute(
                "INSERT INTO answer_attempts(id, message_id, retrieval_snapshot_id, backend, state, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (attempt_uuid, message_uuid, snapshot["id"], backend.value,
                 AttemptState.QUEUED.value, now),
            )
            row = connection.execute(
                "SELECT * FROM answer_attempts WHERE id=?", (attempt_uuid,)
            ).fetchone()
        return dict(row)

    def set_prompt_checksum(self, attempt_uuid: str, checksum: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE answer_attempts SET prompt_checksum=? WHERE id=?", (checksum, attempt_uuid)
            )

    def complete_attempt(
        self,
        attempt_uuid: str,
        *,
        raw_output: str,
        output: dict[str, Any],
        provider_identity: str,
        usage: dict[str, Any],
        timing: dict[str, Any],
        validation: dict[str, Any],
    ) -> bool:
        now = utc_now()
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE answer_attempts SET state='completed', raw_output_text=?, output_json=?, "
                "provider_identity=?, usage_json=?, timing_json=?, validation_json=?, "
                "completed_at=? WHERE id=? AND state='validating'",
                (raw_output, _json(output), provider_identity, _json(usage), _json(timing),
                 _json(validation), now, attempt_uuid),
            )
        return cursor.rowcount == 1

    def fail_attempt(self, attempt_uuid: str, code: str, message: str) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE answer_attempts SET state='failed', error_code=?, error_message=?, "
                "completed_at=? WHERE id=? AND state NOT IN ('completed','cancelled')",
                (code, message, now, attempt_uuid),
            )

    def fail_validation(
        self,
        attempt_uuid: str,
        *,
        raw_output: str,
        provider_identity: str,
        usage: dict[str, Any],
        timing: dict[str, Any],
        validation: dict[str, Any],
    ) -> None:
        """Retain locally useful provider evidence when strict validation fails."""

        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE answer_attempts SET state='failed', raw_output_text=?, provider_identity=?, "
                "usage_json=?, timing_json=?, validation_json=?, "
                "error_code='structured_output_invalid', "
                "error_message='The model response could not be validated against its textbook evidence.', "
                "completed_at=? WHERE id=? AND state='validating'",
                (raw_output, provider_identity, _json(usage), _json(timing), _json(validation),
                 now, attempt_uuid),
            )

    def cancel_attempt(self, attempt_uuid: str) -> bool:
        now = utc_now()
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE answer_attempts SET state='cancelled', error_code='cancelled_by_user', "
                "error_message='Generation was stopped.', completed_at=? WHERE id=? "
                "AND state IN ('queued','retrieving','generating','validating')",
                (now, attempt_uuid),
            )
        return cursor.rowcount == 1


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_attempt_json(attempt: dict[str, Any]) -> None:
    for field in ("output_json", "usage_json", "timing_json", "validation_json"):
        if attempt.get(field):
            attempt[field.removesuffix("_json")] = json.loads(attempt[field])
        attempt.pop(field, None)


def _decode_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    mappings = {
        "activated_signals_json": "activated_specialist_signals",
        "evidence_json": "evidence",
        "context_json": "assembled_context",
        "diagnostics_json": "component_diagnostics",
    }
    for source, target in mappings.items():
        snapshot[target] = json.loads(snapshot.pop(source))
    snapshot["question"] = snapshot["original_query"]
    return snapshot


class ModelSetupRepository:
    """Durable state for explicit, user-triggered model installation jobs."""

    def __init__(self, database: Database):
        self.database = database

    def create(self, component: str) -> dict[str, Any]:
        job_uuid, now = str(uuid4()), utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO model_setup_jobs(id, component, state, stage, created_at, updated_at) "
                "VALUES (?, ?, 'queued', 'queued', ?, ?)",
                (job_uuid, component, now, now),
            )
        return self.get(job_uuid) or {}

    def get(self, job_uuid: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            return _row(connection.execute(
                "SELECT * FROM model_setup_jobs WHERE id=?", (job_uuid,)
            ).fetchone())

    def active(self, component: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            return _row(connection.execute(
                "SELECT * FROM model_setup_jobs WHERE component=? "
                "AND state IN ('queued','running') ORDER BY updated_at DESC LIMIT 1",
                (component,),
            ).fetchone())

    def update(
        self,
        job_uuid: str,
        *,
        state: str,
        stage: str,
        progress: float,
        downloaded_bytes: int = 0,
        total_bytes: int | None = None,
        error_code: str | None = None,
        user_message: str | None = None,
        internal_detail: str | None = None,
        terminal: bool = False,
    ) -> None:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE model_setup_jobs SET state=?, stage=?, progress=?, downloaded_bytes=?, "
                "total_bytes=?, error_code=?, user_message=?, internal_detail=?, updated_at=?, "
                "completed_at=CASE WHEN ? THEN ? ELSE completed_at END WHERE id=?",
                (state, stage, progress, downloaded_bytes, total_bytes, error_code,
                 user_message, internal_detail, now, terminal, now, job_uuid),
            )
