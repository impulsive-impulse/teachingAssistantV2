"""Validate and checksum the immutable Generation Baseline v1 decision."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .generation_benchmark import read_jsonl
from .retrieval_baseline import sha256_file


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config/generation_baseline_v1.json"
DEFAULT_REPORT_DIR = ROOT / "reports/generation_baseline_v1"
EXPECTED_LABELS = [
    "Local Qwen — Gold evidence",
    "GPT-4o API — Gold evidence",
    "Local Qwen — Retrieved evidence",
    "GPT-4o API — Retrieved evidence",
]
EXPECTED_TOP_LEVEL = {
    "schema_version", "baseline", "approval", "frozen_inputs", "shared_pipeline",
    "profiles", "profile_selection", "evaluation_evidence", "recorded_metrics",
    "limitations", "immutability",
}


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Load the generation lock file and reject structural drift immediately."""
    config = json.loads(path.read_text(encoding="utf-8"))
    if set(config) != EXPECTED_TOP_LEVEL:
        missing = sorted(EXPECTED_TOP_LEVEL - set(config))
        extra = sorted(set(config) - EXPECTED_TOP_LEVEL)
        raise ValueError(f"generation baseline fields changed; missing={missing}, extra={extra}")
    if config["schema_version"] != 1:
        raise ValueError("unsupported generation baseline schema")
    baseline = config["baseline"]
    if baseline != {
        "name": "Generation Baseline v1",
        "semantic_version": "1.0.0",
        "frozen": True,
        "approved_on": "2026-07-20",
        "default_profile": "online_quality",
        "offline_fallback_profile": "local_offline",
    }:
        raise ValueError("Generation Baseline v1 identity or frozen profile roles changed")
    if set(config["profiles"]) != {"online_quality", "local_offline"}:
        raise ValueError("Generation Baseline v1 must retain exactly two approved profiles")
    return config


