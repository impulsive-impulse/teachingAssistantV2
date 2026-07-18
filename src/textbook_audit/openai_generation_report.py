"""Build local-vs-OpenAI metrics and a blinded four-answer review packet."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from textbook_audit.generation_benchmark import read_jsonl
from textbook_audit.generation_experiments import (
    ROOT,
    load_experiment_config,
    summarize,
    utc_now,
    write_json_atomic,
    write_jsonl_atomic,
)
from textbook_audit.openai_generation import DEFAULT_CONFIG, load_online_config


# Ad-hoc rebuilds go to a clearly named scratch comparison. Reviewed snapshots
# live beside it under ``comparisons/<stage_name>`` and are never overwritten.
DEFAULT_OUTPUT = ROOT / "reports/openai_generation_experiments/comparisons/latest"
SOURCE_LABELS = {
    "local_gold": "Local Qwen — Gold evidence",
    "openai_gold": "GPT-4o API — Gold evidence",
    "local_retrieved": "Local Qwen — Retrieved evidence",
    "openai_retrieved": "GPT-4o API — Retrieved evidence",
}


def _answer_view(result: dict[str, Any]) -> dict[str, Any]:
    """Project a run result into the existing human-review answer shape."""
    parsed = result["parsed_output"]
    return {
        "evaluation_mode": result.get("evaluation_mode"),
        "supplied_evidence": result["supplied_evidence"],
        "answer": parsed.get("answer", ""),
        "citations": parsed.get("citations", []),
        "automatic_screen": result["evaluation"],
        "reviewer_decision": None,
        "reviewer_notes": "",
    }


def _source_rows(
    online_results: list[dict[str, Any]], config: dict[str, Any], root: Path
) -> dict[str, dict[str, dict[str, Any]]]:
    """Index the two online and two frozen-local answer sources by question."""
    sources: dict[str, dict[str, dict[str, Any]]] = {
        "local_gold": {}, "local_retrieved": {},
        "openai_gold": {}, "openai_retrieved": {},
    }
    question_ids = {row["question_id"] for row in online_results}
    for mode in ("gold", "retrieved"):
        local_rows = read_jsonl(root / config["local_comparison_runs"][mode])
        sources[f"local_{mode}"] = {
            row["question_id"]: row for row in local_rows if row["question_id"] in question_ids
        }
    for row in online_results:
        sources[f"openai_{row['evaluation_mode']}"][row["question_id"]] = row
    return sources


def build_review_packet(
    benchmark_rows: list[dict[str, Any]], sources: dict[str, dict[str, dict[str, Any]]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create deterministic per-question blind labels and a separate answer key."""
    # Fixed source keys are shuffled per question by hashing, keeping labels
    # reproducible while preventing a reviewer from learning one global order.
    packet: list[dict[str, Any]] = []
    answer_key: dict[str, Any] = {"schema_version": 1, "questions": {}}
    by_id = {row["question_id"]: row for row in benchmark_rows}
    # Human comparison is meaningful only when all four providers/modes
    # produced a complete answer. Truncated online rows remain in metrics but
    # are omitted from the blinded answer-quality packet.
    complete_ids = [
        {question_id for question_id, result in rows.items()
         if result.get("status") == "completed"}
        for rows in sources.values()
    ]
    common_ids = set.intersection(*complete_ids)
    for question_id in sorted(common_ids):
        row = by_id[question_id]
        ordered = sorted(sources, key=lambda key: hashlib.sha256(
            f"{question_id}:{key}".encode("utf-8")
        ).hexdigest())
        answers = []
        key_entry: dict[str, str] = {}
        for index, source_key in enumerate(ordered):
            label = f"Answer {chr(ord('A') + index)}"
            answers.append({"label": label, **_answer_view(sources[source_key][question_id])})
            key_entry[label] = source_key
        packet.append({
            "question_id": question_id,
            "question": row["normalized_question"],
            "required_answer_points": row["required_answer_points"],
            "optional_answer_points": row["optional_answer_points"],
            "prohibited_or_unsupported_claims": row["prohibited_or_unsupported_claims"],
            "answers": answers,
        })
        answer_key["questions"][question_id] = key_entry
    return packet, answer_key


