"""Phase H distributed-evidence set construction from retained rankings.

Selectors consume only the completed child ranking and chunk metadata. Gold
pages are inspected after selection to measure direct-evidence hits and complete
multi-page coverage; they never influence expansion or diversity choices.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path
from typing import Any

import numpy as np

from .candidate_compression import APPROVED_PLAN, RANDOM_SEED, _peak_memory_mb, metric_block
from .chunking_bakeoff import build_corpora
from .embedding_bakeoff import _evaluation_scopes, accepted_mapping, searchable_pages, summarize
from .experiment_tracking import (
    checkpoint_run,
    create_run_directory,
    experiment_paths,
    initialize_experiment,
    read_jsonl as read_run_log,
    render_resume,
    sha256_file,
    utc_now,
    write_json,
)
from .retrieval import read_jsonl


METHODS = (
    "base_top5",
    "neighbor_expansion",
    "same_page_expansion",
    "same_section_expansion",
    "coverage_diversity",
    "multi_stage_distinct_pages",
)
BUDGET = 5
PARENT_RUN = "phase_h_h3_combined_specialist_priors"


def _append_unique(output: list[int], seen: set[int], index: int,
                   budget: int) -> None:
    """Append one candidate index once while respecting a hard evidence budget."""
    if len(output) < budget and index not in seen:
        output.append(index)
        seen.add(index)


def select_evidence(method: str, ranking: list[int],
                    chunks: list[dict[str, Any]], budget: int = BUDGET) -> list[int]:
    """Select an ordered, gold-blind evidence set from one complete ranking."""
    if method not in METHODS:
        raise ValueError(f"unknown evidence selector: {method}")
    if budget <= 0:
        raise ValueError("evidence budget must be positive")
    if method == "base_top5":
        return ranking[:budget]
    by_id = {chunk["chunk_id"]: index for index, chunk in enumerate(chunks)}
    rank_position = {index: rank for rank, index in enumerate(ranking)}
    output: list[int] = []
    seen: set[int] = set()
    if method == "neighbor_expansion":
        for index in ranking:
            _append_unique(output, seen, index, budget)
            for field in ("previous_chunk_id", "next_chunk_id"):
                linked = chunks[index].get(field)
                if linked in by_id:
                    _append_unique(output, seen, by_id[linked], budget)
            if len(output) >= budget:
                break
        return output
    if method in {"same_page_expansion", "same_section_expansion"}:
        for seed in ranking:
            _append_unique(output, seen, seed, budget)
            if method == "same_page_expansion":
                seed_pages = set(chunks[seed]["pdf_pages"])
                related = [index for index in ranking
                           if seed_pages.intersection(chunks[index]["pdf_pages"])]
            else:
                related = [index for index in ranking
                           if chunks[index].get("chapter_title") == chunks[seed].get("chapter_title")
                           and chunks[index].get("section_title") == chunks[seed].get("section_title")]
            for index in related:
                _append_unique(output, seen, index, budget)
            if len(output) >= budget:
                break
        return output
    if method == "multi_stage_distinct_pages":
        covered_pages: set[int] = set()
        for index in ranking:
            pages = {int(page) for page in chunks[index]["pdf_pages"]}
            if not pages.issubset(covered_pages):
                _append_unique(output, seen, index, budget)
                covered_pages.update(pages)
            if len(output) >= budget:
                break
        for index in ranking:
            _append_unique(output, seen, index, budget)
        return output
    # Coverage/diversity uses only source rank and candidate metadata. The
    # weights are fixed before evaluation and favor relevance over novelty.
    candidates = ranking[:20]
    covered_pages: set[int] = set()
    covered_sections: set[tuple[Any, Any]] = set()
    while candidates and len(output) < budget:
        def score(index: int) -> tuple[float, int]:
            """Blend source rank with unseen-page and unseen-section novelty."""
            pages = {int(page) for page in chunks[index]["pdf_pages"]}
            section = (chunks[index].get("chapter_title"),
                       chunks[index].get("section_title"))
            value = (1.0 / (1 + rank_position[index])
                     + 0.08 * len(pages - covered_pages)
                     + 0.04 * (section not in covered_sections))
            return value, -rank_position[index]
        chosen = max(candidates, key=score)
        candidates.remove(chosen)
        _append_unique(output, seen, chosen, budget)
        covered_pages.update(int(page) for page in chunks[chosen]["pdf_pages"])
        covered_sections.add((chunks[chosen].get("chapter_title"),
                              chunks[chosen].get("section_title")))
    return output


def _aggregate_evidence(rows: list[dict[str, Any]], ids: list[str]) -> dict[str, Any]:
    """Aggregate direct-hit, complete-page, coverage, and token-budget metrics."""
    selected = [row for row in rows if row["question_id"] in set(ids)]
    result: dict[str, Any] = {"questions": len(selected)}
    for cutoff in (3, 5):
        direct = [row[f"direct_hit_at_{cutoff}"] for row in selected]
        complete = [row[f"complete_gold_pages_at_{cutoff}"] for row in selected]
        coverage = [row[f"gold_page_coverage_at_{cutoff}"] for row in selected]
        tokens = [row[f"token_count_at_{cutoff}"] for row in selected]
        result[f"direct_hit_at_{cutoff}_count"] = sum(direct)
        result[f"complete_gold_pages_at_{cutoff}_count"] = sum(complete)
        result[f"mean_gold_page_coverage_at_{cutoff}"] = (
            sum(coverage) / len(coverage) if coverage else 0.0)
        result[f"average_tokens_at_{cutoff}"] = sum(tokens) / len(tokens) if tokens else 0.0
        result[f"p95_tokens_at_{cutoff}"] = (float(np.percentile(tokens, 95, method="linear"))
                                                if tokens else 0.0)
    return result


def evaluate_selector(method: str, questions: list[dict[str, Any]],
                      pages: dict[str, list[dict[str, Any]]],
                      corpora: dict[str, list[dict[str, Any]]],
                      parent_details: dict[str, dict[str, Any]]) -> tuple[
                          dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Evaluate one evidence selector against direct chunks and complete gold pages."""
    answerable = {q["question_id"] for q in questions
                  if q.get("gold_pdf_pages") and (q.get("gold_answer_span") or "").strip()}
    scopes = _evaluation_scopes(questions, answerable)
    standard_rows, evidence_rows, details, mapped = {}, [], [], set()
    for question in questions:
        qid, book = question["question_id"], question["book_id"]
        chunks = corpora[book]
        by_id = {chunk["chunk_id"]: index for index, chunk in enumerate(chunks)}
        parent = parent_details[qid]
        ranking = [by_id[item["chunk_id"]] for item in parent["ranking"]]
        mapping = accepted_mapping(question, chunks, pages[book])
        gold_chunks = set(mapping["primary"] + mapping["alternatives"])
        if qid in answerable and mapping["status"] == "mapped":
            mapped.add(qid)
        started = time.perf_counter()
        selected = select_evidence(method, ranking, chunks, BUDGET)
        selection_ms = (time.perf_counter() - started) * 1000
        latency = float(parent["latency_ms"]) + selection_ms
        first = next((rank for rank, index in enumerate(selected, 1)
                      if chunks[index]["chunk_id"] in gold_chunks), None)
        standard_rows[qid] = {"answerable": qid in answerable,
                              "first_gold_rank": first, "latency_ms": latency}
        gold_pages = {int(page) for page in question.get("gold_pdf_pages", [])}
        evidence = {"question_id": qid}
        for cutoff in (3, 5):
            subset = selected[:cutoff]
            selected_pages = {int(page) for index in subset
                              for page in chunks[index]["pdf_pages"]}
            evidence[f"direct_hit_at_{cutoff}"] = any(
                chunks[index]["chunk_id"] in gold_chunks for index in subset)
            coverage = (len(selected_pages & gold_pages) / len(gold_pages)
                        if gold_pages else 0.0)
            evidence[f"gold_page_coverage_at_{cutoff}"] = coverage
            evidence[f"complete_gold_pages_at_{cutoff}"] = bool(gold_pages) and coverage == 1.0
            evidence[f"token_count_at_{cutoff}"] = sum(chunks[index]["token_count"]
                                                        for index in subset)
        evidence_rows.append(evidence)
        details.append({
            "question_id": qid, "question": question["question"], "book_id": book,
            "benchmark_slice": question.get("benchmark_slice", "canonical"),
            "selector": method, "parent_run_id": PARENT_RUN,
            "gold_mapping": mapping, "selection_latency_ms": selection_ms,
            "end_to_end_latency_ms": latency, "first_gold_rank": first,
            "gold_pdf_pages": sorted(gold_pages),
            "selected": [{
                "rank": rank, "chunk_id": chunks[index]["chunk_id"],
                "pdf_pages": chunks[index]["pdf_pages"],
                "textbook_pages": chunks[index]["textbook_pages"],
                "chapter_title": chunks[index].get("chapter_title"),
                "section_title": chunks[index].get("section_title"),
                "token_count": chunks[index]["token_count"],
                "text_snippet": " ".join(chunks[index]["text"].split())[:500],
                "matches_accepted_evidence": chunks[index]["chunk_id"] in gold_chunks,
            } for rank, index in enumerate(selected, 1)],
            **evidence,
        })
    metrics = summarize(standard_rows, scopes)
    evidence_metrics = {
        "all_answerable": _aggregate_evidence(evidence_rows, scopes["all_answerable"]),
        "multi_page": _aggregate_evidence(evidence_rows, scopes["multi_page"]),
        "multi_chunk": _aggregate_evidence(evidence_rows, scopes["multi_chunk"]),
    }
    recall = {"answerable_questions": len(answerable), "count": len(mapped),
              "recall": len(mapped) / len(answerable),
              "missing_question_ids": sorted(answerable - mapped),
              "required_invariant_satisfied": mapped == answerable,
              "selected_direct_evidence_at_5_count":
                  evidence_metrics["all_answerable"]["direct_hit_at_5_count"]}
    return {"ranking": metrics, "evidence_sets": evidence_metrics}, details, recall


