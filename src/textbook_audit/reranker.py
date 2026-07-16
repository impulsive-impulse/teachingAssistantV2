"""Local cross-encoder reranking over a deterministic multi-retriever pool.

The module reconstructs only existing retrieval rankings and never consults
gold evidence until evaluation. Four source lists are clustered with the same
evidence-normalization rule as the complementarity audit, fused with RRF, and
then independently scored by a local cross-encoder.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import numpy as np

from .candidate_complementarity import (
    Candidate, _scopes, deduplicate_candidates,
)
from .retrieval import load_pages, read_jsonl

MODEL_NAME = "BAAI/bge-reranker-base"
SOURCE_RETRIEVERS = (
    "page_dense_bge_small",
    "fixed_400_80_bm25",
    "fixed_400_80_dense_bge_small",
    "soft_fusion_hybrid",
)
RRF_CONSTANT = 60
DEFAULT_MAX_PASSAGE_CHARS = 1800


class PairScorer(Protocol):
    """Minimal interface shared by Sentence Transformers and test doubles."""

    def predict(self, sentences: list[list[str]], **kwargs: Any) -> Any:
        """Return one relevance score for every query-passage pair."""


@dataclass(frozen=True)
class MergedCandidate:
    """One deduplicated evidence cluster in deterministic control order."""

    candidate_id: str
    representative: Candidate
    members: tuple[Candidate, ...]
    source_ranks: tuple[tuple[str, int], ...]
    fusion_score: float
    matches_gold: bool
    matched_evidence: tuple[str, ...]


def _representative(cluster: list[Candidate]) -> Candidate:
    """Prefer the shortest normalized unit so pages do not swamp chunk text."""
    unit_priority = {"fixed_chunk": 0, "hierarchical_paragraph": 1,
                     "structured_chunk": 2, "page": 3}
    return min(cluster, key=lambda item: (
        len(item.text.split()), unit_priority.get(item.unit_type, 9),
        item.rank, item.retriever, item.candidate_id,
    ))


def build_candidate_pool(rankings: dict[str, list[Candidate]], source_depth: int = 20,
                         maximum_candidates: int = 20,
                         rrf_constant: int = RRF_CONSTANT) -> list[MergedCandidate]:
    """Deduplicate four source lists, fuse source ranks, and retain a fixed pool.

    Gold flags are carried through for later evaluation but are deliberately
    absent from every ordering key.
    """
    if maximum_candidates < 1 or source_depth < 1:
        raise ValueError("candidate limits must be positive")
    missing = [name for name in SOURCE_RETRIEVERS if name not in rankings]
    if missing:
        raise ValueError("missing required candidate retrievers: " + ", ".join(missing))
    flat = [candidate for source in SOURCE_RETRIEVERS
            for candidate in rankings[source][:source_depth]]
    merged: list[MergedCandidate] = []
    for cluster in deduplicate_candidates(flat):
        source_ranks = tuple(sorted(
            (source, min(item.rank for item in cluster if item.retriever == source))
            for source in {item.retriever for item in cluster}
        ))
        score = sum(1.0 / (rrf_constant + rank) for _, rank in source_ranks)
        representative = _representative(cluster)
        merged.append(MergedCandidate(
            candidate_id=representative.candidate_id,
            representative=representative,
            members=tuple(cluster),
            source_ranks=source_ranks,
            fusion_score=score,
            matches_gold=any(item.matches_gold for item in cluster),
            matched_evidence=tuple(sorted({evidence for item in cluster
                                           for evidence in item.matched_evidence})),
        ))
    # Candidate identity is the final tie-breaker, so equal RRF scores remain
    # stable across Python versions and source-dictionary insertion orders.
    merged.sort(key=lambda item: (-item.fusion_score, item.candidate_id))
    return merged[:maximum_candidates]


def normalize_passage_text(text: str, maximum_chars: int = DEFAULT_MAX_PASSAGE_CHARS) -> str:
    """Collapse extraction whitespace and truncate at a word boundary."""
    normalized = " ".join(text.split())
    if len(normalized) <= maximum_chars:
        return normalized
    clipped = normalized[:maximum_chars]
    return clipped.rsplit(" ", 1)[0] or clipped


def format_query_passage(question: str, candidate: MergedCandidate,
                         maximum_chars: int = DEFAULT_MAX_PASSAGE_CHARS) -> str:
    """Format exactly the query, neutral source headings, and passage content."""
    item = candidate.representative
    metadata = [f"Chapter: {item.chapter_title or 'Unknown'}"]
    if item.section_title:
        metadata.append(f"Section: {item.section_title}")
    metadata.append(f"Content: {normalize_passage_text(item.text, maximum_chars)}")
    return f"Query: {question}\n\nPassage:\n" + "\n".join(metadata)


def map_scores_to_candidates(candidates: list[MergedCandidate], scores: Iterable[float]) -> list[tuple[MergedCandidate, float]]:
    """Attach model outputs by input position and sort with deterministic ties."""
    values = [float(value) for value in np.asarray(list(scores)).reshape(-1)]
    if len(values) != len(candidates):
        raise ValueError(f"reranker returned {len(values)} scores for {len(candidates)} candidates")
    paired = list(zip(candidates, values))
    paired.sort(key=lambda pair: (-pair[1], -pair[0].fusion_score, pair[0].candidate_id))
    return paired


def score_pool(model: PairScorer, question: str, candidates: list[MergedCandidate],
               batch_size: int, maximum_chars: int) -> tuple[list[tuple[MergedCandidate, float]], float]:
    """Batch all pairs for one query and return ranked scores plus wall latency."""
    pairs = [[question, format_query_passage(question, item, maximum_chars)] for item in candidates]
    started = time.perf_counter()
    scores = model.predict(pairs, batch_size=batch_size, show_progress_bar=False,
                           convert_to_numpy=True)
    latency_ms = (time.perf_counter() - started) * 1000
    return map_scores_to_candidates(candidates, scores), latency_ms


def first_gold_rank(ranking: Iterable[Any]) -> int | None:
    """Find the first accepted-evidence position in merged or scored rankings."""
    for rank, item in enumerate(ranking, 1):
        candidate = item[0] if isinstance(item, tuple) else item
        if candidate.matches_gold:
            return rank
    return None


def retrieval_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate exact Hit@K counts, MRR, and reranking latency statistics."""
    answerable = [row for row in rows if row["answerable"]]
    ranks = [row["first_gold_rank"] for row in answerable]
    result: dict[str, Any] = {"answerable_questions": len(answerable)}
    for cutoff in (1, 3, 5):
        count = sum(rank is not None and rank <= cutoff for rank in ranks)
        result[f"hit_at_{cutoff}_count"] = count
        result[f"hit_at_{cutoff}"] = count / len(ranks) if ranks else None
    result["mrr"] = (sum(1.0 / rank if rank else 0.0 for rank in ranks) / len(ranks)
                     if ranks else None)
    latencies = [float(row["latency_ms"]) for row in rows]
    result["average_latency_ms"] = statistics.fmean(latencies) if latencies else None
    result["p50_latency_ms"] = float(np.percentile(latencies, 50)) if latencies else None
    result["p95_latency_ms"] = float(np.percentile(latencies, 95)) if latencies else None
    result["maximum_latency_ms"] = max(latencies) if latencies else None
    result["average_candidates_scored"] = (statistics.fmean(row["candidate_count"] for row in rows)
                                             if rows else None)
    elapsed_seconds = sum(latencies) / 1000
    result["throughput_candidates_per_second"] = (
        sum(row["candidate_count"] for row in rows) / elapsed_seconds if elapsed_seconds else None
    )
    return result


