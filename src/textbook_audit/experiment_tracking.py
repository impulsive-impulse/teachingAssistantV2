"""Persistent, append-only bookkeeping for the local RAG experiment loop.

The experiment state is intentionally independent of any one retriever.  A
new session can recover completed work from the append-only run log, while the
state and resume documents provide a concise current checkpoint.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EXPERIMENT_DIR = Path("reports/experiments")
STATE_NAME = "experiment_state.json"
RUNS_NAME = "experiment_runs.jsonl"
LEADERBOARD_NAME = "experiment_leaderboard.csv"
DECISIONS_NAME = "experiment_decisions.md"
RESUME_NAME = "RESUME_EXPERIMENT.md"

RUN_REQUIRED_FIELDS = (
    "run_id", "timestamp", "phase", "parent_run_id", "changed_variable",
    "configuration", "random_seed", "input_artifact_versions",
    "model_revisions", "metrics", "latency", "peak_memory",
    "disk_index_size", "candidate_recall", "decision", "concise_reason",
    "output_artifact_paths", "reproduce_command",
)

LEADERBOARD_FIELDS = (
    "run_id", "pipeline_name", "hit_at_1", "hit_at_3", "hit_at_5",
    "mrr", "natural_student_hit_at_5", "canonical_hit_at_5",
    "candidate_recall", "p50_latency_ms", "p95_latency_ms",
    "peak_memory_mb", "decision",
)


def utc_now() -> str:
    """Return a timezone-aware, second-resolution timestamp for run records."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    """Hash an immutable input artifact without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_text(path: Path, content: str) -> None:
    """Replace a mutable checkpoint atomically while preserving UTF-8 text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name, suffix=".tmp",
                                             dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path: Path, value: Any) -> None:
    """Write a deterministic, human-readable JSON checkpoint atomically."""
    _atomic_text(path, json.dumps(value, indent=2, ensure_ascii=False,
                                  sort_keys=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read complete non-empty JSONL records and fail on malformed history."""
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def experiment_paths(root: Path) -> dict[str, Path]:
    """Resolve every persistent experiment artifact beneath the project root."""
    base = root / EXPERIMENT_DIR
    return {
        "base": base,
        "state": base / STATE_NAME,
        "runs": base / RUNS_NAME,
        "leaderboard": base / LEADERBOARD_NAME,
        "decisions": base / DECISIONS_NAME,
        "resume": base / RESUME_NAME,
        "run_directories": base / "runs",
    }


def initialize_experiment(root: Path, approved_plan: list[dict[str, Any]],
                          pending_run_ids: Iterable[str],
                          model_cache_status: dict[str, Any]) -> dict[str, Any]:
    """Create recovery artifacts once and preserve an existing checkpoint.

    Initialization never truncates a run log.  If state already exists, only
    newly planned run IDs are appended to its pending list.
    """
    paths = experiment_paths(root)
    paths["base"].mkdir(parents=True, exist_ok=True)
    paths["run_directories"].mkdir(parents=True, exist_ok=True)
    if paths["state"].is_file():
        state = json.loads(paths["state"].read_text(encoding="utf-8"))
        completed = set(state.get("completed_run_ids", []))
        pending = list(state.get("pending_run_ids", []))
        for run_id in pending_run_ids:
            if run_id not in completed and run_id not in pending:
                pending.append(run_id)
        state["pending_run_ids"] = pending
        state["model_cache_status"] = model_cache_status
    else:
        state = {
            "schema_version": 1,
            "project_objective": "Discover the strongest practical, reproducible local textbook RAG pipeline.",
            "fixed_benchmark_rules": {
                "path": "data/benchmarks/retrieval_benchmark_v1.jsonl",
                "total_rows": 66,
                "answerable_rows": 61,
                "excluded_negative_or_weak_evidence_rows": 5,
                "gold_use": "evaluation only; never candidate construction, scoring, truncation, or reranking",
                "historical_artifacts_immutable": True,
            },
            "current_phase": "Phase A — Candidate preservation and compression",
            "approved_plan": approved_plan,
            "completed_run_ids": [],
            "pending_run_ids": list(pending_run_ids),
            "retained_configurations": [],
            "rejected_configurations": [],
            "failed_or_blocked_runs": [],
            "current_best_configurations": {},
            "exact_next_action": "Run the first pending Phase A candidate-compression configuration.",
            "model_cache_status": model_cache_status,
            "last_successful_checkpoint": None,
            "runtime": {
                "platform": platform.platform(),
                "machine": platform.machine(),
                "python": platform.python_version(),
            },
        }
    write_json(paths["state"], state)
    if not paths["runs"].exists():
        paths["runs"].touch()
    if not paths["decisions"].exists():
        _atomic_text(paths["decisions"], "# Experiment decisions\n\n")
    rebuild_leaderboard(root)
    render_resume(root, state)
    return state


