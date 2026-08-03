"""Build a deterministic blinded human-review packet for comparison finalists."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from textbook_audit.generation_benchmark import read_jsonl
from textbook_audit.generation_phase_a import ROOT, write_json_atomic, write_jsonl_atomic


EXPERIMENT_DIR = ROOT / "reports/local_model_comparison_v1"


def load_run(experiment_dir: Path, run_id: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    run_dir = experiment_dir / "runs" / run_id
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    results = {
        row["question_id"]: row for row in read_jsonl(run_dir / "results.jsonl")
    }
    return manifest, results


def build_packet(
    benchmark: list[dict[str, Any]],
    runs: list[tuple[dict[str, Any], dict[str, dict[str, Any]]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Blind labels independently per question to prevent order learning."""

    if len(runs) < 2:
        raise ValueError("human review requires at least two comparison runs")
    stages = {manifest["stage"] for manifest, _ in runs}
    if len(stages) != 1:
        raise ValueError("all blinded runs must use the same benchmark stage")
    common_ids = set.intersection(
        *[
            {
                question_id
                for question_id, result in results.items()
                if result.get("status") == "completed"
            }
            for _, results in runs
        ]
    )
    benchmark_by_id = {row["question_id"]: row for row in benchmark}
    packet: list[dict[str, Any]] = []
    answer_key: dict[str, Any] = {
        "schema_version": 1,
        "stage": next(iter(stages)),
        "questions": {},
    }
    for question_id in sorted(common_ids):
        benchmark_row = benchmark_by_id[question_id]
        ordered = sorted(
            runs,
            key=lambda run: hashlib.sha256(
                f"{question_id}:{run[0]['run_id']}".encode("utf-8")
            ).hexdigest(),
        )
        first_result = ordered[0][1][question_id]
        context_hashes = {
            results[question_id]["context_sha256"] for _, results in ordered
        }
        if len(context_hashes) != 1:
            raise ValueError(f"{question_id}: finalists did not receive identical evidence")
        answers = []
        key_entry: dict[str, Any] = {}
        for index, (manifest, results) in enumerate(ordered):
            label = f"Answer {chr(ord('A') + index)}"
            result = results[question_id]
            answers.append(
                {
                    "label": label,
                    "answer": result["parsed_output"].get("answer", ""),
                    "status": result["parsed_output"].get("status"),
                    "selected_evidence_ids": result["parsed_output"].get(
                        "selected_evidence_ids", []
                    ),
                    "citations": result["parsed_output"].get("citations", []),
                    "review": {
                        "required_point_coverage_0_to_4": None,
                        "overall_quality_1_to_5": None,
                        "citation_support_0_to_2": None,
                        "unsupported_claims_count": None,
                        "formula_accuracy_0_to_2_or_na": None,
                        "multi_passage_completeness_0_to_2_or_na": None,
                        "structured_output_reliable": None,
                        "abstention_appropriate": None,
                        "preferred": None,
                        "notes": "",
                    },
                }
            )
            key_entry[label] = {
                "run_id": manifest["run_id"],
                "model_key": manifest["model_key"],
                "backend": manifest["backend"],
            }
        packet.append(
            {
                "question_id": question_id,
                "question": benchmark_row["normalized_question"],
                "dependency_flags": {
                    "formula": benchmark_row["requires_formula"],
                    "visual": benchmark_row["requires_visual"],
                    "table": benchmark_row["requires_table"],
                    "multiple_passages": benchmark_row["requires_multiple_passages"],
                },
                "required_answer_points": benchmark_row["required_answer_points"],
                "optional_answer_points": benchmark_row["optional_answer_points"],
                "prohibited_or_unsupported_claims": benchmark_row[
                    "prohibited_or_unsupported_claims"
                ],
                "context_sha256": first_result["context_sha256"],
                "supplied_evidence": first_result["supplied_evidence"],
                "answers": answers,
            }
        )
        answer_key["questions"][question_id] = key_entry
    return packet, answer_key


def render_html(packet: list[dict[str, Any]]) -> str:
    sections = []
    for row in packet:
        evidence = "".join(
            "<article><h4>"
            + html.escape(item["evidence_id"])
            + "</h4><pre>"
            + html.escape(item["text"])
            + "</pre></article>"
            for item in row["supplied_evidence"]
        )
        answers = "".join(
            "<section class='answer'><h3>"
            + html.escape(answer["label"])
            + "</h3><p>"
            + html.escape(answer["answer"])
            + "</p><p><strong>Citations:</strong> "
            + html.escape(json.dumps(answer["citations"], ensure_ascii=False))
            + "</p><table><tr><th>Coverage 0–4</th><th>Quality 1–5</th>"
            + "<th>Citation support 0–2</th><th>Unsupported count</th>"
            + "<th>Formula 0–2/N/A</th><th>Multi-passage 0–2/N/A</th>"
            + "<th>Preferred?</th></tr><tr>"
            + "<td></td>" * 7
            + "</tr></table><p class='notes'>Notes:</p></section>"
            for answer in row["answers"]
        )
        rubric = "<ul>" + "".join(
            f"<li>{html.escape(point)}</li>" for point in row["required_answer_points"]
        ) + "</ul>"
        sections.append(
            "<main><h2>"
            + html.escape(f"{row['question_id']}: {row['question']}")
            + "</h2><h3>Required points</h3>"
            + rubric
            + "<details><summary>Frozen supplied evidence</summary>"
            + evidence
            + "</details>"
            + answers
            + "</main>"
        )
    return """<!doctype html>
<html><head><meta charset="utf-8"><title>Blinded local-model review</title>
<style>
body{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;color:#17202a}
main{page-break-after:always;border-bottom:2px solid #ccd1d1;padding-bottom:2rem}
pre{white-space:pre-wrap;background:#f4f6f7;padding:1rem}.answer{border:1px solid #aeb6bf;padding:1rem;margin:1rem 0}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #7b7d7d;padding:.5rem;height:2rem}
.notes{height:4rem;border-bottom:1px solid #7b7d7d}
</style></head><body><h1>Blinded human-review packet</h1>
<p>Score answers before opening the separate answer key. Automatic scores are intentionally omitted.</p>
""" + "\n".join(sections) + "</body></html>\n"


def build_review(
    run_ids: list[str],
    output_dir: Path,
    experiment_dir: Path = EXPERIMENT_DIR,
) -> dict[str, Any]:
    benchmark = read_jsonl(ROOT / "data/benchmarks/generation_benchmark_v1.jsonl")
    runs = [load_run(experiment_dir, run_id) for run_id in run_ids]
    packet, answer_key = build_packet(benchmark, runs)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl_atomic(output_dir / "blinded_human_review_packet.jsonl", packet)
    write_json_atomic(output_dir / "blinded_answer_key.json", answer_key)
    (output_dir / "blinded_human_review_packet.html").write_text(
        render_html(packet), encoding="utf-8", newline="\n"
    )
    summary = {
        "schema_version": 1,
        "questions": len(packet),
        "run_ids": run_ids,
        "packet": "blinded_human_review_packet.jsonl",
        "html": "blinded_human_review_packet.html",
        "answer_key": "blinded_answer_key.json",
    }
    write_json_atomic(output_dir / "packet_manifest.json", summary)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", action="append", required=True)
    parser.add_argument(
        "--experiment-dir",
        type=Path,
        default=EXPERIMENT_DIR,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
    )
    args = parser.parse_args(argv)
    experiment_dir = args.experiment_dir.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else experiment_dir / "human_review/finalists"
    )
    print(
        json.dumps(
            build_review(args.run_id, output_dir, experiment_dir),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