def _distributed_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Rank selectors by direct-evidence preservation before page completeness."""
    multi_page = record["metrics"]["evidence_sets"]["multi_page"]
    multi_chunk = record["metrics"]["evidence_sets"]["multi_chunk"]
    overall = record["metrics"]["evidence_sets"]["all_answerable"]
    return (overall["direct_hit_at_5_count"],
            multi_chunk["direct_hit_at_5_count"],
            multi_page["direct_hit_at_5_count"],
            multi_page["complete_gold_pages_at_5_count"],
            multi_page["mean_gold_page_coverage_at_5"],
            -multi_page["average_tokens_at_5"])


def _render_report(root: Path, records: list[dict[str, Any]]) -> None:
    """Render distributed evidence completeness and context-size comparisons."""
    lines = ["# Phase H — distributed evidence-set construction", "",
             "All selectors consume the same complete combined-specialist ranking and are gold-blind.", "",
             "| Selector | Multi-page complete@3/5 | Multi-page direct@5 | Mean page coverage@5 | Multi-chunk direct@5 | Overall direct@5 | Avg tokens@5 | p95 latency | Decision |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for record in records:
        mp = record["metrics"]["evidence_sets"]["multi_page"]
        mc = record["metrics"]["evidence_sets"]["multi_chunk"]
        overall = record["metrics"]["evidence_sets"]["all_answerable"]
        # Screen decisions are immutable history.  Display the later global
        # preservation gate explicitly so the report cannot imply that two
        # production selectors survived.
        if record["configuration"]["selector"] == "base_top5":
            final_decision = "retain (final)"
        elif record["decision"] == "retain":
            final_decision = "reject (final; screen retained)"
        else:
            final_decision = "reject"
        lines.append(
            f'| {record["configuration"]["selector"]} | '
            f'{mp["complete_gold_pages_at_3_count"]}/{mp["complete_gold_pages_at_5_count"]} of {mp["questions"]} | '
            f'{mp["direct_hit_at_5_count"]}/{mp["questions"]} | '
            f'{mp["mean_gold_page_coverage_at_5"]:.3f} | '
            f'{mc["direct_hit_at_5_count"]}/{mc["questions"]} | '
            f'{overall["direct_hit_at_5_count"]}/{overall["questions"]} | '
            f'{overall["average_tokens_at_5"]:.0f} | '
            f'{record["latency"]["p95_ms"]:.1f} ms | {final_decision} |')
    lines.extend(["", "Complete-page coverage uses reviewed PDF pages only during evaluation. "
                  "The benchmark does not label every separately required fact, so multi-chunk completeness "
                  "is reported as direct accepted-evidence coverage rather than claimed full answer sufficiency.", "",
                  "## Final preservation gate", "",
                  "Base top-5 is the production winner. Coverage/diversity gains one complete multi-page case "
                  "but loses four overall direct-evidence hits, so its screen-stage retain label is rejected by "
                  "the required direct-evidence preservation gate.", ""])
    (root / "reports" / "experiments" / "phase_h_distributed_evidence.md").write_text(
        "\n".join(lines), encoding="utf-8")


def run(root: Path, benchmark: Path) -> dict[str, Any]:
    """Evaluate/checkpoint all distributed selectors and retain at most two."""
    if not benchmark.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark}")
    parent_path = root / "reports" / "experiments" / "runs" / PARENT_RUN / "rankings.jsonl"
    if not parent_path.is_file():
        raise FileNotFoundError(f"combined specialist rankings are missing: {parent_path}")
    run_ids = [f"phase_h_h4_{method}" for method in METHODS]
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    initialize_experiment(root, APPROVED_PLAN, run_ids,
                          state.get("model_cache_status", {}))
    questions = read_jsonl(benchmark)
    pages = searchable_pages(root)
    corpora = build_corpora(root)["fixed_600_100"]
    parent_details = {row["question_id"]: row for row in read_jsonl(parent_path)}
    history = {r["run_id"]: r for r in read_run_log(experiment_paths(root)["runs"])}
    evaluated = {}
    for method in METHODS:
        evaluated[method] = evaluate_selector(
            method, questions, pages, corpora, parent_details)
    provisional = []
    for method in METHODS:
        metrics, _, recall = evaluated[method]
        provisional.append({"configuration": {"selector": method},
                            "metrics": {"overall": metrics["ranking"]["overall"],
                                        "evidence_sets": metrics["evidence_sets"]},
                            "candidate_recall": recall})
    winners = {item["configuration"]["selector"]
               for item in sorted(provisional, key=_distributed_key, reverse=True)[:2]}
    control = next(item for item in provisional
                   if item["configuration"]["selector"] == "base_top5")
    for method, run_id in zip(METHODS, run_ids):
        if run_id in history:
            continue
        metrics, details, recall = evaluated[method]
        preview = next(item for item in provisional
                       if item["configuration"]["selector"] == method)
        if method in winners and _distributed_key(preview) > _distributed_key(control):
            decision = "retain"
            reason = "Top-two distributed selector improved multi-page completeness/coverage over base top-5."
        elif method == "base_top5":
            decision = "retain"
            reason = "Control evidence set retained for latency and completeness comparison."
        else:
            decision = "reject"
            reason = "Did not enter the top-two distributed evidence frontier over base top-5."
        run_dir = create_run_directory(root, run_id)
        details_path = run_dir / "evidence_sets.jsonl"
        with details_path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in details:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        configuration = {"pipeline_name": f"combined_specialists_{method}",
                         "selector": method, "candidate_budget": BUDGET,
                         "parent_ranking_run_id": PARENT_RUN,
                         "gold_blind_selection": True, "returned_unit": "fixed_600_100_chunk"}
        metrics_path, config_path = run_dir / "metrics.json", run_dir / "configuration.json"
        write_json(metrics_path, metrics)
        write_json(config_path, configuration)
        ranking = metrics["ranking"]
        overall = ranking["overall"]
        record = {
            "run_id": run_id, "timestamp": utc_now(), "phase": "H",
            "parent_run_id": PARENT_RUN, "changed_variable": method,
            "configuration": configuration, "random_seed": RANDOM_SEED,
            "input_artifact_versions": {"benchmark_sha256": sha256_file(benchmark),
                                        "parent_rankings_sha256": sha256_file(parent_path)},
            "model_revisions": {"embedding": "inherited from parent run"},
            "metrics": {"overall": overall, "canonical": ranking["slices"]["canonical"],
                        "natural_student": ranking["slices"]["natural_student"],
                        "all_slices": ranking["slices"],
                        "evidence_sets": metrics["evidence_sets"]},
            "latency": {"measurement": "parent retrieval plus deterministic evidence selection",
                        "average_ms": overall["average_latency_ms"],
                        "p50_ms": overall["p50_latency_ms"],
                        "p95_ms": overall["p95_latency_ms"],
                        "maximum_ms": overall["maximum_latency_ms"]},
            "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                            "measurement": "process peak working set"},
            "disk_index_size": {"new_index_bytes": 0},
            "candidate_recall": recall, "decision": decision,
            "concise_reason": reason,
            "output_artifact_paths": [str(details_path.relative_to(root)),
                                      str(metrics_path.relative_to(root)),
                                      str(config_path.relative_to(root))],
            "reproduce_command": "python scripts\\run_evidence_sets.py",
            "runtime_versions": {"python": platform.python_version(),
                                 "numpy": np.__version__, "platform": platform.platform()},
        }
        checkpoint_run(root, record, "Select the distributed evidence winner and advance to Phase I.")
        history[run_id] = record
    records = [history[run_id] for run_id in run_ids]
    # Reapply the final preservation invariant even when immutable screen runs
    # were created by an earlier completeness-first selector key.
    best = max(records, key=_distributed_key)
    retained = [best["run_id"]]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_best_configurations"]["phase_h_distributed_evidence"] = {
        "winner": best["run_id"], "retained_run_ids": retained,
        "candidate_budget": BUDGET}
    state["current_phase"] = "Phase I — Context assembly"
    state["unresolved_questions"] = [
        "What is the smallest top-k or token budget that preserves complete accepted evidence?",
        "Should final context order follow relevance, textbook order, or direct-evidence-first grouping?",
    ]
    state["exact_next_action"] = (
        "Use the retained combined-specialist ranking and distributed selector to compare Phase I "
        "top-k, token budgets, merging, redundancy removal, diversity, and ordering."
    )
    write_json(state_path, state)
    render_resume(root, state)
    _render_report(root, records)
    return {"winner": best["run_id"], "retained": retained, "records": records}


def build_parser() -> argparse.ArgumentParser:
    """Create the deterministic distributed-evidence CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--benchmark", type=Path,
                        default=Path("data/benchmarks/retrieval_benchmark_v1.jsonl"))
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run distributed evidence selection and print its winner."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    benchmark = args.benchmark if args.benchmark.is_absolute() else root / args.benchmark
    result = run(root, benchmark)
    print(json.dumps({"winner": result["winner"], "retained": result["retained"]}, indent=2))


if __name__ == "__main__":
    main()