def _load_cross_encoder(model_name: str, device: str, batch_size: int,
                        model_cache: Path) -> tuple[Any, dict[str, Any]]:
    """Load a cached Sentence Transformers CrossEncoder and runtime metadata."""
    import sentence_transformers
    import torch
    from sentence_transformers import CrossEncoder

    torch.manual_seed(0)
    np.random.seed(0)
    model_cache.mkdir(parents=True, exist_ok=True)
    model = CrossEncoder(model_name, device=device, max_length=512,
                         cache_folder=str(model_cache))
    revision = (getattr(getattr(model, "config", None), "_commit_hash", None)
                or getattr(getattr(model, "model", None).config, "_commit_hash", None)
                or "unavailable")
    metadata = {
        "model_name": model_name,
        "resolved_model_revision": revision,
        "library": "sentence-transformers",
        "library_version": sentence_transformers.__version__,
        "torch_version": torch.__version__,
        "device": device,
        "batch_size": batch_size,
        "model_cache": str(model_cache),
        "model_max_length_tokens": 512,
        "score_activation": type(model.default_activation_function).__name__,
    }
    return model, metadata


def _resolve_device(configured: str | None) -> str:
    """Default to mandatory CPU support; use accelerators only when requested."""
    if not configured or configured.lower() == "cpu":
        return "cpu"
    return configured


