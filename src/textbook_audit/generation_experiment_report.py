"""Build final reports and blinded review artifacts from completed local runs."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from textbook_audit.generation_benchmark import read_jsonl
from textbook_audit.generation_experiments import ROOT, utc_now, write_json_atomic, write_jsonl_atomic


DEFAULT_OUTPUT = ROOT / "reports/generation_experiments"


def classify_failure(result: dict[str, Any], benchmark: dict[str, Any]) -> str | None:
    """Attribute a weak retrieved answer to evidence, grounding, or synthesis."""
    supplied_pages = {
        page for item in result["supplied_evidence"]
        for page in item.get("pdf_pages", [item.get("pdf_page")]) if page is not None
    }
    accepted = set(benchmark["accepted_pdf_pages"])
    evaluation = result["evaluation"]
    if not supplied_pages & accepted:
        return "visual information unavailable" if benchmark["requires_visual"] else "evidence absent from retrieved context"
    if evaluation["false_insufficient_evidence"]:
        return "evidence present but model missed it"
    if evaluation["citation_validity"] < 1.0:
        return "citation failure"
    if evaluation["unsupported_claims"]:
        return "unsupported extrapolation"
    if evaluation["required_point_coverage"] < 1.0:
        if benchmark["requires_formula"]:
            return "formula error or omission"
        if benchmark["requires_multiple_passages"]:
            return "multi-passage synthesis failure"
        return "evidence present but incomplete"
    return None


def pareto_frontier(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return runs not dominated on coverage, citation, unsupported rate, and p95."""
    frontier = []
    for candidate in rows:
        cm = candidate["metrics"]
        dominated = False
        for other in rows:
            if other is candidate:
                continue
            om = other["metrics"]
            c_latency = cm.get("p95_latency_seconds") or float("inf")
            o_latency = om.get("p95_latency_seconds") or float("inf")
            no_worse = (
                om["required_point_coverage"] >= cm["required_point_coverage"]
                and om["citation_validity"] >= cm["citation_validity"]
                and om["unsupported_claim_rate"] <= cm["unsupported_claim_rate"]
                and o_latency <= c_latency
            )
            strictly = (
                om["required_point_coverage"] > cm["required_point_coverage"]
                or om["citation_validity"] > cm["citation_validity"]
                or om["unsupported_claim_rate"] < cm["unsupported_claim_rate"]
                or o_latency < c_latency
            )
            if no_worse and strictly:
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    return frontier


def _load_results(output: Path, run_id: str) -> list[dict[str, Any]]:
    """Load the deterministic compact result view for a completed run."""
    return read_jsonl(output / "runs" / run_id / "results.jsonl")


