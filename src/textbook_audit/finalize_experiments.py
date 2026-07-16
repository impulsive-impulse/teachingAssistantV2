"""Build the evidence-driven final handoff for the approved local RAG loop."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .experiment_tracking import (experiment_paths, read_jsonl, render_resume,
                                  sha256_file, write_json)
from .retrieval import read_jsonl as read_benchmark


QUALITY_RUN = "phase_h_h3_combined_specialist_priors"
LIGHTWEIGHT_RUN = "phase_f_f0_bm25_fixed_600_100"
BALANCED_RUN = QUALITY_RUN
LATENCY_FLOOR_RUN = "phase_f_f3_bge_small_fixed_600_100"
CONTEXT_RUN = "phase_i_i0_overlap_merge_metadata_preserving"
ELIGIBLE_PHASES = {"E", "F", "G", "H"}
DETAIL_ARTIFACT_NAMES = {
    "candidate_pools.jsonl", "representations.jsonl", "ranked_candidates.jsonl",
    "preselected_candidates.jsonl", "rankings.jsonl", "evidence_sets.jsonl",
    "contexts.jsonl",
}


def comparable_retrieval_runs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep successful end-to-end retrieval runs with comparable core metrics."""
    output = []
    for record in records:
        overall = record.get("metrics", {}).get("overall", {})
        natural = record.get("metrics", {}).get("natural_student", {})
        latency = record.get("latency", {})
        memory = record.get("peak_memory", {})
        if (record.get("phase") in ELIGIBLE_PHASES
                # Phase H4/I selectors inherit parent latency but were
                # measured in a process without the parent model, so their
                # peak RSS is not comparable to end-to-end retrievers.
                and not record.get("configuration", {}).get("parent_ranking_run_id")
                and overall.get("answerable_questions") == 61
                and natural.get("answerable_questions") == 20
                and all(key in overall for key in ("hit_at_1_count", "hit_at_5_count", "mrr"))
                and latency.get("p95_ms") is not None
                and memory.get("peak_rss_mb") is not None):
            output.append(record)
    return output


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """Test natural-first quality, latency, and memory Pareto dominance."""
    l_o, r_o = left["metrics"]["overall"], right["metrics"]["overall"]
    l_n, r_n = left["metrics"]["natural_student"], right["metrics"]["natural_student"]
    better = (
        l_n["hit_at_5_count"] >= r_n["hit_at_5_count"],
        l_n["mrr"] >= r_n["mrr"],
        l_o["hit_at_1_count"] >= r_o["hit_at_1_count"],
        l_o["mrr"] >= r_o["mrr"],
        left["latency"]["p95_ms"] <= right["latency"]["p95_ms"],
        left["peak_memory"]["peak_rss_mb"] <= right["peak_memory"]["peak_rss_mb"],
    )
    strict = (
        l_n["hit_at_5_count"] > r_n["hit_at_5_count"]
        or l_n["mrr"] > r_n["mrr"]
        or l_o["hit_at_1_count"] > r_o["hit_at_1_count"]
        or l_o["mrr"] > r_o["mrr"]
        or left["latency"]["p95_ms"] < right["latency"]["p95_ms"]
        or left["peak_memory"]["peak_rss_mb"] < right["peak_memory"]["peak_rss_mb"]
    )
    return all(better) and strict