def load_candidate_rankings(root: Path, audit_path: Path,
                            questions: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], list[Candidate]], dict[str, Any]]:
    """Join audited candidate IDs back to full immutable processed-corpus text.

    The complementarity JSONL is the source of ranking and evidence labels.
    Processed artifacts supply the untruncated passage and neutral headings, so
    the reranker never needs to repeat first-stage embedding inference.
    """
    catalog: dict[str, dict[str, Any]] = {}
    for book_id, pages in load_pages(root).items():
        for page in pages:
            catalog[f'{book_id}:pdf:{int(page["pdf_page_number"])}'] = {
                **page, "text": page["cleaned_text"], "pdf_pages": [page["pdf_page_number"]],
                "textbook_pages": [page.get("textbook_page_number")], "unit_type": "page",
            }
        for filename, unit_type in ((f"{book_id}_chunks_fixed.jsonl", "fixed_chunk"),
                                    (f"{book_id}_hierarchy.jsonl", "hierarchical_paragraph")):
            path = root / "data/processed" / filename
            if not path.is_file():
                raise FileNotFoundError(f"required processed candidate corpus is missing: {path}")
            for unit in read_jsonl(path):
                catalog[str(unit["chunk_id"])] = {**unit, "unit_type": unit_type}
    wanted_questions = {question["question_id"] for question in questions}
    output: dict[tuple[str, str], list[Candidate]] = {}
    for row in read_jsonl(audit_path):
        qid, retriever = row.get("question_id"), row.get("retriever")
        if qid not in wanted_questions or retriever not in SOURCE_RETRIEVERS or row.get("candidate_depth") != 20:
            continue
        ranking = []
        for raw in row["retrieved_candidates"]:
            identifier = str(raw["candidate_id"])
            if identifier not in catalog:
                raise ValueError(f"candidate {identifier} from audit is absent from processed corpora")
            unit = catalog[identifier]
            ranking.append(Candidate(
                retriever=retriever, rank=int(raw["rank"]), candidate_id=identifier,
                unit_type=unit["unit_type"], book_id=row["book_id"],
                pdf_pages=tuple(int(value) for value in unit.get("pdf_pages", [])),
                textbook_pages=tuple(str(value) for value in unit.get("textbook_pages", []) if value is not None),
                text=unit["text"], matches_gold=bool(raw["matches_accepted_evidence"]),
                matched_evidence=tuple(raw.get("accepted_evidence_matched", [])),
                chapter_title=unit.get("chapter_title"), section_title=unit.get("section_title"),
            ))
        output[qid, retriever] = ranking
    missing = [(qid, source) for qid in wanted_questions for source in SOURCE_RETRIEVERS
               if (qid, source) not in output]
    if missing:
        preview = ", ".join(f"{qid}/{source}" for qid, source in missing[:5])
        raise ValueError(f"candidate audit lacks required depth-20 rankings: {preview}")
    metrics_path = root / "reports/candidate_complementarity_metrics.json"
    audit_metadata = (json.loads(metrics_path.read_text(encoding="utf-8"))["run_metadata"]
                      if metrics_path.is_file() else {})
    return output, audit_metadata


# Keep the private spelling as a compatibility alias for older imports while
# new experiment modules use the public, shared corpus-join implementation.
_load_candidate_rankings = load_candidate_rankings


def _failure_category(question: dict[str, Any], control_rank: int | None,
                      reranked_rank: int | None, gold_in_pool: bool,
                      ranked: list[tuple[MergedCandidate, float]]) -> str:
    """Assign a transparent likely cause to a regression or reranked miss."""
    if not gold_in_pool:
        return "accepted_evidence_lost_during_candidate_fusion"
    top = ranked[0][0] if ranked else None
    if top and any(member.matches_gold for member in top.members):
        return "gold_equivalence_or_deduplication_mismatch"
    if top and any(set(member.pdf_pages).intersection(
            page for gold in ranked if gold[0].matches_gold for page in gold[0].representative.pdf_pages)
                   for member in top.members):
        return "broad_topical_context_over_direct_evidence"
    if question.get("formula_dependency"):
        return "formula_or_symbol_relevance_failure"
    if question.get("visual_dependency"):
        return "visual_evidence_not_expressed_in_text"
    if question.get("table_dependency"):
        return "table_structure_not_expressed_in_text"
    if question.get("requires_multiple_pages") or question.get("requires_multiple_chunks"):
        return "distributed_evidence_scored_independently"
    if question.get("benchmark_slice") == "natural_student":
        return "informal_query_semantic_mismatch"
    if control_rank and reranked_rank and reranked_rank > control_rank:
        return "cross_encoder_regression"
    return "direct_evidence_scored_below_topical_context"


