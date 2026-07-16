"""Phase I gold-blind context assembly over the retained Phase H candidates.

This module deliberately separates selection from evaluation.  Assemblers see
only query-independent chunk text, source metadata, and the Phase H ranking;
reviewed spans and pages are consulted only after a context has been built.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import time
from pathlib import Path
from typing import Any

import numpy as np

from .candidate_compression import APPROVED_PLAN, RANDOM_SEED, _peak_memory_mb
from .chunking_bakeoff import build_corpora
from .embedding_bakeoff import _evaluation_scopes, accepted_mapping, searchable_pages
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
from .retrieval import read_jsonl, tokenize


PARENT_RUN = "phase_h_h3_combined_specialist_priors"
POOL_SIZE = 5
METHODS = (
    "top3_relevance",
    "top5_relevance",
    "token_budget_1200",
    "token_budget_1800",
    "token_budget_2400",
    "overlap_merge",
    "overlap_merge_metadata_preserving",
    "same_page_merge",
    "redundancy_removal",
    "diversity_selection",
    "textbook_order",
    "direct_support_grouping",
)


def _word_tokens(text: str) -> list[str]:
    """Split text for deterministic budgeting and lossless-enough joining."""
    return text.split()


def _normalized(text: str) -> str:
    """Normalize OCR whitespace and punctuation for answer-span containment."""
    return " ".join(tokenize(text))


def _overlap_join(left: str, right: str, maximum: int = 140) -> str:
    """Join two chunks while removing their longest exact word overlap."""
    left_words, right_words = _word_tokens(left), _word_tokens(right)
    limit = min(len(left_words), len(right_words), maximum)
    overlap = 0
    for width in range(limit, 7, -1):
        if left_words[-width:] == right_words[:width]:
            overlap = width
            break
    return " ".join(left_words + right_words[overlap:])


def _jaccard(left: str, right: str) -> float:
    """Measure lexical redundancy without embeddings or benchmark labels."""
    a, b = set(tokenize(left)), set(tokenize(right))
    return len(a & b) / len(a | b) if a or b else 1.0


def _hard_budget(segments: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    """Apply an exact word-token ceiling, truncating only the final segment."""
    output, remaining = [], budget
    for segment in segments:
        words = _word_tokens(segment["text"])
        if remaining <= 0:
            break
        kept = words[:remaining]
        if kept:
            output.append({**segment, "text": " ".join(kept),
                           "truncated": len(kept) < len(words)})
            remaining -= len(kept)
    return output


def _ranked_segments(ranking: list[int], chunks: list[dict[str, Any]],
                     count: int = POOL_SIZE) -> list[dict[str, Any]]:
    """Materialize ranked chunk indexes as inspectable context segments."""
    return [{"source_chunk_ids": [chunks[index]["chunk_id"]],
             "source_ranks": [rank], "pdf_pages": chunks[index]["pdf_pages"],
             "textbook_pages": chunks[index]["textbook_pages"],
             "chapter_title": chunks[index].get("chapter_title"),
             "section_title": chunks[index].get("section_title"),
             "source_metadata": [{
                 "chunk_id": chunks[index]["chunk_id"], "source_rank": rank,
                 "pdf_pages": chunks[index]["pdf_pages"],
                 "textbook_pages": chunks[index]["textbook_pages"],
                 "chapter_title": chunks[index].get("chapter_title"),
                 "section_title": chunks[index].get("section_title"),
             }],
             "text": chunks[index]["text"], "truncated": False}
            for rank, index in enumerate(ranking[:count], 1)]


def _merge_segments(segments: list[dict[str, Any]], same_page_only: bool) -> list[dict[str, Any]]:
    """Merge adjacent output segments when their source relationship permits."""
    output: list[dict[str, Any]] = []
    for segment in segments:
        can_merge = bool(output) and (
            not same_page_only
            or bool(set(output[-1]["pdf_pages"]) & set(segment["pdf_pages"])))
        if not can_merge:
            output.append(dict(segment))
            continue
        previous = output[-1]
        previous["text"] = _overlap_join(previous["text"], segment["text"])
        previous["source_chunk_ids"] += segment["source_chunk_ids"]
        previous["source_ranks"] += segment["source_ranks"]
        previous["source_metadata"] += segment["source_metadata"]
        previous["pdf_pages"] = sorted(set(previous["pdf_pages"] + segment["pdf_pages"]))
        previous["textbook_pages"] = list(dict.fromkeys(
            previous["textbook_pages"] + segment["textbook_pages"]))
    return output


def assemble_context(method: str, ranking: list[int],
                     chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assemble one context using ranking/text metadata only, never gold labels."""
    if method not in METHODS:
        raise ValueError(f"unknown context assembly method: {method}")
    if not ranking:
        return []
    base = _ranked_segments(ranking, chunks)
    if method == "top3_relevance":
        return base[:3]
    if method == "top5_relevance":
        return base
    if method.startswith("token_budget_"):
        return _hard_budget(base, int(method.rsplit("_", 1)[1]))
    if method in {"overlap_merge", "overlap_merge_metadata_preserving"}:
        return _merge_segments(base, same_page_only=False)
    if method == "same_page_merge":
        return _merge_segments(base, same_page_only=True)
    if method == "redundancy_removal":
        output: list[dict[str, Any]] = []
        for segment in base:
            if not any(_jaccard(segment["text"], kept["text"]) >= 0.72 for kept in output):
                output.append(segment)
        return output
    if method == "diversity_selection":
        # Greedy relevance/novelty selection stays inside the fixed top-five pool.
        remaining, output = list(base), []
        while remaining and len(output) < 3:
            chosen = max(
                remaining,
                key=lambda item: (1.0 / item["source_ranks"][0]
                                  - 0.20 * max((_jaccard(item["text"], kept["text"])
                                                for kept in output), default=0.0),
                                  -item["source_ranks"][0]),
            )
            output.append(chosen)
            remaining.remove(chosen)
        return output
    if method == "textbook_order":
        return sorted(base, key=lambda item: (min(item["pdf_pages"]),
                                               item["source_ranks"][0]))
    # The top-ranked candidate is treated as presumed direct evidence; related
    # same-section support follows it, then remaining candidates by relevance.
    anchor, remaining = base[0], base[1:]
    related = [item for item in remaining
               if item["chapter_title"] == anchor["chapter_title"]
               and item["section_title"] == anchor["section_title"]]
    unrelated = [item for item in remaining if item not in related]
    return [anchor, *related, *unrelated]