def slice_metrics(results: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    """Aggregate exact counts and screening metrics by a categorical result field."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        groups[str(result[field])].append(result)
    return {
        label: {
            "questions": len(values),
            "required_point_coverage": round(sum(v["evaluation"]["required_point_coverage"] for v in values) / len(values), 4),
            "citation_validity": round(sum(v["evaluation"]["citation_validity"] for v in values) / len(values), 4),
        } for label, values in groups.items()
    }


def build_review_packet(output: Path, ledger: list[dict[str, Any]], benchmark: list[dict[str, Any]]) -> int:
    """Create anonymized finalist answers with evidence and rubrics for human review."""
    finalist_runs = [row for row in ledger if row["split"] == "holdout"]
    labels = {row["run_id"]: f"Answer {chr(65 + index)}" for index, row in enumerate(sorted(finalist_runs, key=lambda x: x["run_id"]))}
    by_question: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for run in finalist_runs:
        for result in _load_results(output, run["run_id"]):
            by_question[result["question_id"]].append((run, result))
    benchmark_by_id = {row["question_id"]: row for row in benchmark}
    packet = []
    for question_id in sorted(by_question):
        row = benchmark_by_id[question_id]
        packet.append({
            "question_id": question_id,
            "question": row["normalized_question"],
            "required_answer_points": row["required_answer_points"],
            "optional_answer_points": row["optional_answer_points"],
            "prohibited_or_unsupported_claims": row["prohibited_or_unsupported_claims"],
            "answers": [{
                "label": labels[run["run_id"]],
                "evaluation_mode": run["evaluation_mode"],
                "supplied_evidence": result["supplied_evidence"],
                "answer": result["parsed_output"].get("answer", ""),
                "citations": result["parsed_output"].get("citations", []),
                "automatic_screen": result["evaluation"],
                "reviewer_decision": None,
                "reviewer_notes": "",
            } for run, result in by_question[question_id]],
        })
    write_jsonl_atomic(output / "blinded_human_review_packet.jsonl", packet)
    write_json_atomic(output / "blinded_answer_key.json", labels)
    return len(packet)


def build_report(output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    """Build the final Markdown report, diagnostics, and machine-readable summary."""
    baseline_frozen = (ROOT / "config/generation_baseline_v1.json").is_file()
    ledger = read_jsonl(output / "experiment_runs.jsonl")
    benchmark = read_jsonl(ROOT / "data/benchmarks/generation_benchmark_v1.jsonl")
    benchmark_by_id = {row["question_id"]: row for row in benchmark}
    winner = json.loads((output / "provisional_winner.json").read_text(encoding="utf-8"))["provisional_winner"]
    final_gold = next(row for row in ledger if row["run_id"] == winner["all_gold_run"])
    final_retrieved = next(row for row in ledger if row["run_id"] == winner["all_retrieved_run"])
    retrieved_results = _load_results(output, final_retrieved["run_id"])
    book_metrics = slice_metrics(retrieved_results, "book_id")
    difficulty_metrics = slice_metrics(retrieved_results, "difficulty")
    failures = []
    dependency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in retrieved_results:
        benchmark_row = benchmark_by_id[result["question_id"]]
        category = classify_failure(result, benchmark_row)
        if category:
            failures.append({
                "question_id": result["question_id"], "question": result["question"],
                "category": category,
                "required_point_coverage": result["evaluation"]["required_point_coverage"],
                "notes": result["parsed_output"].get("missing_information", []),
            })
        for key, active in result["dependency_flags"].items():
            if active:
                dependency[key].append(result)
    dependency_metrics = {
        key: {
            "questions": len(values),
            "required_point_coverage": round(sum(v["evaluation"]["required_point_coverage"] for v in values) / len(values), 4),
            "citation_validity": round(sum(v["evaluation"]["citation_validity"] for v in values) / len(values), 4),
        } for key, values in dependency.items()
    }
    frontier = pareto_frontier(ledger)
    holdout_rows = [row for row in ledger if row["split"] == "holdout"]
    retrieved_holdout = [row for row in holdout_rows if row["evaluation_mode"] == "retrieved"]
    best_quality = max(retrieved_holdout, key=lambda row: row["metrics"]["required_point_coverage"])
    lightweight = next(row for row in retrieved_holdout if row["model_key"] == "qwen3_8b_q4_k_m")
    packet_count = build_review_packet(output, ledger, benchmark)
    abstention = (json.loads((output / "abstention_metrics.json").read_text(encoding="utf-8"))
                  if (output / "abstention_metrics.json").is_file() else None)
    summary = {
        "schema_version": 1, "generated_at": utc_now(), "provisional_winner": winner,
        "decision_status": (
            "frozen_as_local_offline_fallback_in_generation_baseline_v1"
            if baseline_frozen else "provisional_pending_human_review"
        ),
        "gold_metrics": final_gold["metrics"], "retrieved_metrics": final_retrieved["metrics"],
        "pareto_run_ids": [row["run_id"] for row in frontier],
        "failure_counts": dict(Counter(item["category"] for item in failures)),
        "dependency_metrics": dependency_metrics,
        "book_metrics": book_metrics,
        "difficulty_metrics": difficulty_metrics,
        "blinded_review_questions": packet_count,
        "abstention_diagnostic": abstention,
        "gemma_status": "not_run_hugging_face_repository_access_denied",
        "configuration_roles": {
            "best_lightweight": lightweight["run_id"],
            "best_quality": best_quality["run_id"],
            "preferred_balanced": final_retrieved["run_id"],
        },
    }
    write_json_atomic(output / "final_summary.json", summary)
    write_jsonl_atomic(output / "retrieved_failure_breakdown.jsonl", failures)

    recommendation_heading = (
        "## Historical local recommendation (frozen fallback)"
        if baseline_frozen else "## Provisional recommendation"
    )
    status = (
        "- Status: frozen as the local_offline fallback in Generation Baseline v1."
        if baseline_frozen else "- Status: provisional until the blinded packet is reviewed."
    )
    lines = [
        "# Local generation experiments v1", "", recommendation_heading, "",
        f"- Model: `{winner['model_key']}`",
        f"- Prompt: `{winner['prompt_strategy']}`",
        f"- Retrieved context: `{winner['context_strategy']}`",
        f"- Maximum output: {winner['max_output_tokens']} tokens",
        status, "",
        "## Configuration roles", "",
        f"- Best lightweight: `{lightweight['model_key']}`; retrieved holdout coverage "
        f"{lightweight['metrics']['required_point_coverage']:.4f}, p95 "
        f"{lightweight['metrics']['p95_latency_seconds']} s, max output "
        f"{lightweight['settings']['max_output_tokens']} tokens.",
        f"- Best automatic quality: `{best_quality['model_key']}`; retrieved holdout coverage "
        f"{best_quality['metrics']['required_point_coverage']:.4f}, p95 "
        f"{best_quality['metrics']['p95_latency_seconds']} s, max output "
        f"{best_quality['settings']['max_output_tokens']} tokens.",
        "- Preferred balanced: Qwen3-8B. It has the stronger grounding score "
        "(citation validity minus unsupported rate), lower latency and memory, and is the "
        "exact configuration used for the final 40-question run.", "",
        "## Finalist holdout comparison", "",
        "| Model | Mode | Coverage | Citation | Unsupported | Formula | p95 latency | Peak RSS GiB |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in holdout_rows:
        m = row["metrics"]
        lines.append(
            f"| {row['model_key']} | {row['evaluation_mode']} | "
            f"{m['required_point_coverage']:.4f} | {m['citation_validity']:.4f} | "
            f"{m['unsupported_claim_rate']:.4f} | {m['formula_accuracy']:.4f} | "
            f"{m['p95_latency_seconds']} | {m['peak_rss_bytes'] / 1024**3:.2f} |"
        )
    lines.extend([
        "",
        "## Final 40-question comparison", "",
        "| Mode | Required coverage | Citation validity | Unsupported rate | Structured output | p50 latency | p95 latency |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for label, run in (("Gold", final_gold), ("Frozen retrieved", final_retrieved)):
        m = run["metrics"]
        lines.append(f"| {label} | {m['required_point_coverage']:.4f} | {m['citation_validity']:.4f} | {m['unsupported_claim_rate']:.4f} | {m['structured_output_rate']:.4f} | {m['p50_latency_seconds']} | {m['p95_latency_seconds']} |")
    lines.extend(["", "## Dependency diagnostics", "", "| Slice | Questions | Coverage | Citation validity |", "|---|---:|---:|---:|"])
    for key, value in sorted(dependency_metrics.items()):
        lines.append(f"| {key} | {value['questions']} | {value['required_point_coverage']:.4f} | {value['citation_validity']:.4f} |")
    lines.extend(["", "## Retrieved results by book and difficulty", "", "| Slice | Questions | Coverage | Citation validity |", "|---|---:|---:|---:|"])
    for label, value in {**book_metrics, **difficulty_metrics}.items():
        lines.append(f"| {label} | {value['questions']} | {value['required_point_coverage']:.4f} | {value['citation_validity']:.4f} |")
    lines.extend(["", "## Retrieved-context failures", ""])
    if failures:
        lines.extend(["| Question | Category | Coverage |", "|---|---|---:|"])
        for failure in failures:
            lines.append(f"| {failure['question_id']} | {failure['category']} | {failure['required_point_coverage']:.4f} |")
    else:
        lines.append("No deterministic screening failures were classified.")
    lines.extend([
        "", "## Abstention diagnostic", "",
        (f"Prompt-only abstention: {abstention['prompt_only_correct_abstentions']}/5; "
         f"model plus deterministic citation-support check: "
         f"{abstention['model_plus_support_correct_abstentions']}/5. "
         "Treat this as diagnostic only." if abstention else "Not run."),
        "", "## Model availability", "",
        "The approved Gemma 3 4B and 12B repositories returned access denied for the signed-in Hugging Face account, so those arms and the Gemma-only visual diagnostic were not run. This is an external repository-access limitation, not a runtime rejection.",
        "", "## Interpretation limits", "",
        "Lexical rubric matching is a repeatable screen, not proof of scientific correctness. Review `blinded_human_review_packet.jsonl` before freezing a generation baseline.",
        "", "## Success-target assessment", "",
        f"- Gold required-point coverage: {final_gold['metrics']['required_point_coverage']:.2%} "
        "versus the 85% target: **not met**.",
        f"- Retrieved required-point coverage: {final_retrieved['metrics']['required_point_coverage']:.2%} "
        "versus the 75% target: **not met**.",
        f"- Gold citations valid: {round(final_gold['metrics']['citation_validity'] * 40)}/40; "
        f"retrieved citations valid: {round(final_retrieved['metrics']['citation_validity'] * 40)}/40.",
        f"- Retrieved formula screen: {round(final_retrieved['metrics']['formula_accuracy'] * 10)}/10. "
        "Formula answering is the clearest blocker.",
        "- Conclusion: this is a reproducible experiment winner, but it is not strong enough "
        "to freeze as the production generation baseline without blinded human review and a "
        "targeted formula/completeness improvement cycle.",
        "", "## Exact retained runtime and model", "",
        f"- Model: `{final_retrieved['model']['repository']}` revision "
        f"`{final_retrieved['model']['revision']}`, file `{final_retrieved['model']['filename']}`, "
        f"SHA-256 `{final_retrieved['model_sha256']}`.",
        f"- Runtime: llama.cpp build {final_retrieved['runtime']['build_number']} commit "
        f"`{final_retrieved['runtime']['build_commit']}`; Windows ARM64 CPU; "
        f"{final_retrieved['runtime']['threads']} threads; context "
        f"{final_retrieved['runtime']['context_size']}; batch/ubatch "
        f"{final_retrieved['runtime']['batch_size']}/{final_retrieved['runtime']['ubatch_size']}; "
        f"GPU layers {final_retrieved['runtime']['gpu_layers']}.",
        f"- Sampling: seed {final_retrieved['settings']['seed']}, temperature "
        f"{final_retrieved['settings']['temperature']}, max output "
        f"{final_retrieved['settings']['max_output_tokens']}, thinking disabled.",
        "", "## Exact retained prompt template", "", "```text",
        "/no_think",
        "Use only the supplied textbook evidence. Do not use outside knowledge. If it cannot support the question, return insufficient_evidence. Never invent page numbers. First select the relevant evidence IDs internally, then write the answer. Make the answer {depth} and suitable for a Class 10 student.",
        'Return only valid JSON with exactly this shape: {"status":"answered|insufficient_evidence","answer":"...","selected_evidence_ids":["E1"],"citations":[{"evidence_id":"E1","pdf_page":1,"textbook_page":1}],"missing_information":[]}',
        "", "QUESTION:", "{normalized_question}", "", "TEXTBOOK EVIDENCE:",
        "[{evidence_id}] PDF {pdf_page}; textbook {textbook_page}", "{evidence_text}", "```",
        "", "## Reproduction", "",
        "```powershell",
        "temp\\python-x64\\python.exe scripts\\run_generation_experiment_matrix.py `",
        "  --llama-server <path-to-native-arm64-llama-server.exe> `",
        "  --qwen8 <path-to-Qwen3-8B-Q4_K_M.gguf> `",
        "  --qwen14 <path-to-Qwen3-14B-Q4_K_M.gguf>",
        "```", "",
        "Completed checkpoints are reused, and frozen input hashes are verified before every configuration.", "",
    ])
    (output / "generation_experiments_report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary
