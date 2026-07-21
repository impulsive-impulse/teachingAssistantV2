"""Small, explicit SQLite persistence layer with forward-only migrations.

SQLite is accessed through the standard library.  Every service operation gets
its own connection, which avoids sharing connection objects across FastAPI's
worker threads and ingestion workers.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


SCHEMA_VERSION = 3

MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE books (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL UNIQUE,
    original_filename TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    status_reason TEXT,
    page_count INTEGER,
    searchable_page_count INTEGER,
    chapter_count INTEGER,
    source_path TEXT,
    artifact_path TEXT,
    ingestion_policy_version TEXT NOT NULL,
    runtime_profile_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    indexed_at TEXT,
    last_opened_at TEXT,
    deleted_at TEXT
);
CREATE INDEX idx_books_status ON books(status);
CREATE INDEX idx_books_last_opened ON books(last_opened_at DESC);

CREATE TABLE ingestion_jobs (
    id TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    book_id TEXT REFERENCES books(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    stage_progress REAL NOT NULL DEFAULT 0,
    overall_progress REAL NOT NULL DEFAULT 0,
    state TEXT NOT NULL,
    error_code TEXT,
    user_message TEXT,
    internal_detail TEXT,
    started_at TEXT,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX idx_ingestion_jobs_checksum ON ingestion_jobs(checksum);
CREATE INDEX idx_ingestion_jobs_state ON ingestion_jobs(state);

CREATE TABLE chats (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    default_backend TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE INDEX idx_chats_book ON chats(book_id, updated_at DESC);

CREATE TABLE user_messages (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_messages_chat ON user_messages(chat_id, created_at);

CREATE TABLE retrieval_snapshots (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL UNIQUE REFERENCES user_messages(id) ON DELETE CASCADE,
    book_fingerprint TEXT NOT NULL,
    profile_fingerprint TEXT NOT NULL,
    original_query TEXT NOT NULL,
    processed_query TEXT NOT NULL,
    activated_signals_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    context_json TEXT NOT NULL,
    diagnostics_json TEXT NOT NULL,
    retrieval_latency_ms REAL NOT NULL,
    checksum TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE answer_attempts (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES user_messages(id) ON DELETE CASCADE,
    retrieval_snapshot_id TEXT REFERENCES retrieval_snapshots(id) ON DELETE CASCADE,
    backend TEXT NOT NULL,
    state TEXT NOT NULL,
    output_json TEXT,
    provider_identity TEXT,
    usage_json TEXT,
    timing_json TEXT,
    validation_json TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX idx_attempts_message ON answer_attempts(message_id, created_at);
CREATE UNIQUE INDEX idx_one_active_attempt_per_message
    ON answer_attempts(message_id)
    WHERE state IN ('queued', 'retrieving', 'generating', 'validating');
"""

MIGRATION_2 = """
CREATE TABLE model_setup_jobs (
    id TEXT PRIMARY KEY,
    component TEXT NOT NULL,
    state TEXT NOT NULL,
    stage TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER,
    error_code TEXT,
    user_message TEXT,
    internal_detail TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX idx_model_setup_component_state
    ON model_setup_jobs(component, state, updated_at DESC);
"""

MIGRATION_3 = """
ALTER TABLE answer_attempts ADD COLUMN prompt_checksum TEXT;
ALTER TABLE answer_attempts ADD COLUMN raw_output_text TEXT;
"""


class Database:
    """Own schema initialization and transaction-scoped connections."""

    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        """Create the database and apply each missing migration atomically."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            versions = {
                row["version"]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            if 1 not in versions:
                connection.executescript(MIGRATION_1)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
                )
            if 2 not in versions:
                connection.executescript(MIGRATION_2)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (2, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
                )
            if 3 not in versions:
                connection.executescript(MIGRATION_3)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) "
                    "VALUES (3, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
                )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection and commit or roll back its transaction."""

        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