def build_labeled_packet(
    benchmark_rows: list[dict[str, Any]], sources: dict[str, dict[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Create a fixed-order packet with explicit provider and evidence labels."""
    by_id = {row["question_id"]: row for row in benchmark_rows}
    complete_ids = [
        {question_id for question_id, result in rows.items()
         if result.get("status") == "completed"}
        for rows in sources.values()
    ]
    common_ids = set.intersection(*complete_ids)
    packet: list[dict[str, Any]] = []
    for question_id in sorted(common_ids):
        benchmark = by_id[question_id]
        answers = [
            {"label": SOURCE_LABELS[source], **_answer_view(sources[source][question_id])}
            for source in SOURCE_LABELS
        ]
        packet.append({
            "question_id": question_id,
            "question": benchmark["normalized_question"],
            "required_answer_points": benchmark["required_answer_points"],
            "optional_answer_points": benchmark["optional_answer_points"],
            "prohibited_or_unsupported_claims": benchmark["prohibited_or_unsupported_claims"],
            "answers": answers,
        })
    return packet


def build_comparison(
    *, online_results_paths: list[Path], config_path: Path, output_dir: Path, root: Path = ROOT
) -> dict[str, Any]:
    """Write metrics/review artifacts, with later files overriding earlier rows."""
    config = load_online_config(config_path)
    local_config = load_experiment_config(root / config["local_experiment_config"])
    benchmark = read_jsonl(root / local_config["frozen_inputs"]["generation_benchmark"])
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for path in online_results_paths:
        for result in read_jsonl(path):
            merged[(result["question_id"], result["evaluation_mode"])] = result
    online_results = list(merged.values())
    sources = _source_rows(online_results, config, root)
    packet, answer_key = build_review_packet(benchmark, sources)
    labeled_packet = build_labeled_packet(benchmark, sources)
    paired_ids = {row["question_id"] for row in packet}
    completion = {
        source: {
            "planned": len(rows),
            "completed": sum(row.get("status") == "completed" for row in rows.values()),
        }
        for source, rows in sources.items()
    }
    # Quality comparisons use the exact same question IDs for every source.
    # Completion counts remain separate so provider truncation is still clear.
    metrics = {
        source: summarize([row for question_id, row in rows.items() if question_id in paired_ids], None)
        for source, rows in sources.items()
    }
    summary = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "online_results": [str(path) for path in online_results_paths],
        "questions_with_all_four_answers": len(packet),
        "completion": completion,
        "metrics": metrics,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_dir / "comparison_metrics.json", summary)
    write_jsonl_atomic(output_dir / "blinded_human_review_packet.jsonl", packet)
    write_jsonl_atomic(output_dir / "labeled_comparison_packet.jsonl", labeled_packet)
    write_json_atomic(output_dir / "blinded_answer_key.json", answer_key)
    lines = [
        "# Local vs OpenAI generation comparison", "",
        f"Questions with all four answers: **{len(packet)}**", "",
        "| Source | Completed / planned | Paired questions | Required-point coverage | Citation validity | Unsupported-claim rate | P95 latency (s) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for source, value in metrics.items():
        lines.append(
            f"| {source} | {completion[source]['completed']} / {completion[source]['planned']} | "
            f"{value['completed']} | {value['required_point_coverage']:.4f} | "
            f"{value['citation_validity']:.4f} | {value['unsupported_claim_rate']:.4f} | "
            f"{value['p95_latency_seconds'] if value['p95_latency_seconds'] is not None else 'n/a'} |"
        )
    lines.extend([
        "", "Automatic token-overlap metrics are screening signals, not the final quality judgment.",
        "Use the blinded packet for unbiased scoring, or the labeled packet and revealed HTML for direct",
        "local-Qwen versus GPT-4o gap analysis. Review scientific correctness, completeness, grounding,",
        "and clarity manually in either workflow.",
    ])
    (output_dir / "comparison_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    """Create the report CLI used only after an online run has completed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--online-results", type=Path, nargs="+", required=True,
        help="Base results followed by optional supplemental/retry results.",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Build comparison artifacts without making any model calls."""
    args = build_parser().parse_args(argv)
    result = build_comparison(
        online_results_paths=[path.resolve() for path in args.online_results],
        config_path=args.config.resolve(),
        output_dir=args.output_dir.resolve(),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