def _identity(root: Path, relative_path: str) -> dict[str, Any]:
    """Return a portable file identity or fail clearly when evidence is missing."""
    path = root / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"required generation baseline artifact is missing: {path}")
    return {
        "path": relative_path.replace("\\", "/"),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def artifact_paths(config: dict[str, Any]) -> list[str]:
    """Enumerate every repository file that constitutes the frozen decision."""
    paths = ["config/generation_baseline_v1.json"]
    paths.extend(item["path"] for item in config["frozen_inputs"].values())
    paths.append(config["approval"]["signoff_path"])
    evidence = config["evaluation_evidence"]
    paths.extend(evidence[key] for key in (
        "comparison_metrics", "comparison_report", "labeled_packet", "labeled_html"
    ))
    paths.extend(evidence["local_results"].values())
    paths.extend(evidence["online_results_in_override_order"])
    # Stable first-seen deduplication keeps manifest order readable.
    return list(dict.fromkeys(path.replace("\\", "/") for path in paths))


def _validate_input_hashes(root: Path, config: dict[str, Any]) -> None:
    """Verify benchmark and upstream configuration hashes before using results."""
    for name, item in config["frozen_inputs"].items():
        actual = sha256_file(root / item["path"])
        if actual != item["sha256"]:
            raise ValueError(
                f"frozen input checksum mismatch for {name}: expected {item['sha256']}, got {actual}"
            )


def _merged_online_results(root: Path, config: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """Reconstruct final online rows using the documented retry override order."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for relative_path in config["evaluation_evidence"]["online_results_in_override_order"]:
        for row in read_jsonl(root / relative_path):
            merged[(row["question_id"], row["evaluation_mode"])] = row
    return merged


def validate_evidence(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Cross-check source rows, metrics, labels, model resolution, and sign-off."""
    _validate_input_hashes(root, config)
    benchmark = read_jsonl(root / config["frozen_inputs"]["generation_benchmark"]["path"])
    expected_questions = config["frozen_inputs"]["generation_benchmark"]["questions"]
    if len(benchmark) != expected_questions:
        raise ValueError(f"expected {expected_questions} generation questions, found {len(benchmark)}")

    evidence = config["evaluation_evidence"]
    metrics = json.loads((root / evidence["comparison_metrics"]).read_text(encoding="utf-8"))
    if metrics["questions_with_all_four_answers"] != expected_questions:
        raise ValueError("comparison no longer contains all four answers for every question")
    for source, frozen in config["recorded_metrics"].items():
        actual = metrics["metrics"][source]
        for field, value in frozen.items():
            if actual[field] != value:
                raise ValueError(f"recorded metric drift: {source}.{field}")
        completion = metrics["completion"][source]
        if completion != {"planned": expected_questions, "completed": expected_questions}:
            raise ValueError(f"incomplete frozen comparison source: {source}")

    packet = read_jsonl(root / evidence["labeled_packet"])
    if len(packet) != expected_questions:
        raise ValueError("labeled packet question count changed")
    for row in packet:
        labels = [answer["label"] for answer in row["answers"]]
        if labels != EXPECTED_LABELS:
            raise ValueError(f"labeled comparison order changed for {row['question_id']}")

    local_counts: dict[str, int] = {}
    for mode, relative_path in evidence["local_results"].items():
        rows = read_jsonl(root / relative_path)
        if len(rows) != expected_questions or any(
            row["status"] != "completed" or f"__{mode}__" not in row["run_id"]
            for row in rows
        ):
            raise ValueError(f"local {mode} result set is incomplete or mixed")
        local_counts[mode] = len(rows)

    online = _merged_online_results(root, config)
    expected_online = expected_questions * 2
    if len(online) != expected_online or any(row["status"] != "completed" for row in online.values()):
        raise ValueError("merged online result set is not 40 questions x 2 completed modes")
    resolved = {row["generation"]["resolved_model"] for row in online.values()}
    expected_model = config["profiles"]["online_quality"]["resolved_and_frozen_model"]
    if resolved != {expected_model}:
        raise ValueError(f"online resolved-model drift: {sorted(resolved)}")

    signoff = json.loads((root / config["approval"]["signoff_path"]).read_text(encoding="utf-8"))
    if signoff["outcome"] != "accepted" or signoff["questions_reviewed"] != expected_questions:
        raise ValueError("human-review acceptance is missing or incomplete")
    if signoff["per_question_rubric_scores_recorded"]:
        raise ValueError("sign-off must not claim per-question scoring that was not performed")
    return {
        "questions": expected_questions,
        "profiles": list(config["profiles"]),
        "local_completed": local_counts,
        "online_completed": len(online),
        "resolved_online_model": expected_model,
        "human_review": signoff["outcome"],
    }


def build_manifest(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Create a portable checksum manifest without invoking retrieval or generation."""
    return {
        "schema_version": 1,
        "baseline": config["baseline"],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "artifacts": [_identity(root, path) for path in artifact_paths(config)],
    }


def verify_manifest(root: Path, manifest_path: Path) -> dict[str, Any]:
    """Recompute every frozen artifact checksum and report exact mismatches."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches = []
    for item in manifest["artifacts"]:
        path = root / item["path"]
        if not path.is_file():
            mismatches.append({"path": item["path"], "error": "missing"})
            continue
        actual = sha256_file(path)
        if actual != item["sha256"]:
            mismatches.append({
                "path": item["path"], "expected": item["sha256"], "actual": actual
            })
    return {
        "artifacts_checked": len(manifest["artifacts"]),
        "mismatches": mismatches,
        "valid": not mismatches,
    }


def main(argv: list[str] | None = None) -> None:
    """Expose manifest generation and zero-call validation as a small CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("manifest", "validate", "checksums"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = load_config(config_path)
    report_dir = root / "reports/generation_baseline_v1"
    manifest_path = report_dir / "manifest.json"
    if args.action == "manifest":
        report_dir.mkdir(parents=True, exist_ok=True)
        manifest = build_manifest(root, config)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"manifest": str(manifest_path), "artifacts": len(manifest["artifacts"])}, indent=2))
        return
    if not manifest_path.is_file():
        raise FileNotFoundError("generation baseline manifest is missing; run the manifest action first")
    checksums = verify_manifest(root, manifest_path)
    if not checksums["valid"]:
        raise ValueError(f"generation baseline checksum mismatch: {checksums['mismatches']}")
    if args.action == "checksums":
        print(json.dumps(checksums, indent=2))
        return
    evidence = validate_evidence(root, config)
    print(json.dumps({"baseline": config["baseline"], "evidence": evidence, "checksums": checksums}, indent=2))


if __name__ == "__main__":
    main()