def create_run_directory(root: Path, run_id: str) -> Path:
    """Reserve an empty immutable output directory for exactly one run."""
    destination = experiment_paths(root)["run_directories"] / run_id
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"run output directory already contains artifacts: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def append_run_record(root: Path, record: dict[str, Any]) -> None:
    """Append one validated record while refusing duplicate run identifiers."""
    missing = [field for field in RUN_REQUIRED_FIELDS if field not in record]
    if missing:
        raise ValueError("run record is missing required fields: " + ", ".join(missing))
    path = experiment_paths(root)["runs"]
    existing_ids = {item["run_id"] for item in read_jsonl(path)}
    if record["run_id"] in existing_ids:
        raise ValueError(f'run ID already exists in append-only history: {record["run_id"]}')
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n")


def _leaderboard_value(record: dict[str, Any], *keys: str) -> Any:
    """Read a nested run value without making the leaderboard schema brittle."""
    value: Any = record
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def rebuild_leaderboard(root: Path) -> None:
    """Regenerate the sortable summary from authoritative append-only records."""
    paths = experiment_paths(root)
    rows = []
    for record in read_jsonl(paths["runs"]):
        rows.append({
            "run_id": record["run_id"],
            "pipeline_name": record.get("configuration", {}).get("pipeline_name", record["run_id"]),
            "hit_at_1": _leaderboard_value(record, "metrics", "overall", "hit_at_1"),
            "hit_at_3": _leaderboard_value(record, "metrics", "overall", "hit_at_3"),
            "hit_at_5": _leaderboard_value(record, "metrics", "overall", "hit_at_5"),
            "mrr": _leaderboard_value(record, "metrics", "overall", "mrr"),
            "natural_student_hit_at_5": _leaderboard_value(record, "metrics", "natural_student", "hit_at_5"),
            "canonical_hit_at_5": _leaderboard_value(record, "metrics", "canonical", "hit_at_5"),
            "candidate_recall": _leaderboard_value(record, "candidate_recall", "recall"),
            "p50_latency_ms": _leaderboard_value(record, "latency", "p50_ms"),
            "p95_latency_ms": _leaderboard_value(record, "latency", "p95_ms"),
            "peak_memory_mb": _leaderboard_value(record, "peak_memory", "peak_rss_mb"),
            "decision": record["decision"],
        })
    rows.sort(key=lambda row: (
        -(row["natural_student_hit_at_5"] or -1),
        -(row["hit_at_1"] or -1),
        row["p95_latency_ms"] if row["p95_latency_ms"] is not None else float("inf"),
        row["run_id"],
    ))
    path = paths["leaderboard"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEADERBOARD_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def append_decision(root: Path, record: dict[str, Any], next_action: str) -> None:
    """Append one concise retain/reject/investigate decision to the journal."""
    metrics = record["metrics"]["overall"]
    recall = record["candidate_recall"]
    # Retrieval runs report ranked Hit@K/MRR, while Phase I reports whether the
    # assembled context preserved direct evidence and reviewed answer spans.
    # Keep one shared append-only journal without inventing retrieval metrics
    # for a context-only experiment.
    if "hit_at_1_count" in metrics:
        evidence = (
            f'candidate recall {recall["count"]}/{recall["answerable_questions"]}; '
            f'Hit@1 {metrics["hit_at_1_count"]}/{metrics["answerable_questions"]}; '
            f'Hit@5 {metrics["hit_at_5_count"]}/{metrics["answerable_questions"]}; '
            f'MRR {metrics["mrr"]:.3f}.')
    else:
        evidence = (
            f'inherited candidate recall {recall["count"]}/{recall["answerable_questions"]}; '
            f'direct evidence {metrics["direct_evidence_hit_count"]}/{metrics["questions"]}; '
            f'exact span {metrics["answer_span_retained_count"]}/{metrics["questions"]}; '
            f'average context {metrics["average_context_tokens"]:.0f} tokens.')
    entry = (
        f'## {record["timestamp"]} — {record["run_id"]}\n\n'
        f'- Decision: **{record["decision"]}** — {record["concise_reason"]}\n'
        f'- Evidence: {evidence}\n'
        f'- Next: {next_action}\n\n'
    )
    with experiment_paths(root)["decisions"].open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(entry)


def render_resume(root: Path, state: dict[str, Any]) -> None:
    """Render the compact recovery document from current machine state."""
    completed = state.get("completed_run_ids", [])
    retained = state.get("retained_configurations", [])
    rejected = state.get("rejected_configurations", [])
    best = state.get("current_best_configurations", {})
    unresolved = state.get("unresolved_questions", [])
    lines = [
        "# Resume local RAG experiments", "",
        "## Project objective", "",
        state["project_objective"], "",
        "## Fixed benchmark rules", "",
        "- Use `data/benchmarks/retrieval_benchmark_v1.jsonl`: 66 rows, 61 answerable and 5 excluded negatives.",
        "- Gold evidence is evaluation-only and historical baseline artifacts are immutable.",
        "- Candidate compression must not discard accepted evidence available in source rankings.", "",
        "## Current phase", "", state["current_phase"], "",
        "## Current best pipeline", "",
        (json.dumps(best, ensure_ascii=False) if best else "No experiment winner retained yet."), "",
        "## Completed experiments", "",
        *(f"- `{run_id}`" for run_id in completed),
        *( ["- None yet."] if not completed else []), "",
        "## Retained directions", "",
        *(f"- `{item}`" for item in retained),
        *( ["- None yet."] if not retained else []), "",
        "## Rejected directions", "",
        *(f"- `{item}`" for item in rejected),
        *( ["- None yet."] if not rejected else []), "",
        "## Unresolved questions", "",
        *(f"- {question}" for question in unresolved),
        *( ["- None recorded."] if not unresolved else []), "",
        "## Exact next command or task", "", state["exact_next_action"], "",
        "## Warnings and invariants", "",
        "- Do not modify the benchmark, reviewed gold, historical reports, or previous baseline outputs.",
        "- Gold evidence is evaluation-only; never use it to build, score, truncate, or rerank candidates.",
        "- Use successive narrowing and do not introduce unapproved models or uncontrolled configuration grids.",
        "- Resume from the append-only run log; never overwrite a completed run directory.", "",
    ]
    _atomic_text(experiment_paths(root)["resume"], "\n".join(lines))


def checkpoint_run(root: Path, record: dict[str, Any], next_action: str,
                   current_best: dict[str, Any] | None = None) -> dict[str, Any]:
    """Commit one completed run to history, state, leaderboard, and recovery docs."""
    append_run_record(root, record)
    paths = experiment_paths(root)
    state = json.loads(paths["state"].read_text(encoding="utf-8"))
    run_id = record["run_id"]
    if run_id not in state["completed_run_ids"]:
        state["completed_run_ids"].append(run_id)
    state["pending_run_ids"] = [item for item in state["pending_run_ids"] if item != run_id]
    config_name = record["configuration"].get("pipeline_name", run_id)
    if record["decision"] == "retain" and config_name not in state["retained_configurations"]:
        state["retained_configurations"].append(config_name)
    if record["decision"] == "reject" and config_name not in state["rejected_configurations"]:
        state["rejected_configurations"].append(config_name)
    if current_best is not None:
        state["current_best_configurations"] = current_best
    state["exact_next_action"] = next_action
    state["last_successful_checkpoint"] = {
        "run_id": run_id, "timestamp": record["timestamp"],
        "output_artifact_paths": record["output_artifact_paths"],
    }
    write_json(paths["state"], state)
    rebuild_leaderboard(root)
    append_decision(root, record, next_action)
    render_resume(root, state)
    return state