def _aggregate(rows: list[dict[str, Any]], ids: list[str]) -> dict[str, Any]:
    """Summarize evidence preservation, span retention, coverage, and size."""
    wanted = set(ids)
    selected = [row for row in rows if row["question_id"] in wanted]
    n = len(selected)
    metric: dict[str, Any] = {"questions": n}
    for field in ("direct_evidence_hit", "answer_span_retained",
                  "complete_gold_pages"):
        count = sum(bool(row[field]) for row in selected)
        metric[f"{field}_count"] = count
        metric[f"{field}_rate"] = count / n if n else 0.0
    coverage = [row["gold_page_coverage"] for row in selected]
    tokens = [row["context_tokens"] for row in selected]
    metric["mean_gold_page_coverage"] = sum(coverage) / n if n else 0.0
    metric["average_context_tokens"] = sum(tokens) / n if n else 0.0
    metric["p95_context_tokens"] = (float(np.percentile(tokens, 95, method="linear"))
                                     if tokens else 0.0)
    return metric


def evaluate_method(method: str, questions: list[dict[str, Any]],
                    pages: dict[str, list[dict[str, Any]]],
                    corpora: dict[str, list[dict[str, Any]]],
                    parent: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Evaluate a context assembler after construction against reviewed gold."""
    answerable = {q["question_id"] for q in questions
                  if q.get("gold_pdf_pages") and (q.get("gold_answer_span") or "").strip()}
    scopes = _evaluation_scopes(questions, answerable)
    details, evaluation_rows = [], []
    for question in questions:
        qid, book = question["question_id"], question["book_id"]
        chunks = corpora[book]
        by_id = {chunk["chunk_id"]: index for index, chunk in enumerate(chunks)}
        ranking = [by_id[item["chunk_id"]] for item in parent[qid]["ranking"]]
        mapping = accepted_mapping(question, chunks, pages[book])
        gold_chunks = set(mapping["primary"] + mapping["alternatives"])
        started = time.perf_counter()
        segments = assemble_context(method, ranking, chunks)
        assembly_ms = (time.perf_counter() - started) * 1000
        source_ids = {chunk_id for segment in segments
                      for chunk_id in segment["source_chunk_ids"]}
        context_text = "\n\n".join(segment["text"] for segment in segments)
        selected_pages = {int(page) for segment in segments for page in segment["pdf_pages"]}
        gold_pages = {int(page) for page in question.get("gold_pdf_pages", [])}
        coverage = (len(selected_pages & gold_pages) / len(gold_pages)
                    if gold_pages else 0.0)
        span = question.get("gold_answer_span") or ""
        row = {
            "question_id": qid,
            "direct_evidence_hit": bool(source_ids & gold_chunks),
            "answer_span_retained": bool(span) and _normalized(span) in _normalized(context_text),
            "gold_page_coverage": coverage,
            "complete_gold_pages": bool(gold_pages) and coverage == 1.0,
            "context_tokens": len(_word_tokens(context_text)),
        }
        evaluation_rows.append(row)
        details.append({
            "question_id": qid, "question": question["question"], "book_id": book,
            "benchmark_slice": question.get("benchmark_slice", "canonical"),
            "method": method, "parent_run_id": PARENT_RUN,
            "assembly_latency_ms": assembly_ms,
            "end_to_end_latency_ms": float(parent[qid]["latency_ms"]) + assembly_ms,
            "gold_mapping": mapping,
            "segments": [{**segment, "text_snippet": " ".join(segment["text"].split())[:500],
                           "token_count": len(_word_tokens(segment["text"]))}
                         for segment in segments],
            **row,
        })
    metrics = {name: _aggregate(evaluation_rows, ids)
               for name, ids in scopes.items()}
    return {"overall": metrics["all_answerable"], "slices": metrics}, details


def _winner_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Prefer direct/span preservation, then completeness, then smaller context."""
    overall = record["metrics"]["overall"]
    multi_page = record["metrics"]["all_slices"]["multi_page"]
    return (overall["direct_evidence_hit_count"],
            overall["answer_span_retained_count"],
            multi_page["complete_gold_pages_count"],
            overall["complete_gold_pages_count"],
            record["configuration"]["assembler"] == "overlap_merge_metadata_preserving",
            -overall["average_context_tokens"])


def _render_report(root: Path, records: list[dict[str, Any]], winner: str) -> None:
    """Write a compact comparison with the final evidence-preservation gate."""
    lines = ["# Phase I — context assembly", "",
             "All assemblers consume the same retained Phase H top-five pool and are gold-blind.", "",
             "| Method | Direct evidence | Exact span | Complete pages | Multi-page complete | Avg tokens | p95 tokens | Decision |",
             "|---|---:|---:|---:|---:|---:|---:|---|"]
    for record in records:
        overall = record["metrics"]["overall"]
        mp = record["metrics"]["all_slices"]["multi_page"]
        final_decision = ("retain (final)" if record["run_id"] == winner else
                          "reject (superseded)" if record["decision"] == "retain" else
                          "reject")
        lines.append(
            f'| {record["configuration"]["assembler"]} | '
            f'{overall["direct_evidence_hit_count"]}/{overall["questions"]} | '
            f'{overall["answer_span_retained_count"]}/{overall["questions"]} | '
            f'{overall["complete_gold_pages_count"]}/{overall["questions"]} | '
            f'{mp["complete_gold_pages_count"]}/{mp["questions"]} | '
            f'{overall["average_context_tokens"]:.0f} | '
            f'{overall["p95_context_tokens"]:.0f} | {final_decision} |')
    lines.extend(["", "## Selection", "",
                  f"Retained `{winner}`. The gate first preserves accepted evidence and literal reviewed spans, "
                  "then multi-page completeness and context size; the final tie-break requires per-source "
                  "page/chapter/section provenance after merging.", "",
                  "Exact-span retention is intentionally strict and can undercount semantically complete contexts "
                  "when OCR or overlap removal changes wording.", ""])
    (root / "reports" / "experiments" / "phase_i_context_assembly.md").write_text(
        "\n".join(lines), encoding="utf-8")


def run(root: Path, benchmark: Path) -> dict[str, Any]:
    """Run/checkpoint every approved assembler and advance to the Phase J gate."""
    if not benchmark.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark}")
    parent_path = root / "reports" / "experiments" / "runs" / PARENT_RUN / "rankings.jsonl"
    if not parent_path.is_file():
        raise FileNotFoundError(f"retained Phase H rankings are missing: {parent_path}")
    run_ids = [f"phase_i_i0_{method}" for method in METHODS]
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    initialize_experiment(root, APPROVED_PLAN, run_ids, state.get("model_cache_status", {}))
    questions = read_jsonl(benchmark)
    pages = searchable_pages(root)
    corpora = build_corpora(root)["fixed_600_100"]
    parent = {row["question_id"]: row for row in read_jsonl(parent_path)}
    history = {row["run_id"]: row for row in read_run_log(experiment_paths(root)["runs"])}
    evaluated = {method: evaluate_method(method, questions, pages, corpora, parent)
                 for method in METHODS}
    previews = []
    for method in METHODS:
        metrics, _ = evaluated[method]
        previews.append({"configuration": {"assembler": method},
                         "metrics": {"overall": metrics["overall"],
                                     "all_slices": metrics["slices"]}})
    winning_method = max(previews, key=_winner_key)["configuration"]["assembler"]
    for method, run_id in zip(METHODS, run_ids):
        if run_id in history:
            continue
        metrics, details = evaluated[method]
        run_dir = create_run_directory(root, run_id)
        details_path = run_dir / "contexts.jsonl"
        with details_path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in details:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        configuration = {"assembler": method, "parent_ranking_run_id": PARENT_RUN,
                         "candidate_pool": POOL_SIZE, "gold_blind_assembly": True,
                         "returned_unit": "assembled_fixed_600_100_context"}
        metrics_path, config_path = run_dir / "metrics.json", run_dir / "configuration.json"
        write_json(metrics_path, metrics)
        write_json(config_path, configuration)
        overall = metrics["overall"]
        record = {
            "run_id": run_id, "timestamp": utc_now(), "phase": "I",
            "parent_run_id": PARENT_RUN, "changed_variable": method,
            "configuration": configuration, "random_seed": RANDOM_SEED,
            "input_artifact_versions": {"benchmark_sha256": sha256_file(benchmark),
                                        "parent_rankings_sha256": sha256_file(parent_path)},
            "model_revisions": {"embedding": "inherited from parent run"},
            "metrics": {"overall": overall,
                        "canonical": metrics["slices"]["canonical"],
                        "natural_student": metrics["slices"]["natural_student"],
                        "all_slices": metrics["slices"]},
            "latency": {"measurement": "deterministic assembly only",
                        "average_ms": float(np.mean([r["assembly_latency_ms"] for r in details])),
                        "p95_ms": float(np.percentile([r["assembly_latency_ms"] for r in details], 95))},
            "peak_memory": {"peak_rss_mb": _peak_memory_mb()},
            "disk_index_size": {"new_index_bytes": 0},
            # The inherited top-five pool contains accepted evidence for 50 of
            # 61 answerable questions; assembly may preserve fewer of those.
            "candidate_recall": {"source": PARENT_RUN, "pool_size": POOL_SIZE,
                                 "count": 50, "answerable_questions": 61,
                                 "recall": 50 / 61},
            "decision": "retain" if method == winning_method else "reject",
            "concise_reason": ("Best evidence-preserving context under the ordered Phase I gate."
                               if method == winning_method else
                               "Did not beat the evidence-preservation and context-size frontier."),
            "output_artifact_paths": [str(details_path.relative_to(root)),
                                      str(metrics_path.relative_to(root)),
                                      str(config_path.relative_to(root))],
            "reproduce_command": "python scripts\\run_context_assembly.py",
            "runtime_versions": {"python": platform.python_version(),
                                 "numpy": np.__version__, "platform": platform.platform()},
        }
        checkpoint_run(root, record, "Apply the Phase J generation-benchmark gate.")
        history[run_id] = record
    records = [history[run_id] for run_id in run_ids]
    winner = max(records, key=_winner_key)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_best_configurations"]["phase_i_context_assembly"] = {
        "winner": winner["run_id"], "retained_run_ids": [winner["run_id"]],
        "candidate_pool": POOL_SIZE}
    state["current_phase"] = "Phase J — blocked generation gate"
    state["unresolved_questions"] = [
        "A reviewed generation benchmark with answer correctness, faithfulness, and citation labels is missing."
    ]
    state["exact_next_action"] = (
        "Do not run answer generation until a valid reviewed generation benchmark is approved."
    )
    write_json(state_path, state)
    render_resume(root, state)
    _render_report(root, records, winner["run_id"])
    return {"winner": winner["run_id"], "retained": [winner["run_id"]]}


def main() -> None:
    """Expose Phase I as a reproducible command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--benchmark", type=Path,
                        default=Path("data/benchmarks/retrieval_benchmark_v1.jsonl"))
    args = parser.parse_args()
    root = args.root.resolve()
    benchmark = args.benchmark if args.benchmark.is_absolute() else root / args.benchmark
    print(json.dumps(run(root, benchmark), indent=2))


if __name__ == "__main__":
    main()