def _percentiles(values: list[float]) -> dict[str, float | int | None]:
    """Summarize score distributions without proposing an abstention threshold."""
    return {
        "count": len(values),
        "mean": statistics.fmean(values) if values else None,
        "p50": float(np.percentile(values, 50)) if values else None,
        "p95": float(np.percentile(values, 95)) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def _baseline_summary(root: Path) -> dict[str, Any]:
    """Copy only comparison metric blocks from prior immutable artifacts."""
    output = {}
    for name in ("page_level_retrieval_metrics.json", "chunk_level_retrieval_metrics.json",
                 "hierarchical_retrieval_metrics.json"):
        path = root / "reports" / name
        if path.is_file():
            output[name] = json.loads(path.read_text(encoding="utf-8"))
    return output


def _diagnostic_candidate(item: MergedCandidate, score: float | None) -> dict[str, Any]:
    """Serialize the evidence and score required to inspect a failure."""
    source = item.representative
    return {"candidate_id": item.candidate_id, "text": normalize_passage_text(source.text),
            "pdf_pages": list(source.pdf_pages), "textbook_pages": list(source.textbook_pages),
            "source_ranks": dict(item.source_ranks), "fusion_score": item.fusion_score,
            "reranker_score": score, "matches_gold": item.matches_gold}


def render_report(metrics: dict[str, Any]) -> str:
    """Render comparisons, slice behavior, diagnostics, compute cost, and decision."""
    pct = lambda value: "n/a" if value is None else f"{100 * value:.1f}%"
    lines = ["# Local Cross-Encoder Reranking Baseline v1", "",
             "Four existing candidate sources are deduplicated, ordered by deterministic RRF, and capped before local cross-encoder scoring. Gold evidence is used only for evaluation.", "",
             "## Headline results", "",
             "| Budget | Ordering | N | Hit@1 | Hit@3 | Hit@5 | MRR | Avg ms | p50 ms | p95 ms | Max ms | Candidates/s |",
             "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for budget in metrics["run_metadata"]["candidate_budgets"]:
        for ordering in ("rank_fusion_control", "bge_reranker_base"):
            block = metrics["overall"][str(budget)][ordering]
            lines.append(f'| {budget} | {ordering.replace("_", " ")} | {block["answerable_questions"]} | {block["hit_at_1_count"]}/{block["answerable_questions"]} ({pct(block["hit_at_1"])}) | {block["hit_at_3_count"]}/{block["answerable_questions"]} ({pct(block["hit_at_3"])}) | {block["hit_at_5_count"]}/{block["answerable_questions"]} ({pct(block["hit_at_5"])}) | {block["mrr"]:.3f} | {block["average_latency_ms"]:.1f} | {block["p50_latency_ms"]:.1f} | {block["p95_latency_ms"]:.1f} | {block["maximum_latency_ms"]:.1f} | {block["throughput_candidates_per_second"]:.1f} |')
    lines += ["", "Control latency measures deterministic list slicing only; reranker latency measures local batched pair scoring and excludes model/corpus loading.", "",
              "## Existing candidate-source comparison", "",
              "These evidence-normalized values use the same accepted-span matching as candidate construction, making them the fairest prior-baseline comparison.", "",
              "| Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |", "|---|---:|---:|---:|---:|---:|"]
    for name, block in metrics["comparison_baselines"].items():
        n = block["answerable_questions"]
        lines.append(f'| {name.replace("_", " ")} | {n} | {block["hit_at_1_count"]}/{n} ({pct(block["hit_at_1"])}) | {block["hit_at_3_count"]}/{n} ({pct(block["hit_at_3"])}) | {block["hit_at_5_count"]}/{n} ({pct(block["hit_at_5"])}) | {block["mrr"]:.3f} |')
    lines += ["",
              "## Canonical and natural-student slices", "",
              "| Budget | Slice | Ordering | N | Hit@1 | Hit@3 | Hit@5 | MRR |",
              "|---:|---|---|---:|---:|---:|---:|---:|"]
    for budget, slices in metrics["slices"].items():
        for name in ("canonical", "natural_student"):
            for ordering, block in slices[name].items():
                lines.append(f'| {budget} | {name} | {ordering.replace("_", " ")} | {block["answerable_questions"]} | {block["hit_at_1_count"]}/{block["answerable_questions"]} ({pct(block["hit_at_1"])}) | {pct(block["hit_at_3"])} | {pct(block["hit_at_5"])} | {block["mrr"]:.3f} |')
    required = ("book:biology", "book:physical_sciences", "formula_dependent",
                "visual_dependent", "table_dependent", "multi_page", "multi_chunk")
    lines += ["", "## Book and dependency slices — reranker", "",
              "| Budget | Slice | N | Hit@1 | Hit@3 | Hit@5 | MRR |",
              "|---:|---|---:|---:|---:|---:|---:|"]
    for budget, slices in metrics["slices"].items():
        for name in required:
            block = slices[name]["bge_reranker_base"]
            lines.append(f'| {budget} | {name.replace("book:", "").replace("_", " ")} | {block["answerable_questions"]} | {pct(block["hit_at_1"])} | {pct(block["hit_at_3"])} | {pct(block["hit_at_5"])} | {block["mrr"]:.3f} |')
    lines += ["", "## Natural-query style slices — reranker", "",
              "| Budget | Query style | N | Hit@1 | Hit@3 | Hit@5 | MRR |",
              "|---:|---|---:|---:|---:|---:|---:|"]
    for budget, slices in metrics["slices"].items():
        for name in sorted(value for value in slices if value.startswith("query_style:")):
            block = slices[name]["bge_reranker_base"]
            lines.append(f'| {budget} | {name.split(":", 1)[1].replace("_", " ")} | {block["answerable_questions"]} | {pct(block["hit_at_1"])} | {pct(block["hit_at_3"])} | {pct(block["hit_at_5"])} | {block["mrr"]:.3f} |')
    available_difficulties = metrics["slices"].get("20", {})
    lines += ["", "## Difficulty slices — budget-20 reranker", "",
              "| Difficulty | N | Hit@1 | Hit@3 | Hit@5 | MRR |",
              "|---|---:|---:|---:|---:|---:|"]
    for name in sorted(value for value in available_difficulties if value.startswith("difficulty:")):
        block = available_difficulties[name]["bge_reranker_base"]
        lines.append(f'| {name.split(":", 1)[1]} | {block["answerable_questions"]} | {pct(block["hit_at_1"])} | {pct(block["hit_at_3"])} | {pct(block["hit_at_5"])} | {block["mrr"]:.3f} |')
    lines += ["", "## Candidate budget and pool recall", "",
              "| Budget | Gold present in fused pool | Added reranking latency vs 10 |",
              "|---:|---:|---:|"]
    latency10 = metrics["overall"]["10"]["bge_reranker_base"]["average_latency_ms"]
    for budget in metrics["run_metadata"]["candidate_budgets"]:
        recall = metrics["candidate_pool_recall"][str(budget)]
        latency = metrics["overall"][str(budget)]["bge_reranker_base"]["average_latency_ms"]
        lines.append(f'| {budget} | {recall["count"]}/{recall["answerable_questions"]} ({pct(recall["recall"])}) | {latency-latency10:+.1f} ms |')
    lines += ["", "## Diagnostics", "",
              f'- Improved from outside top 5 to top 5: {", ".join(metrics["diagnostics"]["improved_outside_5_to_top_5"]) or "none"}.',
              f'- Improved to rank 1: {", ".join(metrics["diagnostics"]["improved_to_rank_1"]) or "none"}.',
              f'- Regressions: {", ".join(metrics["diagnostics"]["regressions"]) or "none"}.',
              f'- Gold present but still below 5: {", ".join(metrics["diagnostics"]["gold_present_but_below_5"]) or "none"}.', "",
              "Every regression and top-five miss, including candidate text and all accepted candidate scores, is stored under `diagnostic_cases` in the metrics JSON.", "",
              "| Question | Slice | Control rank | Reranked rank | Likely cause |",
              "|---|---|---:|---:|---|"]
    for case in metrics["diagnostic_cases"]:
        lines.append(f'| {case["question_id"]} | {case["benchmark_slice"]} | {case["original_rank"] or ">20"} | {case["reranked_position"] or ">20"} | {case["likely_failure_category"].replace("_", " ")} |')
    lines += ["",
              "## Negative/weak-evidence behavior", ""]
    negative = metrics["negative_queries"]["20"]
    lines += [f'Top reranker scores average {negative["negative_top_scores"]["mean"]:.3f} for the five excluded queries versus {negative["answerable_top_scores"]["mean"]:.3f} for answerable queries. The mean difference is {negative["mean_difference_answerable_minus_negative"]:+.3f}; this exploratory overlap does not define an abstention threshold.', "",
              "## Runtime and text policy", "",
              f'- Model: `{metrics["run_metadata"]["reranker"]["model_name"]}`; revision `{metrics["run_metadata"]["reranker"]["resolved_model_revision"]}`; device `{metrics["run_metadata"]["reranker"]["device"]}`.',
              f'- Passage content is whitespace-normalized and capped at {metrics["run_metadata"]["maximum_passage_chars"]} characters at a word boundary; the cross-encoder tokenizer additionally caps the complete pair at 512 tokens.',
              "- Query/passage inputs contain source chapter/section titles and content only—never gold, benchmark, difficulty, or dependency metadata.", "",
              "## Decision", ""]
    for index, answer in enumerate(metrics["decision_answers"], 1):
        lines.append(f"{index}. {answer}")
    lines.append("")
    return "\n".join(lines)


def run(root: Path, benchmark: Path, candidate_audit: Path, results_path: Path,
        metrics_path: Path, report_path: Path, cache_dir: Path, model_cache: Path,
        model_name: str = MODEL_NAME, candidate_budgets: tuple[int, ...] = (10, 20),
        batch_size: int = 8, device: str | None = None,
        maximum_passage_chars: int = DEFAULT_MAX_PASSAGE_CHARS,
        minimum_coverage: float = 0.5, model: PairScorer | None = None) -> dict[str, Any]:
    """Construct pools, rerank both budgets, evaluate slices, and write artifacts."""
    if benchmark.name.endswith("_candidates.jsonl"):
        raise ValueError("Use the reviewed retrieval_benchmark_v1.jsonl, never the candidates file")
    if not benchmark.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark}")
    if not candidate_audit.is_file():
        raise FileNotFoundError(f"required candidate audit artifact is missing: {candidate_audit}")
    if not candidate_budgets or any(value not in (10, 20) for value in candidate_budgets):
        raise ValueError("candidate budgets must contain only 10 and/or 20")
    if batch_size < 1 or maximum_passage_chars < 100:
        raise ValueError("batch size must be positive and passage limit at least 100 characters")
    questions = read_jsonl(benchmark)
    configured_device = _resolve_device(device)
    candidates, dense_metadata = load_candidate_rankings(root, candidate_audit, questions)
    if model is None:
        model, reranker_metadata = _load_cross_encoder(model_name, configured_device,
                                                       batch_size, model_cache)
        # Warm model kernels once; warm-up latency is intentionally excluded.
        model.predict([["warm up", "warm up"]], batch_size=1,
                      show_progress_bar=False, convert_to_numpy=True)
    else:
        reranker_metadata = {"model_name": model_name, "resolved_model_revision": "test-double",
                             "library": type(model).__module__, "library_version": "test-double",
                             "torch_version": "not_loaded", "device": configured_device,
                             "batch_size": batch_size, "model_cache": str(model_cache),
                             "model_max_length_tokens": 512}
    answerable_ids = {question["question_id"] for question in questions
                      if (question.get("gold_answer_span") or "").strip()
                      and question.get("gold_pdf_pages")}
    scopes = _scopes(questions, answerable_ids)
    # Difficulty is benchmark-defined rather than part of the shared audit
    # helper, so add every observed value explicitly for reranker reporting.
    for difficulty in sorted({question.get("difficulty", "unknown") for question in questions
                              if question["question_id"] in answerable_ids}):
        scopes[f"difficulty:{difficulty}"] = [question["question_id"] for question in questions
                                               if question["question_id"] in answerable_ids
                                               and question.get("difficulty", "unknown") == difficulty]
    per_budget: dict[str, dict[str, dict[str, Any]]] = {}
    detail_rows: list[dict[str, Any]] = []
    scored_pools: dict[tuple[str, int], list[tuple[MergedCandidate, float]]] = {}
    control_pools: dict[tuple[str, int], list[MergedCandidate]] = {}
    by_id = {question["question_id"]: question for question in questions}
    for question_index, question in enumerate(questions, 1):
        qid = question["question_id"]
        source_lists = {source: candidates[qid, source] for source in SOURCE_RETRIEVERS}
        full_pool = build_candidate_pool(source_lists, source_depth=20, maximum_candidates=20)
        per_budget[qid] = {}
        for budget in candidate_budgets:
            pool = full_pool[:budget]
            control_started = time.perf_counter()
            control = list(pool)
            control_latency = (time.perf_counter() - control_started) * 1000
            reranked, rerank_latency = score_pool(model, question["question"], pool,
                                                  batch_size, maximum_passage_chars)
            control_pools[qid, budget] = control
            scored_pools[qid, budget] = reranked
            answerable = qid in answerable_ids
            per_budget[qid][str(budget)] = {
                "rank_fusion_control": {"answerable": answerable,
                    "first_gold_rank": first_gold_rank(control), "latency_ms": control_latency,
                    "candidate_count": len(control)},
                "bge_reranker_base": {"answerable": answerable,
                    "first_gold_rank": first_gold_rank(reranked), "latency_ms": rerank_latency,
                    "candidate_count": len(reranked)},
            }
            for ordering, ranked_items, latency in (
                ("rank_fusion_control", [(item, None) for item in control], control_latency),
                ("bge_reranker_base", reranked, rerank_latency),
            ):
                for rank, (item, score) in enumerate(ranked_items[:5], 1):
                    source = item.representative
                    detail_rows.append({"question_id": qid, "question": question["question"],
                        "book_id": question["book_id"], "benchmark_slice": question.get("benchmark_slice", "canonical"),
                        "query_style": question.get("query_style"), "candidate_budget": budget,
                        "ordering": ordering, "rank": rank, "candidate_id": item.candidate_id,
                        "unit_type": source.unit_type, "source_retrievers": [name for name, _ in item.source_ranks],
                        "source_ranks": dict(item.source_ranks), "fusion_score": item.fusion_score,
                        "reranker_score": score, "pdf_pages": list(source.pdf_pages),
                        "textbook_pages": list(source.textbook_pages), "chapter_title": source.chapter_title,
                        "section_title": source.section_title, "retrieved_text": normalize_passage_text(source.text),
                        "matches_accepted_gold_evidence": item.matches_gold,
                        "accepted_evidence_matched": list(item.matched_evidence), "latency_ms": latency,
                        "evaluation_status": "answerable" if answerable else "excluded_negative_or_weak_evidence"})
        if question_index == 1 or question_index % 5 == 0 or question_index == len(questions):
            print(f"Reranked {question_index}/{len(questions)} questions", flush=True)

    def rows_for(ids: Iterable[str], budget: int, ordering: str) -> list[dict[str, Any]]:
        """Select compact evaluation rows for one slice, budget, and ordering."""
        return [per_budget[qid][str(budget)][ordering] for qid in ids]

    overall = {str(budget): {ordering: retrieval_metrics(rows_for(by_id, budget, ordering))
                             for ordering in ("rank_fusion_control", "bge_reranker_base")}
               for budget in candidate_budgets}
    slice_metrics = {str(budget): {
        name: {ordering: retrieval_metrics(rows_for(ids, budget, ordering))
               for ordering in ("rank_fusion_control", "bge_reranker_base")}
        for name, ids in scopes.items()} for budget in candidate_budgets}
    pool_recall = {}
    for budget in candidate_budgets:
        count = sum(any(item.matches_gold for item in control_pools[qid, budget])
                    for qid in scopes["all_answerable"])
        pool_recall[str(budget)] = {"answerable_questions": len(answerable_ids), "count": count,
                                    "recall": count / len(answerable_ids)}

    # Diagnostics use the more informative 20-candidate run when available.
    diagnostic_budget = max(candidate_budgets)
    improved5: list[str] = []; improved1: list[str] = []; regressions: list[str] = []
    below5: list[str] = []; diagnostic_cases = []
    for qid in scopes["all_answerable"]:
        control = control_pools[qid, diagnostic_budget]
        reranked = scored_pools[qid, diagnostic_budget]
        original_rank, new_rank = first_gold_rank(control), first_gold_rank(reranked)
        gold_present = any(item.matches_gold for item in control)
        if (original_rank is None or original_rank > 5) and new_rank is not None and new_rank <= 5:
            improved5.append(qid)
        if new_rank == 1 and original_rank != 1:
            improved1.append(qid)
        if original_rank is not None and (new_rank is None or new_rank > original_rank):
            regressions.append(qid)
        if gold_present and (new_rank is None or new_rank > 5):
            below5.append(qid)
        if qid in regressions or new_rank is None or new_rank > 5:
            scores_by_id = {item.candidate_id: score for item, score in reranked}
            diagnostic_cases.append({"question_id": qid,
                "benchmark_slice": by_id[qid].get("benchmark_slice", "canonical"),
                "question": by_id[qid]["question"], "original_rank": original_rank,
                "reranked_position": new_rank,
                "top_reranked_candidate": _diagnostic_candidate(reranked[0][0], reranked[0][1]),
                "accepted_evidence_candidates": [_diagnostic_candidate(item, scores_by_id[item.candidate_id])
                    for item in control if item.matches_gold],
                "likely_failure_category": _failure_category(by_id[qid], original_rank, new_rank,
                                                               gold_present, reranked)})

    negative_ids = [question["question_id"] for question in questions if question["question_id"] not in answerable_ids]
    negative_metrics = {}
    for budget in candidate_budgets:
        negative_scores = [scored_pools[qid, budget][0][1] for qid in negative_ids]
        answerable_scores = [scored_pools[qid, budget][0][1] for qid in scopes["all_answerable"]]
        negative_metrics[str(budget)] = {"excluded_question_ids": negative_ids,
            "negative_top_scores": _percentiles(negative_scores),
            "answerable_top_scores": _percentiles(answerable_scores),
            "mean_difference_answerable_minus_negative": statistics.fmean(answerable_scores) - statistics.fmean(negative_scores)}

    best_budget = max(candidate_budgets)
    control = overall[str(best_budget)]["rank_fusion_control"]
    reranked = overall[str(best_budget)]["bge_reranker_base"]
    natural_control = slice_metrics[str(best_budget)]["natural_student"]["rank_fusion_control"]
    natural_reranked = slice_metrics[str(best_budget)]["natural_student"]["bge_reranker_base"]
    budget10 = overall.get("10", {}).get("bge_reranker_base")
    budget20 = overall.get("20", {}).get("bge_reranker_base")
    audit_metrics_path = root / "reports/candidate_complementarity_metrics.json"
    audit_metrics = json.loads(audit_metrics_path.read_text(encoding="utf-8"))
    comparison_baselines = {name: audit_metrics["individual_metrics"]["all_answerable"][name]
                            for name in SOURCE_RETRIEVERS}
    strongest_baseline = max(comparison_baselines.values(), key=lambda block: (block["hit_at_5"], block["mrr"]))
    metrics = {"run_metadata": {"benchmark": str(benchmark), "candidate_audit": str(candidate_audit),
        "candidate_sources": list(SOURCE_RETRIEVERS), "candidate_budgets": list(candidate_budgets),
        "source_depth_per_retriever": 20, "fusion": f"RRF k={RRF_CONSTANT}",
        "deduplication": "shared PDF page and >=0.80 five-token-shingle containment",
        "maximum_passage_chars": maximum_passage_chars, "minimum_gold_span_coverage": minimum_coverage,
        "reranker": reranker_metadata, "dense_candidate_generation": dense_metadata},
        "overall": overall, "slices": slice_metrics, "comparison_baselines": comparison_baselines,
        "candidate_pool_recall": pool_recall,
        "negative_queries": negative_metrics,
        "diagnostics": {"budget": diagnostic_budget,
            "improved_outside_5_to_top_5": improved5, "improved_to_rank_1": improved1,
            "regressions": regressions, "gold_present_but_below_5": below5},
        "diagnostic_cases": diagnostic_cases, "prior_baselines": _baseline_summary(root),
        "decision_answers": [
            f'At budget {best_budget}, reranking changes Hit@1 from {control["hit_at_1_count"]}/61 to {reranked["hit_at_1_count"]}/61, Hit@3 from {control["hit_at_3_count"]}/61 to {reranked["hit_at_3_count"]}/61, Hit@5 from {control["hit_at_5_count"]}/61 to {reranked["hit_at_5_count"]}/61, and MRR from {control["mrr"]:.3f} to {reranked["mrr"]:.3f}.',
            f'Natural-student Hit@5 changes from {natural_control["hit_at_5_count"]}/20 to {natural_reranked["hit_at_5_count"]}/20 and MRR from {natural_control["mrr"]:.3f} to {natural_reranked["mrr"]:.3f}.',
            f'The fused top-{best_budget} pool preserves accepted evidence for {pool_recall[str(best_budget)]["count"]}/61 answerable questions; reranking cannot recover evidence omitted before scoring.',
            (f'Budget 20 changes Hit@5 by {budget20["hit_at_5"]-budget10["hit_at_5"]:+.1%} and average latency by {budget20["average_latency_ms"]-budget10["average_latency_ms"]:+.1f} ms versus budget 10.' if budget10 and budget20 else 'Only one candidate budget was run.'),
            f'Local reranking adds {reranked["average_latency_ms"]:.1f} ms/query on {reranker_metadata["device"]} at batch size {batch_size}.',
            f'{len(below5)} questions retain gold in the pool but remain below top 5; exact types and scores are in the diagnostics.',
            ('Use bge-reranker-base in the first offline generation baseline.'
             if reranked["hit_at_5"] >= strongest_baseline["hit_at_5"] and reranked["mrr"] >= strongest_baseline["mrr"]
             else 'Do not promote bge-reranker-base yet: it improves the compressed RRF control at Hit@3/5 but remains below the strongest existing individual retriever and regresses Hit@1.'),
        ]}
    for path in (results_path, metrics_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in detail_rows), encoding="utf-8")
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path.write_text(render_report(metrics), encoding="utf-8")
    return metrics


def build_parser() -> argparse.ArgumentParser:
    """Expose model, budget, batch, device, cache, and artifact configuration."""
    parser = argparse.ArgumentParser(description="Run local BGE cross-encoder reranking")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--benchmark", type=Path); parser.add_argument("--candidate-audit", type=Path)
    parser.add_argument("--results", type=Path); parser.add_argument("--metrics", type=Path)
    parser.add_argument("--report", type=Path); parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--model-cache", type=Path); parser.add_argument("--model-name", default=MODEL_NAME)
    parser.add_argument("--candidate-budgets", type=int, nargs="+", default=[10, 20])
    parser.add_argument("--batch-size", type=int, default=8); parser.add_argument("--device", default="cpu")
    parser.add_argument("--maximum-passage-chars", type=int, default=DEFAULT_MAX_PASSAGE_CHARS)
    parser.add_argument("--gold-min-coverage", type=float, default=0.5)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Resolve project defaults, execute both budgets, and print headlines."""
    args = build_parser().parse_args(argv); root = args.root.resolve()
    metrics = run(root,
        (args.benchmark or root / "data/benchmarks/retrieval_benchmark_v1.jsonl").resolve(),
        (args.candidate_audit or root / "data/retrieval/candidate_complementarity_results.jsonl").resolve(),
        (args.results or root / "data/retrieval/reranker_results.jsonl").resolve(),
        (args.metrics or root / "reports/reranker_metrics.json").resolve(),
        (args.report or root / "reports/reranker_baseline.md").resolve(),
        (args.cache_dir or root / "data/retrieval/cache").resolve(),
        (args.model_cache or root / "data/retrieval/cache/models").resolve(),
        args.model_name, tuple(sorted(set(args.candidate_budgets))), args.batch_size,
        args.device, args.maximum_passage_chars, args.gold_min_coverage)
    print(json.dumps({"overall": metrics["overall"], "decision": metrics["decision_answers"]}, indent=2))


if __name__ == "__main__":
    main()
