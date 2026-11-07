"""Crash-safe attempted-call accounting shared by evaluation and collection queries."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from .assessment_protocol import fingerprint


PHASE_LIMITS = {"development": 60, "final_evaluation": 180, "fresh_final_rerun": 180, "contingency": 80}
MAXIMUM_ATTEMPTS = 500


class BudgetExceeded(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class CallLedger:
    def __init__(self, path: Path, protocol_sha256: str):
        if not isinstance(protocol_sha256, str) or len(protocol_sha256) != 64:
            raise ValueError("call accounting requires a protocol fingerprint")
        self.path, self.protocol_sha256 = path.resolve(), protocol_sha256
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS approval (
                    id INTEGER PRIMARY KEY CHECK(id=1), protocol_sha256 TEXT NOT NULL,
                    maximum_attempts INTEGER NOT NULL, phases_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, phase TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL, state TEXT NOT NULL,
                    created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT,
                    error_code TEXT, result_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_attempt_request ON attempts(run_id,request_sha256,state);
            """)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM approval WHERE id=1").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO approval(id,protocol_sha256,maximum_attempts,phases_json) VALUES (1,?,?,?)",
                    (protocol_sha256, MAXIMUM_ATTEMPTS, json.dumps(PHASE_LIMITS, sort_keys=True)),
                )
            elif (
                row["protocol_sha256"] != protocol_sha256 or row["maximum_attempts"] != MAXIMUM_ATTEMPTS
                or json.loads(row["phases_json"]) != PHASE_LIMITS
            ):
                raise ValueError("existing ledger belongs to another protocol or approval; it cannot be reset")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def reserve(self, run_id: str, phase: str, request_sha256: str) -> str:
        if (
            not isinstance(run_id, str) or not run_id
            or not isinstance(request_sha256, str) or len(request_sha256) != 64
            or not isinstance(phase, str) or phase not in PHASE_LIMITS
        ):
            raise ValueError("paid dispatch requires an explicit run, phase and request fingerprint")
        attempt_id = str(uuid4())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            total = connection.execute("SELECT COUNT(*) AS n FROM attempts").fetchone()["n"]
            phase_count = connection.execute("SELECT COUNT(*) AS n FROM attempts WHERE phase=?", (phase,)).fetchone()["n"]
            if total >= MAXIMUM_ATTEMPTS or phase_count >= PHASE_LIMITS[phase]:
                raise BudgetExceeded("attempt limit reached; final/rerun reservations cannot be consumed")
            connection.execute(
                "INSERT INTO attempts(id,run_id,phase,request_sha256,state,created_at) VALUES (?,?,?,?, 'reserved',?)",
                (attempt_id, run_id, phase, request_sha256, _now()),
            )
        return attempt_id

    def start(self, attempt_id: str) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE attempts SET state='started',started_at=? WHERE id=? AND state='reserved'",
                (_now(), attempt_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("attempt was already dispatched or is unavailable")

    def finish(self, attempt_id: str, result: dict[str, Any], *, error_code: str | None = None) -> None:
        with self.connect() as connection:
            allowed = ("reserved", "started") if error_code else ("started",)
            placeholders = ",".join("?" for _state in allowed)
            cursor = connection.execute(
                "UPDATE attempts SET state=?,completed_at=?,error_code=?,result_json=? "
                f"WHERE id=? AND state IN ({placeholders})",
                ("failed" if error_code else "completed", _now(), error_code,
                 json.dumps(result, ensure_ascii=False, sort_keys=True), attempt_id, *allowed),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("attempt result cannot be overwritten")

    def cached(self, run_id: str, request_sha256: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id,result_json FROM attempts WHERE run_id=? AND request_sha256=? "
                "AND state='completed' ORDER BY created_at,id LIMIT 1",
                (run_id, request_sha256),
            ).fetchone()
        return {"attempt_id": row["id"], "result": json.loads(row["result_json"])} if row else None

    def status(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute("SELECT phase,state,started_at FROM attempts").fetchall()
        counts = {phase: sum(row["phase"] == phase for row in rows) for phase in PHASE_LIMITS}
        return {
            "maximum_attempts": MAXIMUM_ATTEMPTS, "reserved_or_attempted": len(rows),
            "remaining": MAXIMUM_ATTEMPTS - len(rows),
            "dispatched_upper_bound": sum(row["started_at"] is not None for row in rows),
            "phase_counts": counts,
            "phase_remaining": {phase: PHASE_LIMITS[phase] - counts[phase] for phase in PHASE_LIMITS},
            "failed": sum(row["state"] == "failed" for row in rows),
            "unfinished": sum(row["state"] in {"reserved", "started"} for row in rows),
        }


def request_fingerprint(prompt_package: dict[str, Any], model: str, max_output_tokens: int) -> str:
    return fingerprint({
        "prompt": prompt_package["prompt"], "schema": prompt_package["schema"],
        "context_checksum": prompt_package["context_checksum"],
        "model": model, "temperature": 0, "max_output_tokens": max_output_tokens,
    })
