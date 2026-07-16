"""Build, evaluate, checksum, and validate frozen Retrieval Baseline v1 artifacts."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from .embedding_bakeoff import (_evaluation_scopes, _snapshot_path,
                                accepted_mapping, searchable_pages, summarize)
from .retrieval import read_jsonl
from .retrieval_baseline import (DEFAULT_CONFIG, RetrievalBaseline, load_config,
                                 sha256_file)


REPORT_DIR = Path("reports/retrieval_baseline_v1")
GOLDEN_FIXTURE = Path("tests/fixtures/retrieval_baseline_v1_golden.json")
WINNING_METRICS = Path(
    "reports/experiments/runs/phase_h_h3_combined_specialist_priors/metrics.json")
RUN_LEDGER = Path("reports/experiments/experiment_runs.jsonl")


def _relative(root: Path, path: Path) -> str:
    """Prefer portable repository-relative paths, retaining external paths."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _artifact_identity(root: Path, relative_path: str) -> dict[str, Any]:
    """Describe one required file with a portable path, size, and checksum."""
    path = root / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"required baseline artifact is missing: {path}")
    return {"path": _relative(root, path), "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path)}


def _directory_identity(path: Path) -> dict[str, Any]:
    """Hash a directory from ordered relative names and each file checksum."""
    import hashlib
    files = sorted(item for item in path.rglob("*") if item.is_file())
    digest = hashlib.sha256()
    total = 0
    for item in files:
        relative = item.relative_to(path).as_posix()
        size = item.stat().st_size
        total += size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(item).encode("ascii"))
        digest.update(b"\n")
    return {"path": str(path.resolve()), "file_count": len(files),
            "size_bytes": total, "identity_sha256": digest.hexdigest()}