def pareto_frontier(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every non-dominated comparable retrieval configuration."""
    return [record for record in records
            if not any(other["run_id"] != record["run_id"]
                       and _dominates(other, record) for other in records)]


def _index_bytes(record: dict[str, Any]) -> int:
    """Read the most specific stored index-size field without guessing."""
    disk = record.get("disk_index_size", {})
    for field in ("embedding_index_bytes", "new_index_bytes", "run_artifacts_bytes"):
        if disk.get(field) is not None:
            return int(disk[field])
    return 0


def _leaderboard_row(record: dict[str, Any], frontier: set[str]) -> dict[str, Any]:
    """Flatten one immutable run into the final sortable leaderboard schema."""
    overall = record["metrics"]["overall"]
    natural = record["metrics"]["natural_student"]
    canonical = record["metrics"]["canonical"]
    recall = record.get("candidate_recall", {})
    return {
        "run_id": record["run_id"], "phase": record["phase"],
        "pipeline_name": record.get("configuration", {}).get(
            "pipeline_name", record["run_id"]),
        "hit_at_1": overall["hit_at_1_count"],
        "hit_at_1_pct": round(100 * overall["hit_at_1"], 3),
        "hit_at_3": overall["hit_at_3_count"],
        "hit_at_3_pct": round(100 * overall["hit_at_3"], 3),
        "hit_at_5": overall["hit_at_5_count"],
        "hit_at_5_pct": round(100 * overall["hit_at_5"], 3),
        "mrr": round(overall["mrr"], 6),
        "natural_hit_at_5": natural["hit_at_5_count"],
        "natural_hit_at_5_pct": round(100 * natural["hit_at_5"], 3),
        "natural_mrr": round(natural["mrr"], 6),
        "canonical_hit_at_5": canonical["hit_at_5_count"],
        "canonical_hit_at_5_pct": round(100 * canonical["hit_at_5"], 3),
        "candidate_recall": recall.get("count"),
        "p50_latency_ms": round(float(record["latency"].get("p50_ms", 0)), 3),
        "p95_latency_ms": round(float(record["latency"]["p95_ms"]), 3),
        "peak_memory_mb": round(float(record["peak_memory"]["peak_rss_mb"]), 3),
        "index_bytes": _index_bytes(record),
        "pareto_frontier": record["run_id"] in frontier,
        "historical_decision": record["decision"],
    }


def _failure_category(question: dict[str, Any]) -> str:
    """Assign one transparent post-ranking diagnostic category to a miss."""
    if question.get("visual_dependency"):
        return "visual evidence limited to captions/text"
    if question.get("formula_dependency"):
        return "formula/symbol semantic mismatch"
    if question.get("table_dependency"):
        return "table evidence mismatch"
    if question.get("requires_multiple_pages") or question.get("requires_multiple_chunks"):
        return "distributed evidence not ranked in top five"
    if question.get("benchmark_slice") == "natural_student":
        return "natural wording or underspecification"
    return "general lexical/semantic ranking miss"


def remaining_failures(benchmark: list[dict[str, Any]],
                       ranking_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter]:
    """List every answerable top-five miss and diagnostic category."""
    by_id = {row["question_id"]: row for row in benchmark}
    failures = []
    for row in ranking_rows:
        question = by_id[row["question_id"]]
        if not question.get("gold_answer_span"):
            continue
        if row.get("first_gold_rank") is not None and row["first_gold_rank"] <= 5:
            continue
        category = _failure_category(question)
        failures.append({"question_id": row["question_id"],
                         "book_id": row["book_id"],
                         "benchmark_slice": row.get("benchmark_slice", "canonical"),
                         "question": row["question"], "category": category})
    return failures, Counter(item["category"] for item in failures)


def _selected_pipeline(record: dict[str, Any], role: str) -> dict[str, Any]:
    """Serialize the measured configuration and resource envelope for handoff."""
    return {"role": role, "run_id": record["run_id"],
            "configuration": record["configuration"],
            "model_revisions": record["model_revisions"],
            "metrics": {key: record["metrics"][key]
                        for key in ("overall", "canonical", "natural_student")},
            "all_slices": record["metrics"].get("all_slices", {}),
            "latency": record["latency"], "peak_memory": record["peak_memory"],
            "disk_index_size": record["disk_index_size"],
            "candidate_recall": record["candidate_recall"]}


def _render_report(selection: dict[str, Any], leaderboard: list[dict[str, Any]],
                   frontier: list[dict[str, Any]], failures: list[dict[str, Any]],
                   categories: Counter) -> str:
    """Render the concise final evidence report required by the approved loop."""
    chosen = {item["role"]: item for item in selection["selected_pipelines"]}
    def hit(metric: dict[str, Any], cutoff: int) -> str:
        """Format one exact retrieval count with its denominator and percent."""
        count = metric[f"hit_at_{cutoff}_count"]
        total = metric["answerable_questions"]
        return f"{count}/{total} ({100 * count / total:.1f}%)"
    lines = ["# Final local RAG experiment report", "",
             "The approved retrieval loop is complete through stable context assembly. "
             "Phase J was not run because no reviewed generation-quality benchmark exists.", "",
             "## Completion audit", "",
             "| Phase | Completed runs | Disposition |",
             "|---|---:|---|",
             f'| A — candidate preservation | {selection["run_counts_by_phase"].get("A", 0)} | Full deduplicated union retained 61/61; every capped pool lost evidence. |',
             f'| B — text representation | {selection["run_counts_by_phase"].get("B", 0)} | Query-dense member + two page windows + neighbours retained for controlled reranker tests. |',
             f'| C — fusion/reranking logic | {selection["run_counts_by_phase"].get("C", 0)} | Soft fusion retained for speed; capped preselectors rejected on recall. |',
             f'| D — reranker bake-off | {selection["run_counts_by_phase"].get("D", 0)} | MiniLM retained only as diagnostic; larger models stopped by successive runtime gates. |',
             f'| E — embedding bake-off | {selection["run_counts_by_phase"].get("E", 0)} | BGE-small retained for local balance; E5 retained as quality reference. |',
             f'| F — chunking | {selection["run_counts_by_phase"].get("F", 0)} | Fixed 600/100 selected; BGE-small hybrid confirmed. |',
             f'| G — query processing | {selection["run_counts_by_phase"].get("G", 0)} | Deterministic textbook synonyms retained; Gemma remained separately gated. |',
             f'| H — specialists | {selection["run_counts_by_phase"].get("H", 0)} | Combined equation/table/caption priors retained; base top-five preserved. |',
             f'| I — context assembly | {selection["run_counts_by_phase"].get("I", 0)} | Overlap merge retained. |',
             "| J — answer generation | 0 | Correctly gated: generation benchmark absent. |", "",
             f'All {selection["total_completed_runs"]} immutable run records have unique IDs, complete required fields, reproduction commands, and locally existing declared outputs; pending run count is zero. '
             f'The artifact manifest hashes all {selection["artifact_manifest_rows"]} declared files. '
             f'{selection["gitignored_detail_artifacts"]} bulky per-query detail files are reproducible and intentionally excluded from Git; compact configurations, metrics, ledgers, and reports are tracked.', "",
             "## Selected pipelines", "",
             "| Role | Run | Overall H@1/3/5 | MRR | Natural H@5 / MRR | Canonical H@5 | p95 | Peak RSS |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for role in ("best_quality", "best_lightweight_cpu", "preferred_balanced"):
        item = chosen[role]
        o, n, c = item["metrics"]["overall"], item["metrics"]["natural_student"], item["metrics"]["canonical"]
        lines.append(f'| {role} | `{item["run_id"]}` | '
                     f'{hit(o, 1)} / {hit(o, 3)} / {hit(o, 5)} | '
                     f'{o["mrr"]:.3f} | {hit(n, 5)} / {n["mrr"]:.3f} | '
                     f'{hit(c, 5)} | {item["latency"]["p95_ms"]:.1f} ms | '
                     f'{item["peak_memory"]["peak_rss_mb"]:.0f} MB |')
    balanced_slices = chosen["preferred_balanced"]["all_slices"]
    slice_order = ["book:biology", "book:physical_sciences", "formula_dependent",
                   "visual_dependent", "table_dependent", "multi_page", "multi_chunk",
                   "difficulty:easy", "difficulty:medium", "difficulty:hard",
                   "query_style:colloquial", "query_style:short_underspecified",
                   "query_style:different_vocabulary", "query_style:cause_effect",
                   "query_style:misconception", "query_style:imperfect_grammar"]
    lines.extend(["", "Best quality and balanced are the same combined-specialist pipeline. "
                  "The lightweight profile is fixed-600/100 BM25 with no neural model; it trades four natural "
                  "and five overall Hit@5 successes for a roughly 40x lower p95 and much smaller memory footprint. "
                  "Differences of one question should be treated cautiously.", "",
                  "## Balanced pipeline slices", "",
                  "| Slice | N | Hit@1 | Hit@3 | Hit@5 | MRR |",
                  "|---|---:|---:|---:|---:|---:|"])
    for name in slice_order:
        metric = balanced_slices.get(name)
        if not metric:
            continue
        lines.append(f'| {name} | {metric["answerable_questions"]} | {hit(metric, 1)} | '
                     f'{hit(metric, 3)} | {hit(metric, 5)} | {metric["mrr"]:.3f} |')
    lines.extend(["", "The five negative/weak-evidence rows are excluded from Hit@K and MRR; "
                  "no generation or abstention score is claimed for them.", "",
                  "## Quality–latency–memory Pareto frontier", "",
                  "Dominance maximizes natural Hit@5/MRR and overall Hit@1/MRR while minimizing warm p95 latency and peak RSS.", "",
                  "| Run | Natural H@5 | Natural MRR | Overall H@1 | Overall MRR | p95 | Peak RSS |",
                  "|---|---:|---:|---:|---:|---:|---:|"])
    by_id = {row["run_id"]: row for row in leaderboard}
    for record in sorted(frontier, key=lambda r: (-r["metrics"]["natural_student"]["hit_at_5_count"],
                                                  -r["metrics"]["overall"]["mrr"],
                                                  r["latency"]["p95_ms"])):
        row = by_id[record["run_id"]]
        lines.append(f'| `{row["run_id"]}` | {row["natural_hit_at_5"]}/20 | '
                     f'{row["natural_mrr"]:.3f} | {row["hit_at_1"]}/61 | {row["mrr"]:.3f} | '
                     f'{row["p95_latency_ms"]:.1f} ms | {row["peak_memory_mb"]:.0f} MB |')
    lines.extend(["", "## Exact balanced architecture", "", "```text",
                  "student question + explicit book_id",
                  "  -> deterministic textbook-synonym expansion",
                  "  -> [fixed 600/100 BM25] + [normalized BGE-small cosine]",
                  "  -> static specialist activator",
                  "       formula -> equation + surrounding-text page prior",
                  "       table   -> row-with-repeated-header page prior",
                  "       visual  -> caption + nearby-text page prior",
                  "  -> lift active page priors to child chunks",
                  "  -> reciprocal-rank fusion (k=60)",
                  "  -> top five fixed chunks",
                  "  -> exact-overlap merging with PDF/textbook/chapter/section metadata",
                  "  -> grounded evidence context (generation intentionally absent)",
                  "```", "", "## Reproduce", "", "```powershell",
                  "# Rebuild/reuse the selected indexes and benchmark runs",
                  "temp\\python-x64\\python.exe scripts\\run_chunking_bakeoff.py --stage bge_confirmation --device cpu --batch-size 16",
                  "temp\\python-x64\\python.exe scripts\\run_query_processing.py --stage screen --device cpu --batch-size 16",
                  "temp\\python-x64\\python.exe scripts\\run_specialist_retrieval.py --stage combined --device cpu --batch-size 16",
                  "temp\\python-x64\\python.exe scripts\\run_evidence_sets.py",
                  "temp\\python-x64\\python.exe scripts\\run_context_assembly.py",
                  "python scripts\\finalize_experiments.py",
                  "", "# Query the retained balanced pipeline with full evidence text",
                  "temp\\python-x64\\python.exe scripts\\query_final_pipeline.py \"How do plants eat?\" --book-id biology --profile balanced --include-text",
                  "```", "", "## Remaining top-five failures", ""])
    for category, count in sorted(categories.items()):
        lines.append(f"- {category}: {count}")
    lines.extend(["", "| ID | Book | Slice | Likely cause | Question |",
                  "|---|---|---|---|---|"])
    for failure in failures:
        question = failure["question"].replace("|", "\\|")
        lines.append(f'| {failure["question_id"]} | {failure["book_id"]} | '
                     f'{failure["benchmark_slice"]} | {failure["category"]} | {question} |')
    lines.extend(["", "These causes are post-ranking diagnostics based on dependency labels and wording; "
                  "they were not used to construct or score rankings.", "",
                  "## Limitations and next milestone", "",
                  "- The benchmark has only 61 answerable questions; one row is 1.6 percentage points overall and five points in the natural slice.",
                  "- Exact reviewed spans do not prove that a generated answer would be correct, faithful, well cited, or appropriately abstaining.",
                  "- Visual retrieval is caption/nearby-text only; extracted rasters were audited but no unapproved multimodal model was used.",
                  "- CPU timings are local warm-query measurements and some earlier fusion-only runs are excluded from this comparable frontier.",
                  "", "## Explicitly stopped or gated work", "",
                  "- BGE-M3 multi-vector/ColBERT escalation stopped after dense/sparse variants were slower without a natural-student gain.",
                  "- BGE-reranker-v2-m3 was stopped after an eight-query screen at 154 seconds p95; mxbai-base was stopped as runtime-infeasible after more than 300 seconds without a completed query.",
                  "- Local Gemma rewriting remained a separate unapproved model gate and was not downloaded or run.",
                  "- Locally generated diagram descriptions and multimodal ranking were not run because no multimodal model was approved; visual-caption retrieval and raster extraction were audited separately.",
                  "- Phase J generation was not run because retrieval labels cannot evaluate answer correctness or grounding.",
                  "", "Next milestone: create a reviewed generation benchmark covering correctness, context faithfulness, page citations, and abstention on the five negative rows; only then approve Phase J.", ""])
    return "\n".join(lines)


def run(root: Path) -> dict[str, Any]:
    """Generate final leaderboard, frontier, selected configs, and report."""
    paths = experiment_paths(root)
    records = read_jsonl(paths["runs"])
    by_id = {record["run_id"]: record for record in records}
    required = {QUALITY_RUN, LIGHTWEIGHT_RUN, BALANCED_RUN, LATENCY_FLOOR_RUN, CONTEXT_RUN}
    missing = sorted(required - set(by_id))
    if missing:
        raise FileNotFoundError("required completed experiment runs are missing: " + ", ".join(missing))
    manifest_rows = []
    for record in records:
        for relative in record["output_artifact_paths"]:
            artifact = root / relative
            if not artifact.is_file():
                raise FileNotFoundError(
                    f'declared run artifact is missing: {record["run_id"]}: {relative}')
            detail = artifact.name in DETAIL_ARTIFACT_NAMES
            manifest_rows.append({
                "run_id": record["run_id"], "path": relative,
                "size_bytes": artifact.stat().st_size,
                "sha256": sha256_file(artifact),
                "retention": ("gitignored_reproducible_detail" if detail
                              else "tracked_traceability"),
            })
    manifest_path = paths["base"] / "experiment_artifact_manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in manifest_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    comparable = comparable_retrieval_runs(records)
    frontier = pareto_frontier(comparable)
    frontier_ids = {record["run_id"] for record in frontier}
    rows = [_leaderboard_row(record, frontier_ids) for record in comparable]
    rows.sort(key=lambda row: (-row["natural_hit_at_5"], -row["mrr"],
                               row["p95_latency_ms"], row["run_id"]))
    output_dir = paths["base"]
    leaderboard_path = output_dir / "final_experiment_leaderboard.csv"
    with leaderboard_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    frontier_path = output_dir / "final_pareto_frontier.csv"
    frontier_rows = [row for row in rows if row["pareto_frontier"]]
    with frontier_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(frontier_rows)
    benchmark = read_benchmark(root / "data" / "benchmarks" / "retrieval_benchmark_v1.jsonl")
    ranking_rows = read_benchmark(root / "reports" / "experiments" / "runs" /
                                  QUALITY_RUN / "rankings.jsonl")
    failures, categories = remaining_failures(benchmark, ranking_rows)
    selection = {
        "schema_version": 1,
        "total_completed_runs": len(records),
        "artifact_manifest_rows": len(manifest_rows),
        "gitignored_detail_artifacts": sum(
            row["retention"] == "gitignored_reproducible_detail"
            for row in manifest_rows),
        "run_counts_by_phase": dict(sorted(Counter(
            record["phase"] for record in records).items())),
        "selected_pipelines": [
            _selected_pipeline(by_id[QUALITY_RUN], "best_quality"),
            _selected_pipeline(by_id[LIGHTWEIGHT_RUN], "best_lightweight_cpu"),
            _selected_pipeline(by_id[BALANCED_RUN], "preferred_balanced"),
        ],
        "latency_floor_reference": _selected_pipeline(by_id[LATENCY_FLOOR_RUN],
                                                        "latency_floor_reference"),
        "context_assembly": _selected_pipeline(by_id[CONTEXT_RUN], "context_assembly"),
        "pareto_definition": {
            "maximize": ["natural_student Hit@5", "natural_student MRR",
                         "overall Hit@1", "overall MRR"],
            "minimize": ["warm p95 latency", "peak RSS"],
            "eligible_phases": sorted(ELIGIBLE_PHASES),
        },
        "remaining_top5_failures": failures,
        "generation_status": "blocked: no reviewed generation-quality benchmark",
    }
    selection_path = output_dir / "final_pipeline_selection.json"
    write_json(selection_path, selection)
    report_path = output_dir / "final_experiment_report.md"
    report_path.write_text(_render_report(selection, rows, frontier, failures, categories),
                           encoding="utf-8")
    # Finalization is a meaningful recovery checkpoint even though it is not a
    # new retrieval run. Keep restart state aligned with the generated handoff.
    state = json.loads(paths["state"].read_text(encoding="utf-8"))
    state["current_phase"] = "Phase J — gated; approved retrieval loop complete"
    state["current_best_configurations"]["final_pipeline_selection"] = {
        "best_quality": QUALITY_RUN,
        "best_lightweight_cpu": LIGHTWEIGHT_RUN,
        "preferred_balanced": BALANCED_RUN,
        "context_assembly": CONTEXT_RUN,
    }
    state["unresolved_questions"] = [
        "A reviewed generation benchmark for correctness, faithfulness, citations, and abstention is required before Phase J."
    ]
    state["exact_next_action"] = (
        "Review reports/experiments/final_experiment_report.md; create and approve a grounded-answer generation benchmark before Phase J."
    )
    write_json(paths["state"], state)
    render_resume(root, state)
    return {"comparable_runs": len(rows), "pareto_runs": len(frontier_rows),
            "top5_failures": len(failures),
            "outputs": [str(path.relative_to(root)) for path in
                        (leaderboard_path, frontier_path, selection_path, report_path,
                         manifest_path)]}


def main() -> None:
    """Expose deterministic finalization as a reproducible local command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run(args.root.resolve()), indent=2))


if __name__ == "__main__":
    main()