def _git_metadata(root: Path) -> dict[str, Any]:
    """Capture the exact repository commit and whether freeze files are dirty."""
    def command(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    return {"commit": command("rev-parse", "HEAD"),
            "branch": command("branch", "--show-current"),
            "working_tree_dirty": bool(command("status", "--porcelain"))}


def _dependency_versions() -> dict[str, str]:
    """Record versions that affect extraction, ranking, and serialization."""
    names = ("numpy", "pypdf", "psutil", "PyYAML", "sentence-transformers",
             "transformers", "torch")
    return {name: importlib.metadata.version(name) for name in names}


def baseline_commands() -> dict[str, str]:
    """Return the small canonical command set recorded in docs and manifest."""
    python = "temp\\python-x64\\python.exe"
    manager = f"{python} scripts\\manage_retrieval_baseline_v1.py"
    return {
        "prepare_corpus": f"{python} scripts\\audit_textbooks.py",
        "build_or_reuse_indexes": f"{manager} build",
        "validate_baseline": f"{manager} validate",
        "full_benchmark_evaluation": f"{manager} evaluate",
        "query_one_book": (f'{python} scripts\\query_final_pipeline.py "How do plants eat?" '
                           "--book-id biology --include-text"),
        "rebuild_indexes_from_scratch": f"{manager} build --force-rebuild",
        "verify_checksums": f"{manager} checksums",
    }


def build_manifest(root: Path, config: dict[str, Any], runtime: RetrievalBaseline | None = None) -> dict[str, Any]:
    """Create the complete v1 provenance manifest from files and runtime state."""
    embedding = config["embedding"]
    snapshot = _snapshot_path(root / "data/retrieval/cache/models",
                              embedding["model_name"], embedding["revision"])
    indexes = []
    for path in config["indexes"]["chunk_embeddings"].values():
        indexes.append(_artifact_identity(root, path))
    template = config["indexes"]["specialist_filename_template"]
    for branch in ("formula", "table", "visual"):
        method = config["specialists"][branch]["method"]
        for book in config["inputs"]["supported_books"]:
            path = Path(config["indexes"]["specialist_directory"]) / template.format(
                method=method, book_id=book)
            indexes.append(_artifact_identity(root, path.as_posix()))
    config_path = Path(config["_config_path"])
    return {
        "schema_version": 1,
        "baseline": {**config["baseline"]},
        "winning_experiment_run_id": config["baseline"]["source_winning_run_id"],
        "git": _git_metadata(root),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtime": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                    "operating_system": platform.platform(), "machine": platform.machine()},
        "dependencies": _dependency_versions(),
        "model": {"name": embedding["model_name"], "resolved_revision": embedding["revision"],
                  "dimensions": embedding["dimensions"], "runtime_device": (
                      runtime.loaded.metadata["device"] if runtime else embedding["device_policy"]["default"]),
                  "cache_identity": _directory_identity(snapshot)},
        "source_pdfs": {book: _artifact_identity(root, path)
                        for book, path in config["inputs"]["source_pdfs"].items()},
        "processed_corpus_artifacts": {book: _artifact_identity(root, path)
                                       for book, path in config["inputs"]["processed_pages"].items()},
        "index_artifacts": indexes,
        "configuration": {"path": _relative(root, config_path),
                          "sha256": sha256_file(config_path)},
        "benchmark": _artifact_identity(root, config["inputs"]["benchmark"]),
        "commands": baseline_commands(),
    }


def evaluate_runtime(root: Path, runtime: RetrievalBaseline) -> dict[str, Any]:
    """Evaluate complete rankings after gold-blind retrieval has finished."""
    config = runtime.config
    questions = read_jsonl(root / config["inputs"]["benchmark"])
    pages = searchable_pages(root)
    answerable = {q["question_id"] for q in questions
                  if q.get("gold_pdf_pages") and (q.get("gold_answer_span") or "").strip()}
    scopes = _evaluation_scopes(questions, answerable)
    rows: dict[str, dict[str, Any]] = {}
    for question in questions:
        qid, book = question["question_id"], question["book_id"]
        corpus = runtime.chunks[book]
        mapping = accepted_mapping(question, corpus, pages[book])
        gold = set(mapping["primary"] + mapping["alternatives"])
        ranked = runtime._rank(question["question"], book)
        first = next((rank for rank, index in enumerate(ranked["ranking"], 1)
                      if corpus[int(index)]["chunk_id"] in gold), None)
        rows[qid] = {"answerable": qid in answerable, "first_gold_rank": first,
                     "latency_ms": float(ranked["latency_ms"])}
    metrics = summarize(rows, scopes)
    metrics["environment"] = {
        "measurement": "fresh clean-command validation; model/index load excluded from query latency",
        "peak_rss_mb": psutil.Process(os.getpid()).memory_info().peak_wset / (1024 * 1024)
        if hasattr(psutil.Process(os.getpid()).memory_info(), "peak_wset") else
        psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024),
        "python": platform.python_version(), "platform": platform.platform(),
        "device": runtime.loaded.metadata["device"],
    }
    return metrics


def _winning_record(root: Path) -> dict[str, Any]:
    """Read the immutable winning ledger row used for timing and memory."""
    rows = read_jsonl(root / RUN_LEDGER)
    return next(row for row in rows
                if row["run_id"] == "phase_h_h3_combined_specialist_priors")


def frozen_metrics(root: Path, fresh: dict[str, Any] | None = None) -> dict[str, Any]:
    """Preserve full original slices and keep fresh environment metrics separate."""
    original = json.loads((root / WINNING_METRICS).read_text(encoding="utf-8"))["metrics"]
    record = _winning_record(root)
    return {
        "schema_version": 1, "baseline_version": "1.0.0",
        "winning_experiment_run_id": "phase_h_h3_combined_specialist_priors",
        "original_selected_run": {
            "metrics": original, "latency": record["latency"],
            "peak_memory": record["peak_memory"],
            "environment_sensitive": ["latency", "peak_memory"],
        },
        "fresh_validation": fresh,
    }


def validate_golden(root: Path, runtime: RetrievalBaseline,
                    repeat: int = 2) -> dict[str, Any]:
    """Check stable fixture expectations and repeat-run ordering determinism."""
    fixture = json.loads((root / GOLDEN_FIXTURE).read_text(encoding="utf-8"))
    failures = []
    stable_outputs: dict[str, list[str]] = {}
    for case in fixture["cases"]:
        signatures = []
        for _ in range(repeat):
            result = runtime.retrieve(case["question"], case["book_id"], include_text=False).to_dict()
            ids = [item["evidence_id"] for item in result["evidence"]]
            signatures.append(ids)
            if not set(case["expected_evidence_ids_in_top_five"]).intersection(ids):
                failures.append(f"{case['question_id']}: expected evidence absent")
            if result["activated_specialist_signals"] != case["expected_activated_specialists"]:
                failures.append(f"{case['question_id']}: specialist activation differs")
            missing = set(fixture["required_evidence_fields"]) - set(result["evidence"][0])
            if missing:
                failures.append(f"{case['question_id']}: metadata missing {sorted(missing)}")
        if any(signature != signatures[0] for signature in signatures[1:]):
            failures.append(f"{case['question_id']}: repeat ordering differs")
        stable_outputs[case["question_id"]] = signatures[0]
    if failures:
        raise AssertionError("; ".join(failures))
    return {"cases": len(fixture["cases"]), "repeats": repeat,
            "deterministic": True, "top_five": stable_outputs}


def verify_manifest(root: Path, manifest_path: Path) -> dict[str, Any]:
    """Recompute every repository artifact checksum recorded by the manifest."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = (list(manifest["source_pdfs"].values())
                 + list(manifest["processed_corpus_artifacts"].values())
                 + manifest["index_artifacts"] + [manifest["benchmark"]])
    artifacts.append({"path": manifest["configuration"]["path"],
                      "sha256": manifest["configuration"]["sha256"]})
    mismatches = []
    for artifact in artifacts:
        path = root / artifact["path"]
        actual = sha256_file(path) if path.is_file() else None
        if actual != artifact["sha256"]:
            mismatches.append({"path": artifact["path"], "expected": artifact["sha256"],
                               "actual": actual})
    if mismatches:
        raise AssertionError(f"baseline checksum mismatches: {mismatches}")
    return {"verified_artifacts": len(artifacts), "mismatches": []}


def _clear_indexes(root: Path, config: dict[str, Any]) -> None:
    """Delete only v1's named cache files after validating their cache location."""
    cache_root = (root / "data/retrieval/cache").resolve()
    paths = [root / path for path in config["indexes"]["chunk_embeddings"].values()]
    template = config["indexes"]["specialist_filename_template"]
    for branch in ("formula", "table", "visual"):
        method = config["specialists"][branch]["method"]
        for book in config["inputs"]["supported_books"]:
            paths.append(root / config["indexes"]["specialist_directory"] /
                         template.format(method=method, book_id=book))
    for path in paths:
        resolved = path.resolve()
        if cache_root not in resolved.parents:
            raise ValueError(f"refusing to remove index outside cache: {resolved}")
        if resolved.is_file():
            resolved.unlink()


def main(argv: list[str] | None = None) -> None:
    """Provide canonical build, evaluation, validation, and checksum commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "evaluate", "validate", "manifest", "checksums"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--device")
    parser.add_argument("--force-rebuild", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    config = load_config(args.config, root)
    report = root / REPORT_DIR
    report.mkdir(parents=True, exist_ok=True)
    if args.action == "checksums":
        print(json.dumps(verify_manifest(root, report / "manifest.json"), indent=2))
        return
    if args.force_rebuild:
        if args.action != "build":
            raise ValueError("--force-rebuild is valid only with the build action")
        _clear_indexes(root, config)
    runtime = RetrievalBaseline(root, config, args.device)
    if args.action == "build":
        print(json.dumps({"status": "ready", "chunk_indexes": runtime.chunk_index,
                          "specialist_indexes": runtime.specialist_indexes}, indent=2))
        return
    fresh = evaluate_runtime(root, runtime) if args.action in {"evaluate", "validate"} else None
    if fresh is not None:
        (report / "metrics.json").write_text(
            json.dumps(frozen_metrics(root, fresh), indent=2) + "\n", encoding="utf-8")
    golden = validate_golden(root, runtime) if args.action == "validate" else None
    manifest = build_manifest(root, config, runtime)
    (report / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    result = {"action": args.action, "fresh_metrics": fresh,
              "golden_regression": golden, "manifest": "reports/retrieval_baseline_v1/manifest.json"}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
