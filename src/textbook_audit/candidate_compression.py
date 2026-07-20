"""Phase A candidate preservation and deterministic compression experiments.

Every selector starts from the same four audited depth-20 source rankings.
Gold annotations travel with candidates solely so evaluation can detect losses;
no selector reads those annotations when clustering, scoring, or truncating.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import time
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .candidate_complementarity import Candidate, _scopes, deduplicate_candidates
from .experiment_tracking import (
    checkpoint_run, create_run_directory, experiment_paths,
    initialize_experiment, read_jsonl as read_run_log, render_resume,
    sha256_file, utc_now, write_json,
)
from .reranker import (
    MergedCandidate, RRF_CONSTANT, SOURCE_RETRIEVERS, _representative,
    load_candidate_rankings,
)
from .retrieval import (BM25, MODEL_NAME, QUERY_PREFIX, load_pages, read_jsonl,
                        stable_ranking, tokenize)


SOURCE_DEPTH = 20
BUDGETS = (8, 10, 15, 20)
RANDOM_SEED = 0

APPROVED_PLAN = [
    {"phase": "A", "name": "candidate preservation and compression", "status": "approved"},
    {"phase": "B", "name": "candidate text representation", "status": "approved after Phase A gate"},
    {"phase": "C", "name": "fusion and reranking logic", "status": "approved after Phase B"},
    {"phase": "D", "name": "local reranker bake-off", "status": "approved with successive stopping"},
    {"phase": "E", "name": "embedding model bake-off", "status": "approved with successive stopping"},
    {"phase": "F", "name": "chunking and multi-granularity retrieval", "status": "approved after Phase E"},
    {"phase": "G", "name": "deterministic query processing", "status": "approved; Gemma separately gated"},
    {"phase": "H", "name": "textbook retrieval specialists", "status": "approved; multimodal model separately gated"},
    {"phase": "I", "name": "context assembly", "status": "approved"},
    {"phase": "J", "name": "answer generation",
     "status": "completed separately; Generation Baseline v1 frozen"},
]


@dataclass(frozen=True)
class CompressionConfig:
    """One preregistered gold-blind candidate-selection configuration."""

    selector: str
    deduplication_threshold: float = 0.8
    rrf_constant: int = RRF_CONSTANT
    source_weights: tuple[tuple[str, float], ...] = ()
    mmr_lambda: float = 0.75
    query_signal_weights: tuple[tuple[str, float], ...] = ()

    @property
    def name(self) -> str:
        """Return a stable human-readable configuration identifier."""
        threshold = f"t{int(round(self.deduplication_threshold * 100)):03d}"
        return f"{self.selector}_{threshold}"

    def as_dict(self) -> dict[str, Any]:
        """Serialize all variables needed to reproduce candidate ordering."""
        return {
            "pipeline_name": self.name,
            "selector": self.selector,
            "source_depth": SOURCE_DEPTH,
            "candidate_budgets": list(BUDGETS),
            "deduplication_threshold": self.deduplication_threshold,
            "rrf_constant": self.rrf_constant,
            "source_weights": dict(self.source_weights),
            "mmr_lambda": self.mmr_lambda,
            "query_signal_weights": dict(self.query_signal_weights),
            "candidate_sources": list(SOURCE_RETRIEVERS),
        }


@dataclass(frozen=True)
class DenseResources:
    """Cached candidate vectors plus the local model used for query vectors."""

    model: Any
    vectors: dict[str, np.ndarray]
    metadata: dict[str, Any]
    model_load_latency_ms: float


@dataclass(frozen=True)
class QueryContext:
    """Gold-free query signals shared by query-aware compression selectors."""

    question: str
    query_embedding: np.ndarray
    encode_latency_ms: float
    candidate_vectors: dict[str, np.ndarray]


def broad_configs() -> list[CompressionConfig]:
    """Return the controlled Phase A1 comparison without a Cartesian sweep."""
    weights = (
        ("page_dense_bge_small", 1.0),
        ("fixed_400_80_bm25", 1.0),
        ("fixed_400_80_dense_bge_small", 0.75),
        ("soft_fusion_hybrid", 1.25),
    )
    return [
        CompressionConfig("plain_rrf"),
        CompressionConfig("weighted_rrf", source_weights=weights),
        CompressionConfig("fixed_source_quotas"),
        CompressionConfig("quotas_then_rrf"),
        CompressionConfig("unique_source_preservation"),
        CompressionConfig("diversity_mmr"),
    ]


def query_relevance_configs() -> list[CompressionConfig]:
    """Return the two controlled A3 selectors after rank-only compression fails."""
    weights = (("source_rrf", 1.0), ("dense_bge_small", 1.0), ("bm25", 1.0))
    return [
        CompressionConfig("query_relevance_fusion", query_signal_weights=weights),
        CompressionConfig("query_relevance_mmr", mmr_lambda=0.85,
                          query_signal_weights=weights),
    ]


def load_cached_dense_resources(root: Path) -> DenseResources:
    """Load pinned BGE-small and join existing page/chunk vectors by candidate ID.

    ``local_files_only`` enforces the Phase A promise that this fallback reuses
    the existing model cache and cannot trigger a network download.
    """
    try:
        import sentence_transformers
        import torch
        import transformers
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("Query-aware compression requires the existing experiment environment") from exc
    started = time.perf_counter()
    model = SentenceTransformer(MODEL_NAME, device="cpu", local_files_only=True)
    load_latency_ms = (time.perf_counter() - started) * 1000
    vectors: dict[str, np.ndarray] = {}
    cache_dir = root / "data/retrieval/cache"
    for book_id, pages in load_pages(root).items():
        units = [
            (pages, cache_dir / f"{book_id}_bge-small-en-v1.5.npz",
             lambda unit: f'{book_id}:pdf:{int(unit["pdf_page_number"])}'),
            (read_jsonl(root / "data/processed" / f"{book_id}_chunks_fixed.jsonl"),
             cache_dir / f"{book_id}_fixed_bge-small-en-v1.5.npz",
             lambda unit: str(unit["chunk_id"])),
            (read_jsonl(root / "data/processed" / f"{book_id}_hierarchy.jsonl"),
             cache_dir / f"{book_id}_hierarchy_paragraph_bge-small-en-v1.5.npz",
             lambda unit: str(unit["chunk_id"])),
        ]
        for records, cache_path, identifier in units:
            if not cache_path.is_file():
                raise FileNotFoundError(f"required cached candidate embeddings are missing: {cache_path}")
            matrix = np.load(cache_path, allow_pickle=False)["embeddings"].astype(np.float32)
            if len(matrix) != len(records):
                raise ValueError(f"cached embedding count does not match processed corpus: {cache_path}")
            for unit, vector in zip(records, matrix):
                vectors[identifier(unit)] = vector
    revision_obj = getattr(getattr(model, "_first_module", lambda: None)(), "auto_model", None)
    revision = getattr(getattr(revision_obj, "config", None), "_commit_hash", None) or "unavailable"
    metadata = {
        "model_name": MODEL_NAME,
        "model_revision": revision,
        "sentence_transformers_version": sentence_transformers.__version__,
        "transformers_version": transformers.__version__,
        "torch_version": torch.__version__,
        "runtime_device": str(model.device),
        "embedding_dimensions": int(next(iter(vectors.values())).shape[0]),
        "normalized": True,
        "query_prefix": QUERY_PREFIX,
        "candidate_embedding_source": "existing validated page/fixed/hierarchy NPZ caches",
        "local_files_only": True,
    }
    return DenseResources(model, vectors, metadata, load_latency_ms)


def build_query_contexts(questions: list[dict[str, Any]],
                         resources: DenseResources) -> dict[str, QueryContext]:
    """Encode every benchmark query locally once while retaining per-query latency."""
    # Warm tokenizer and kernels once; cold model loading is recorded separately.
    resources.model.encode([QUERY_PREFIX + "warm up"], convert_to_numpy=True,
                           normalize_embeddings=True, show_progress_bar=False)
    contexts = {}
    for question in questions:
        started = time.perf_counter()
        vector = resources.model.encode(
            [QUERY_PREFIX + question["question"]], convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False,
        )[0].astype(np.float32)
        latency_ms = (time.perf_counter() - started) * 1000
        contexts[question["question_id"]] = QueryContext(
            question["question"], vector, latency_ms, resources.vectors)
    return contexts


def _merged_clusters(rankings: dict[str, list[Candidate]], config: CompressionConfig) -> list[MergedCandidate]:
    """Normalize four native source lists into evidence clusters with RRF scores."""
    missing = [source for source in SOURCE_RETRIEVERS if source not in rankings]
    if missing:
        raise ValueError("missing required candidate retrievers: " + ", ".join(missing))
    flat = [candidate for source in SOURCE_RETRIEVERS
            for candidate in rankings[source][:SOURCE_DEPTH]]
    output = []
    for cluster in deduplicate_candidates(flat, config.deduplication_threshold):
        source_ranks = tuple(sorted(
            (source, min(item.rank for item in cluster if item.retriever == source))
            for source in {item.retriever for item in cluster}
        ))
        score = sum(1.0 / (config.rrf_constant + rank) for _, rank in source_ranks)
        representative = _representative(cluster)
        output.append(MergedCandidate(
            candidate_id=representative.candidate_id,
            representative=representative,
            members=tuple(cluster),
            source_ranks=source_ranks,
            fusion_score=score,
            matches_gold=any(item.matches_gold for item in cluster),
            matched_evidence=tuple(sorted({evidence for item in cluster
                                           for evidence in item.matched_evidence})),
        ))
    output.sort(key=lambda item: (-item.fusion_score, item.candidate_id))
    return output


def _cached_clusters(question_id: str,
                     rankings: dict[tuple[str, str], list[Candidate]],
                     config: CompressionConfig,
                     cache: dict[tuple[str, float, int], list[MergedCandidate]]) -> list[MergedCandidate]:
    """Reuse text-heavy deduplication across selectors sharing a threshold."""
    key = (question_id, config.deduplication_threshold, config.rrf_constant)
    if key not in cache:
        cache[key] = _merged_clusters(
            {source: rankings[question_id, source] for source in SOURCE_RETRIEVERS},
            config,
        )
    return cache[key]


def _weighted_order(clusters: list[MergedCandidate], config: CompressionConfig) -> list[MergedCandidate]:
    """Apply fixed source weights to RRF without consulting benchmark labels."""
    weights = dict(config.source_weights)
    scored = []
    for candidate in clusters:
        score = sum(weights.get(source, 1.0) / (config.rrf_constant + rank)
                    for source, rank in candidate.source_ranks)
        scored.append(replace(candidate, fusion_score=score))
    return sorted(scored, key=lambda item: (-item.fusion_score, item.candidate_id))


def _source_order(clusters: list[MergedCandidate], source: str) -> list[MergedCandidate]:
    """Order evidence clusters by their native position in one source list."""
    relevant = [item for item in clusters if source in dict(item.source_ranks)]
    return sorted(relevant, key=lambda item: (dict(item.source_ranks)[source], item.candidate_id))


def _quota_selection(clusters: list[MergedCandidate], budget: int) -> list[MergedCandidate]:
    """Reserve an equal deterministic quota per source, then fill unused slots."""
    source_lists = {source: _source_order(clusters, source) for source in SOURCE_RETRIEVERS}
    base, remainder = divmod(budget, len(SOURCE_RETRIEVERS))
    quotas = {source: base + (index < remainder)
              for index, source in enumerate(SOURCE_RETRIEVERS)}
    selected: list[MergedCandidate] = []
    selected_ids: set[int] = set()

    def add(candidate: MergedCandidate) -> bool:
        """Append one candidate once and report whether selection changed."""
        identity = id(candidate)
        if identity in selected_ids:
            return False
        selected.append(candidate)
        selected_ids.add(identity)
        return True

    for source in SOURCE_RETRIEVERS:
        added = 0
        for candidate in source_lists[source]:
            if add(candidate):
                added += 1
            if added == quotas[source]:
                break
    # Deduplication can make a source quota overlap another source.  Round-robin
    # filling preserves source balance while ensuring the requested pool size.
    rank = 0
    while len(selected) < min(budget, len(clusters)):
        progress = False
        for source in SOURCE_RETRIEVERS:
            candidates = source_lists[source]
            if rank < len(candidates) and add(candidates[rank]):
                progress = True
                if len(selected) == min(budget, len(clusters)):
                    break
        rank += 1
        if not progress and rank >= max((len(items) for items in source_lists.values()), default=0):
            break
    if len(selected) < min(budget, len(clusters)):
        for candidate in clusters:
            add(candidate)
            if len(selected) == min(budget, len(clusters)):
                break
    return selected


@lru_cache(maxsize=None)
def _token_set(text: str) -> frozenset[str]:
    """Cache normalized term sets because MMR compares the same passages often."""
    return frozenset(tokenize(text))


def _token_similarity(left: MergedCandidate, right: MergedCandidate) -> float:
    """Estimate topical redundancy with deterministic token-set Jaccard."""
    a, b = _token_set(left.representative.text), _token_set(right.representative.text)
    return len(a & b) / len(a | b) if a and b else 0.0


def _mmr_selection(clusters: list[MergedCandidate], budget: int,
                   relevance_weight: float) -> list[MergedCandidate]:
    """Greedily balance RRF relevance and lexical evidence diversity."""
    if not 0.0 <= relevance_weight <= 1.0:
        raise ValueError("MMR lambda must be between 0 and 1")
    if not clusters:
        return []
    scores = [item.fusion_score for item in clusters]
    low, high = min(scores), max(scores)
    normalized = {id(item): ((item.fusion_score - low) / (high - low)
                             if high > low else 1.0) for item in clusters}
    remaining = list(clusters)
    selected: list[MergedCandidate] = []
    while remaining and len(selected) < budget:
        def key(candidate: MergedCandidate) -> tuple[float, float, str]:
            """Order MMR candidates by novelty-adjusted relevance and stable ties."""
            redundancy = max((_token_similarity(candidate, item) for item in selected), default=0.0)
            value = relevance_weight * normalized[id(candidate)] - (1.0 - relevance_weight) * redundancy
            return -value, -candidate.fusion_score, candidate.candidate_id
        winner = min(remaining, key=key)
        selected.append(winner)
        remaining.remove(winner)
    return selected


def _query_relevance_order(clusters: list[MergedCandidate], config: CompressionConfig,
                           context: QueryContext) -> list[MergedCandidate]:
    """Fuse source rank, cached dense relevance, and local BM25 candidate rank.

    Every cluster receives the best dense and lexical score of its member
    representations.  This prevents the neutral shortest-unit representative
    choice from hiding a more query-relevant page or paragraph in the same
    evidence cluster.
    """
    if not clusters:
        return []
    members: list[Candidate] = []
    owners: list[int] = []
    for cluster_index, cluster in enumerate(clusters):
        for member in cluster.members:
            members.append(member)
            owners.append(cluster_index)
    lexical_member_scores = BM25(member.text for member in members).scores(context.question)
    lexical = np.full(len(clusters), -math.inf, dtype=np.float64)
    dense = np.full(len(clusters), -math.inf, dtype=np.float64)
    for member_index, (member, owner) in enumerate(zip(members, owners)):
        lexical[owner] = max(lexical[owner], float(lexical_member_scores[member_index]))
        vector = context.candidate_vectors.get(member.candidate_id)
        if vector is None:
            raise ValueError(f"cached embedding is missing for candidate {member.candidate_id}")
        dense[owner] = max(dense[owner], float(vector @ context.query_embedding))
    base_rank = np.arange(1, len(clusters) + 1, dtype=np.int64)
    dense_order = stable_ranking(dense)
    lexical_order = stable_ranking(lexical)
    dense_rank = np.empty(len(clusters), dtype=np.int64); dense_rank[dense_order] = np.arange(1, len(clusters) + 1)
    lexical_rank = np.empty(len(clusters), dtype=np.int64); lexical_rank[lexical_order] = np.arange(1, len(clusters) + 1)
    weights = {"source_rrf": 1.0, "dense_bge_small": 1.0, "bm25": 1.0,
               **dict(config.query_signal_weights)}
    output = []
    for index, candidate in enumerate(clusters):
        score = (
            weights["source_rrf"] / (config.rrf_constant + int(base_rank[index]))
            + weights["dense_bge_small"] / (config.rrf_constant + int(dense_rank[index]))
            + weights["bm25"] / (config.rrf_constant + int(lexical_rank[index]))
        )
        output.append(replace(candidate, fusion_score=score))
    return sorted(output, key=lambda item: (-item.fusion_score, item.candidate_id))


def select_from_clusters(clusters: list[MergedCandidate], config: CompressionConfig,
                         budget: int, context: QueryContext | None = None) -> list[MergedCandidate]:
    """Select from precomputed evidence clusters with one gold-blind method."""
    if budget not in BUDGETS:
        raise ValueError(f"candidate budget must be one of {BUDGETS}")
    if config.selector == "plain_rrf":
        return clusters[:budget]
    if config.selector == "weighted_rrf":
        return _weighted_order(clusters, config)[:budget]
    if config.selector == "fixed_source_quotas":
        return _quota_selection(clusters, budget)
    if config.selector == "quotas_then_rrf":
        selected = _quota_selection(clusters, budget)
        return sorted(selected, key=lambda item: (-item.fusion_score, item.candidate_id))
    if config.selector == "unique_source_preservation":
        unique = []
        for source in SOURCE_RETRIEVERS:
            candidates = [item for item in clusters
                          if len(item.source_ranks) == 1 and item.source_ranks[0][0] == source]
            if candidates:
                unique.append(candidates[0])
        selected = sorted(unique, key=lambda item: (-item.fusion_score, item.candidate_id))
        identities = {id(item) for item in selected}
        selected.extend(item for item in clusters if id(item) not in identities)
        return selected[:budget]
    if config.selector == "diversity_mmr":
        return _mmr_selection(clusters, budget, config.mmr_lambda)
    if config.selector in ("query_relevance_fusion", "query_relevance_mmr"):
        if context is None:
            raise ValueError(f"{config.selector} requires a gold-free query context")
        ordered = _query_relevance_order(clusters, config, context)
        if config.selector == "query_relevance_fusion":
            return ordered[:budget]
        return _mmr_selection(ordered, budget, config.mmr_lambda)
    raise ValueError(f"unknown candidate selector: {config.selector}")


def select_candidates(rankings: dict[str, list[Candidate]], config: CompressionConfig,
                      budget: int, context: QueryContext | None = None) -> list[MergedCandidate]:
    """Cluster native rankings once and apply one gold-blind compression method."""
    return select_from_clusters(_merged_clusters(rankings, config), config, budget, context)


def first_gold_rank(candidates: Iterable[MergedCandidate]) -> int | None:
    """Return the first selected evidence cluster containing accepted evidence."""
    for rank, candidate in enumerate(candidates, 1):
        if candidate.matches_gold:
            return rank
    return None


def metric_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate exact retrieval counts, MRR, and selector latency percentiles."""
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
    return result


def _candidate_dict(candidate: MergedCandidate, rank: int) -> dict[str, Any]:
    """Serialize a selected cluster with every contributing source for audit."""
    representative = candidate.representative
    return {
        "rank": rank,
        "candidate_id": candidate.candidate_id,
        "unit_type": representative.unit_type,
        "book_id": representative.book_id,
        "pdf_pages": list(representative.pdf_pages),
        "textbook_pages": list(representative.textbook_pages),
        "chapter_title": representative.chapter_title,
        "section_title": representative.section_title,
        "source_ranks": dict(candidate.source_ranks),
        "fusion_score": candidate.fusion_score,
        "cluster_member_ids": [item.candidate_id for item in candidate.members],
        "text_snippet": " ".join(representative.text.split())[:500],
        "matches_accepted_evidence": candidate.matches_gold,
        "accepted_evidence_matched": list(candidate.matched_evidence),
    }


def _peak_memory_mb() -> float | None:
    """Read the process peak working set when psutil exposes it on this OS."""
    try:
        import psutil
        info = psutil.Process().memory_info()
        value = getattr(info, "peak_wset", None) or info.rss
        return float(value) / (1024 * 1024)
    except (ImportError, OSError):
        return None


def _directory_size(path: Path) -> int:
    """Count bytes in one immutable run directory after artifacts are written."""
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def evaluate_config(root: Path, benchmark_path: Path, audit_path: Path,
                    questions: list[dict[str, Any]],
                    rankings: dict[tuple[str, str], list[Candidate]],
                    cluster_cache: dict[tuple[str, float, int], list[MergedCandidate]],
                    config: CompressionConfig, run_id: str,
                    decision: str, reason: str, next_action: str,
                    audit_metadata: dict[str, Any],
                    query_contexts: dict[str, QueryContext] | None = None,
                    dense_resources: DenseResources | None = None) -> dict[str, Any]:
    """Evaluate one configuration, write its immutable artifacts, and checkpoint."""
    run_dir = create_run_directory(root, run_id)
    answerable_ids = {question["question_id"] for question in questions
                      if question.get("gold_pdf_pages") and (question.get("gold_answer_span") or "").strip()}
    scopes = _scopes(questions, answerable_ids)
    for difficulty in sorted({question.get("difficulty", "unknown") for question in questions
                              if question["question_id"] in answerable_ids}):
        scopes[f"difficulty:{difficulty}"] = [
            question["question_id"] for question in questions
            if question["question_id"] in answerable_ids
            and question.get("difficulty", "unknown") == difficulty
        ]
    by_id = {question["question_id"]: question for question in questions}
    evaluation_rows: dict[int, dict[str, dict[str, Any]]] = {budget: {} for budget in BUDGETS}
    detail_rows = []
    for question in questions:
        qid = question["question_id"]
        # Evidence equivalence is independent of candidate budget, so compute
        # the expensive full-text clusters once per query/configuration.
        clusters = _cached_clusters(qid, rankings, config, cluster_cache)
        context = query_contexts.get(qid) if query_contexts else None
        for budget in BUDGETS:
            started = time.perf_counter()
            selected = select_from_clusters(clusters, config, budget, context)
            selection_ms = (time.perf_counter() - started) * 1000
            latency_ms = selection_ms + (context.encode_latency_ms if context else 0.0)
            gold_rank = first_gold_rank(selected)
            evaluation_rows[budget][qid] = {
                "answerable": qid in answerable_ids,
                "first_gold_rank": gold_rank,
                "latency_ms": latency_ms,
                "candidate_count": len(selected),
            }
            detail_rows.append({
                "question_id": qid,
                "question": question["question"],
                "book_id": question["book_id"],
                "benchmark_slice": question.get("benchmark_slice", "canonical"),
                "query_style": question.get("query_style"),
                "candidate_budget": budget,
                "selector": config.selector,
                "deduplication_threshold": config.deduplication_threshold,
                "evaluation_status": "answerable" if qid in answerable_ids else "excluded_negative_or_weak_evidence",
                "first_accepted_evidence_rank": gold_rank,
                "candidate_count": len(selected),
                "latency_ms": latency_ms,
                "retrieved_candidates": [_candidate_dict(item, rank)
                                         for rank, item in enumerate(selected, 1)],
            })
    by_budget: dict[str, Any] = {}
    for budget in BUDGETS:
        rows = evaluation_rows[budget]
        overall = metric_block(list(rows.values()))
        slice_metrics = {name: metric_block([rows[qid] for qid in ids])
                         for name, ids in scopes.items()}
        lost = [qid for qid in scopes["all_answerable"]
                if rows[qid]["first_gold_rank"] is None]
        recall_count = len(answerable_ids) - len(lost)
        by_budget[str(budget)] = {
            "candidate_recall": {
                "answerable_questions": len(answerable_ids),
                "count": recall_count,
                "recall": recall_count / len(answerable_ids),
                "lost_evidence_question_ids": lost,
                "required_invariant_satisfied": not lost,
            },
            "overall": overall,
            "slices": slice_metrics,
        }
    lossless = [budget for budget in BUDGETS
                if by_budget[str(budget)]["candidate_recall"]["required_invariant_satisfied"]]
    primary_budget = min(lossless) if lossless else max(BUDGETS)
    primary = by_budget[str(primary_budget)]
    metrics = {
        "run_metadata": {
            "run_id": run_id,
            "phase": "A",
            "configuration": config.as_dict(),
            "primary_budget": primary_budget,
            "source_available_answerable_evidence": len(answerable_ids),
            "selection_uses_gold": False,
            "query_relevance": (dense_resources.metadata if dense_resources else None),
            "evaluation_matcher": "reviewed page/alternative plus >=0.50 contiguous answer-span coverage inherited from candidate audit",
        },
        "by_budget": by_budget,
        "selected_primary_metrics": primary,
    }
    pools_path = run_dir / "candidate_pools.jsonl"
    with pools_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in detail_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    metrics_path = run_dir / "metrics.json"
    config_path = run_dir / "configuration.json"
    write_json(metrics_path, metrics)
    write_json(config_path, config.as_dict())
    peak_memory = _peak_memory_mb()
    overall = primary["overall"]
    canonical = primary["slices"]["canonical"]
    natural = primary["slices"]["natural_student"]
    record = {
        "run_id": run_id,
        "timestamp": utc_now(),
        "phase": "A",
        "parent_run_id": None,
        "changed_variable": "candidate compression selector" if config.deduplication_threshold == 0.8 else "evidence deduplication threshold",
        "configuration": {**config.as_dict(), "primary_budget": primary_budget},
        "random_seed": RANDOM_SEED,
        "input_artifact_versions": {
            "benchmark_sha256": sha256_file(benchmark_path),
            "candidate_audit_sha256": sha256_file(audit_path),
            "candidate_audit_metadata": audit_metadata,
        },
        "model_revisions": {
            "inference_models_used": ([dense_resources.metadata]
                                       if dense_resources else []),
            "upstream_bge_small": audit_metadata.get("dense", {}).get("page", {}).get("model_revision"),
        },
        "metrics": {"overall": overall, "canonical": canonical, "natural_student": natural},
        "latency": {
            "measurement": "selection over precomputed evidence clusters; corpus loading and deduplication excluded",
            "average_ms": overall["average_latency_ms"],
            "p50_ms": overall["p50_latency_ms"],
            "p95_ms": overall["p95_latency_ms"],
            "maximum_ms": overall["maximum_latency_ms"],
            "cold_model_load_ms": (dense_resources.model_load_latency_ms
                                   if dense_resources else None),
        },
        "peak_memory": {"peak_rss_mb": peak_memory, "measurement": "process peak working set"},
        "disk_index_size": {"run_artifacts_bytes": _directory_size(run_dir), "new_index_bytes": 0},
        "candidate_recall": primary["candidate_recall"],
        "decision": decision,
        "concise_reason": reason,
        "output_artifact_paths": [
            str(pools_path.relative_to(root)), str(metrics_path.relative_to(root)),
            str(config_path.relative_to(root)),
        ],
        "reproduce_command": f"temp\\python-x64\\python.exe scripts\\run_candidate_compression.py --stage single --selector {config.selector} --dedup-threshold {config.deduplication_threshold}",
        "runtime_versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "platform": platform.platform(),
            "device": "cpu",
        },
    }
    checkpoint_run(root, record, next_action)
    return {"record": record, "metrics": metrics}


def _preview_config(questions: list[dict[str, Any]], rankings: dict[tuple[str, str], list[Candidate]],
                    config: CompressionConfig,
                    cluster_cache: dict[tuple[str, float, int], list[MergedCandidate]],
                    query_contexts: dict[str, QueryContext] | None = None) -> dict[str, Any]:
    """Evaluate just enough in memory to choose A1 finalists before recording decisions."""
    answerable = [question for question in questions
                  if question.get("gold_pdf_pages") and (question.get("gold_answer_span") or "").strip()]
    clusters_by_question = {
        question["question_id"]: _cached_clusters(
            question["question_id"], rankings, config, cluster_cache)
        for question in answerable
    }
    summary = {}
    for budget in BUDGETS:
        rows = []
        natural_hits = 0
        for question in answerable:
            qid = question["question_id"]
            context = query_contexts.get(qid) if query_contexts else None
            selected = select_from_clusters(clusters_by_question[qid], config, budget, context)
            rank = first_gold_rank(selected)
            rows.append({"answerable": True, "first_gold_rank": rank,
                         "latency_ms": 0.0, "candidate_count": len(selected)})
            if question.get("benchmark_slice") == "natural_student" and rank is not None and rank <= 5:
                natural_hits += 1
        metrics = metric_block(rows)
        recall = sum(row["first_gold_rank"] is not None for row in rows)
        summary[budget] = {"recall": recall, "natural_hit_5_count": natural_hits,
                           "hit_at_1_count": metrics["hit_at_1_count"], "mrr": metrics["mrr"]}
    lossless = [budget for budget in BUDGETS if summary[budget]["recall"] == len(answerable)]
    primary = min(lossless) if lossless else max(BUDGETS)
    return {"config": config, "summary": summary, "primary_budget": primary,
            "lossless": bool(lossless)}


def _finalist_key(preview: dict[str, Any]) -> tuple[Any, ...]:
    """Prefer lossless small pools, then natural quality, Hit@1, and MRR."""
    primary = preview["summary"][preview["primary_budget"]]
    return (
        0 if preview["lossless"] else 1,
        preview["primary_budget"] if preview["lossless"] else -primary["recall"],
        -primary["natural_hit_5_count"],
        -primary["hit_at_1_count"],
        -primary["mrr"],
        preview["config"].name,
    )


def _model_cache_status(root: Path) -> dict[str, Any]:
    """Record approved/cached model state without loading or downloading models."""
    return {
        "bge_small_en_v1_5": {
            "status": "cached",
            "revision": "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        },
        "bge_reranker_base": {
            "status": "cached",
            "revision": "2cfc18c9415c912f9d8155881c133215df768a70",
            "path": str(root / "data/retrieval/cache/models"),
        },
        "new_models_downloaded_in_phase_a": [],
    }


def _run_query_relevance_followup(root: Path, benchmark_path: Path, audit_path: Path,
                                  questions: list[dict[str, Any]],
                                  rankings: dict[tuple[str, str], list[Candidate]],
                                  audit_metadata: dict[str, Any],
                                  cluster_cache: dict[tuple[str, float, int], list[MergedCandidate]]) -> dict[str, Any]:
    """Run A3 query-aware fusion after every rank-only budget loses evidence."""
    resources = load_cached_dense_resources(root)
    contexts = build_query_contexts(questions, resources)
    preliminary = sorted(
        (_preview_config(questions, rankings, config, cluster_cache, contexts)
         for config in query_relevance_configs()),
        key=_finalist_key,
    )
    if any(item["lossless"] for item in preliminary):
        configs = [item["config"] for item in preliminary]
    else:
        # Narrow threshold sensitivity to only the stronger query-aware method;
        # the other method remains as one t080 control.
        best = preliminary[0]["config"]
        other = preliminary[1]["config"]
        configs = [replace(best, deduplication_threshold=value)
                   for value in (0.7, 0.8, 0.9)] + [other]
    # Remove the possible duplicate t080 configuration while preserving order.
    unique: dict[str, CompressionConfig] = {config.name: config for config in configs}
    previews = sorted(
        (_preview_config(questions, rankings, config, cluster_cache, contexts)
         for config in unique.values()),
        key=_finalist_key,
    )
    winner = previews[0] if previews[0]["lossless"] else None
    pending = [f"phase_a_a3_{item['config'].name}" for item in previews]
    initialize_experiment(root, APPROVED_PLAN, pending, _model_cache_status(root))
    completed = {record["run_id"] for record in read_run_log(experiment_paths(root)["runs"])}
    for index, preview in enumerate(previews, 1):
        config = preview["config"]
        run_id = f"phase_a_a3_{config.name}"
        if run_id in completed:
            continue
        primary = preview["summary"][preview["primary_budget"]]
        is_winner = winner is not None and config.name == winner["config"].name
        decision = "retain" if is_winner else "reject"
        reason = (f'Lossless query-aware Phase A pool at budget {preview["primary_budget"]}.'
                  if is_winner else
                  f'Not a lossless Phase A winner; recall {primary["recall"]}/61 at budget {preview["primary_budget"]}.')
        next_action = ("Run the next query-aware Phase A configuration."
                       if index < len(previews) else
                       ("Begin Phase B candidate text representation with the retained lossless pool."
                        if winner else
                        "Retain the uncompressed deduplicated union and report that budget 20 cannot satisfy the invariant."))
        evaluate_config(
            root, benchmark_path, audit_path, questions, rankings, cluster_cache,
            config, run_id, decision, reason, next_action, audit_metadata,
            contexts, resources,
        )
        completed.add(run_id)
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if winner:
        winning_run = f"phase_a_a3_{winner['config'].name}"
        state["current_phase"] = "Phase B — Candidate text representation"
        state["current_best_configurations"] = {
            "phase_a": {
                "run_id": winning_run,
                "pipeline_name": winner["config"].name,
                "candidate_budget": winner["primary_budget"],
                "candidate_recall": "61/61",
            }
        }
        state["retained_configurations"] = [winner["config"].name]
        state["exact_next_action"] = (
            "Run Phase B page and chunk representation experiments using the retained Phase A pool."
        )
    else:
        state["exact_next_action"] = (
            "Implement and measure the uncompressed deduplicated-union fallback; do not start reranking."
        )
    write_json(state_path, state)
    render_resume(root, state)
    return {
        "stage": "a3",
        "winner": winner["config"].name if winner else None,
        "winner_budget": winner["primary_budget"] if winner else None,
        "best_recall": previews[0]["summary"][previews[0]["primary_budget"]]["recall"],
        "model": resources.metadata,
        "cold_model_load_ms": resources.model_load_latency_ms,
    }


def _run_uncompressed_fallback(root: Path, benchmark_path: Path, audit_path: Path,
                               questions: list[dict[str, Any]],
                               rankings: dict[tuple[str, str], list[Candidate]],
                               audit_metadata: dict[str, Any]) -> dict[str, Any]:
    """Retain every deduplicated source cluster when budget-20 cannot be lossless."""
    config = CompressionConfig("uncompressed_union")
    run_id = "phase_a_a4_uncompressed_union_t080"
    initialize_experiment(root, APPROVED_PLAN, [run_id], _model_cache_status(root))
    existing = {record["run_id"]: record
                for record in read_run_log(experiment_paths(root)["runs"])}
    if run_id in existing:
        record = existing[run_id]
        return {"stage": "a4", "winner": config.name,
                "candidate_recall": record["candidate_recall"],
                "pool_statistics": record["configuration"].get("pool_statistics")}
    run_dir = create_run_directory(root, run_id)
    answerable_ids = {question["question_id"] for question in questions
                      if question.get("gold_pdf_pages") and (question.get("gold_answer_span") or "").strip()}
    scopes = _scopes(questions, answerable_ids)
    for difficulty in sorted({question.get("difficulty", "unknown") for question in questions
                              if question["question_id"] in answerable_ids}):
        scopes[f"difficulty:{difficulty}"] = [
            question["question_id"] for question in questions
            if question["question_id"] in answerable_ids
            and question.get("difficulty", "unknown") == difficulty
        ]
    rows: dict[str, dict[str, Any]] = {}
    details = []
    pool_sizes = []
    for question in questions:
        qid = question["question_id"]
        started = time.perf_counter()
        clusters = _merged_clusters(
            {source: rankings[qid, source] for source in SOURCE_RETRIEVERS}, config)
        latency_ms = (time.perf_counter() - started) * 1000
        pool_sizes.append(len(clusters))
        rank = first_gold_rank(clusters)
        rows[qid] = {"answerable": qid in answerable_ids,
                     "first_gold_rank": rank, "latency_ms": latency_ms,
                     "candidate_count": len(clusters)}
        details.append({
            "question_id": qid, "question": question["question"],
            "book_id": question["book_id"],
            "benchmark_slice": question.get("benchmark_slice", "canonical"),
            "query_style": question.get("query_style"),
            "candidate_budget": "all_deduplicated_clusters",
            "selector": config.selector,
            "deduplication_threshold": config.deduplication_threshold,
            "evaluation_status": "answerable" if qid in answerable_ids else "excluded_negative_or_weak_evidence",
            "first_accepted_evidence_rank": rank,
            "candidate_count": len(clusters),
            "latency_ms": latency_ms,
            "retrieved_candidates": [_candidate_dict(item, position)
                                     for position, item in enumerate(clusters, 1)],
        })
    overall = metric_block(list(rows.values()))
    slice_metrics = {name: metric_block([rows[qid] for qid in ids])
                     for name, ids in scopes.items()}
    lost = [qid for qid in scopes["all_answerable"]
            if rows[qid]["first_gold_rank"] is None]
    recall = {
        "answerable_questions": len(answerable_ids),
        "count": len(answerable_ids) - len(lost),
        "recall": (len(answerable_ids) - len(lost)) / len(answerable_ids),
        "lost_evidence_question_ids": lost,
        "required_invariant_satisfied": not lost,
    }
    pool_statistics = {
        "minimum": min(pool_sizes),
        "average": statistics.fmean(pool_sizes),
        "p50": float(np.percentile(pool_sizes, 50)),
        "p95": float(np.percentile(pool_sizes, 95)),
        "maximum": max(pool_sizes),
    }
    metrics = {
        "run_metadata": {
            "run_id": run_id, "phase": "A",
            "configuration": config.as_dict(),
            "selection_uses_gold": False,
            "budget_policy": "retain every cluster after deterministic evidence deduplication",
            "pool_statistics": pool_statistics,
        },
        "candidate_recall": recall,
        "overall": overall,
        "slices": slice_metrics,
    }
    pools_path = run_dir / "candidate_pools.jsonl"
    with pools_path.open("w", encoding="utf-8", newline="\n") as handle:
        for detail in details:
            handle.write(json.dumps(detail, ensure_ascii=False) + "\n")
    metrics_path = run_dir / "metrics.json"
    config_path = run_dir / "configuration.json"
    write_json(metrics_path, metrics)
    write_json(config_path, {**config.as_dict(), "candidate_budgets": "all",
                             "pool_statistics": pool_statistics})
    record = {
        "run_id": run_id, "timestamp": utc_now(), "phase": "A",
        "parent_run_id": "phase_a_a3_query_relevance_mmr_t070",
        "changed_variable": "candidate budget fallback",
        "configuration": {**config.as_dict(), "candidate_budgets": "all",
                          "pool_statistics": pool_statistics},
        "random_seed": RANDOM_SEED,
        "input_artifact_versions": {
            "benchmark_sha256": sha256_file(benchmark_path),
            "candidate_audit_sha256": sha256_file(audit_path),
            "candidate_audit_metadata": audit_metadata,
        },
        "model_revisions": {"inference_models_used": [],
                            "upstream_bge_small": audit_metadata.get("dense", {}).get("page", {}).get("model_revision")},
        "metrics": {"overall": overall, "canonical": slice_metrics["canonical"],
                    "natural_student": slice_metrics["natural_student"]},
        "latency": {
            "measurement": "per-query full-source evidence clustering and RRF ordering; corpus loading excluded",
            "average_ms": overall["average_latency_ms"],
            "p50_ms": overall["p50_latency_ms"],
            "p95_ms": overall["p95_latency_ms"],
            "maximum_ms": overall["maximum_latency_ms"],
        },
        "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                        "measurement": "process peak working set"},
        "disk_index_size": {"run_artifacts_bytes": _directory_size(run_dir),
                            "new_index_bytes": 0},
        "candidate_recall": recall,
        "decision": "retain" if not lost else "reject",
        "concise_reason": (
            "Only the full deduplicated union preserves every source-available accepted evidence case."
            if not lost else "Even the full source union failed the required evidence invariant."
        ),
        "output_artifact_paths": [str(pools_path.relative_to(root)),
                                  str(metrics_path.relative_to(root)),
                                  str(config_path.relative_to(root))],
        "reproduce_command": "temp\\python-x64\\python.exe scripts\\run_candidate_compression.py --stage a4",
        "runtime_versions": {"python": platform.python_version(),
                             "numpy": np.__version__, "platform": platform.platform(),
                             "device": "cpu"},
    }
    next_action = ("Begin Phase B representation experiments over the lossless full union."
                   if not lost else
                   "Audit the source ranking evidence labels before any further experiment.")
    checkpoint_run(root, record, next_action)
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not lost:
        state["current_phase"] = "Phase B — Candidate text representation"
        state["retained_configurations"] = [config.name]
        state["current_best_configurations"] = {
            "phase_a": {"run_id": run_id, "pipeline_name": config.name,
                        "candidate_budget": "all", "candidate_recall": "61/61",
                        "pool_statistics": pool_statistics}
        }
        state["exact_next_action"] = (
            "Run Phase B representation experiments over every candidate in the lossless deduplicated union."
        )
    write_json(state_path, state)
    render_resume(root, state)
    return {"stage": "a4", "winner": config.name if not lost else None,
            "candidate_recall": recall, "pool_statistics": pool_statistics}


def run_phase_a(root: Path, benchmark_path: Path, audit_path: Path,
                stage: str = "all", selector: str | None = None,
                dedup_threshold: float = 0.8) -> dict[str, Any]:
    """Run controlled A1 narrowing and A2 threshold confirmation with resume."""
    if benchmark_path.name.endswith("_candidates.jsonl"):
        raise ValueError("Use the reviewed retrieval_benchmark_v1.jsonl, never the candidates file")
    if not benchmark_path.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark_path}")
    if not audit_path.is_file():
        raise FileNotFoundError(f"required candidate audit artifact is missing: {audit_path}")
    questions = read_jsonl(benchmark_path)
    rankings, audit_metadata = load_candidate_rankings(root, audit_path, questions)
    cluster_cache: dict[tuple[str, float, int], list[MergedCandidate]] = {}
    if stage == "a3":
        return _run_query_relevance_followup(
            root, benchmark_path, audit_path, questions, rankings,
            audit_metadata, cluster_cache,
        )
    if stage == "a4":
        return _run_uncompressed_fallback(
            root, benchmark_path, audit_path, questions, rankings, audit_metadata,
        )
    configs = broad_configs()
    if stage == "single":
        match = next((item for item in configs if item.selector == selector), None)
        if match is None:
            raise ValueError("--selector must name one registered selector in single mode")
        configs = [replace(match, deduplication_threshold=dedup_threshold)]
    pending = [f"phase_a_a1_{item.name}" for item in configs]
    initialize_experiment(root, APPROVED_PLAN, pending, _model_cache_status(root))
    completed = {record["run_id"] for record in read_run_log(experiment_paths(root)["runs"])}

    if stage in ("all", "a1"):
        previews = sorted((_preview_config(questions, rankings, config, cluster_cache) for config in configs),
                          key=_finalist_key)
        finalists = {item["config"].name for item in previews[:3]}
        for index, preview in enumerate(previews, 1):
            config = preview["config"]
            run_id = f"phase_a_a1_{config.name}"
            if run_id in completed:
                continue
            primary = preview["summary"][preview["primary_budget"]]
            if config.name in finalists:
                decision = "investigate"
                reason = (f'A1 finalist: {primary["recall"]}/61 recall at budget '
                          f'{preview["primary_budget"]}; confirm deduplication sensitivity.')
            else:
                decision = "reject"
                reason = (f'Dominated in the controlled A1 shortlist; best evaluated recall '
                          f'is {primary["recall"]}/61 at the selected budget.')
            next_action = ("Run the next Phase A1 selector." if index < len(previews)
                           else "Run deduplication-threshold confirmation for the three A1 finalists.")
            evaluate_config(root, benchmark_path, audit_path, questions, rankings, cluster_cache,
                            config, run_id, decision, reason, next_action, audit_metadata)
            completed.add(run_id)
        if stage == "a1":
            return {"stage": "a1", "finalists": sorted(finalists)}
    else:
        # When resuming A2 directly, reconstruct the same preregistered A1 choice.
        previews = sorted((_preview_config(questions, rankings, config, cluster_cache) for config in broad_configs()),
                          key=_finalist_key)
        finalists = {item["config"].name for item in previews[:3]}

    if stage in ("all", "a2"):
        base_finalists = [item["config"] for item in previews if item["config"].name in finalists]
        confirmation = [replace(config, deduplication_threshold=threshold)
                        for config in base_finalists for threshold in (0.7, 0.8, 0.9)]
        confirmation_previews = sorted(
            (_preview_config(questions, rankings, config, cluster_cache) for config in confirmation),
            key=_finalist_key,
        )
        winner = confirmation_previews[0]
        if not winner["lossless"]:
            winner_name = None
        else:
            winner_name = winner["config"].name
        a2_pending = [f"phase_a_a2_{item['config'].name}" for item in confirmation_previews]
        initialize_experiment(root, APPROVED_PLAN, a2_pending, _model_cache_status(root))
        completed = {record["run_id"] for record in read_run_log(experiment_paths(root)["runs"])}
        for index, preview in enumerate(confirmation_previews, 1):
            config = preview["config"]
            run_id = f"phase_a_a2_{config.name}"
            if run_id in completed:
                continue
            primary = preview["summary"][preview["primary_budget"]]
            if config.name == winner_name:
                decision = "retain"
                reason = (f'Smallest highest-ranked lossless Phase A pool: 61/61 recall at '
                          f'budget {preview["primary_budget"]}.')
            else:
                decision = "reject"
                reason = (f'Not the Phase A Pareto winner; recall {primary["recall"]}/61 at '
                          f'budget {preview["primary_budget"]}.')
            next_action = ("Run the next Phase A2 confirmation." if index < len(confirmation_previews)
                           else ("Begin Phase B candidate text representation with the retained lossless pool."
                                 if winner_name else
                                 "Investigate an uncompressed fallback because no budget <=20 was lossless."))
            result = evaluate_config(root, benchmark_path, audit_path, questions, rankings, cluster_cache,
                                     config, run_id, decision, reason, next_action, audit_metadata)
            if config.name == winner_name:
                state_path = experiment_paths(root)["state"]
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state["current_best_configurations"] = {
                    "phase_a": {
                        "run_id": run_id,
                        "pipeline_name": config.name,
                        "candidate_budget": preview["primary_budget"],
                        "candidate_recall": result["record"]["candidate_recall"],
                    }
                }
                state["retained_configurations"] = [config.name]
                write_json(state_path, state)
            completed.add(run_id)
        return {
            "stage": "a2",
            "winner": winner_name,
            "winner_budget": winner["primary_budget"] if winner_name else None,
            "winner_summary": winner["summary"][winner["primary_budget"]],
        }
    config = configs[0]
    preview = _preview_config(questions, rankings, config, cluster_cache)
    run_id = f"phase_a_single_{config.name}_{int(time.time())}"
    initialize_experiment(root, APPROVED_PLAN, [run_id], _model_cache_status(root))
    primary = preview["summary"][preview["primary_budget"]]
    decision = "investigate" if preview["lossless"] else "reject"
    return evaluate_config(
        root, benchmark_path, audit_path, questions, rankings, cluster_cache, config, run_id,
        decision, f'Single diagnostic run with {primary["recall"]}/61 candidate recall.',
        "Review the diagnostic run before changing the approved Phase A plan.", audit_metadata,
    )


def build_parser() -> argparse.ArgumentParser:
    """Expose project paths and controlled Phase A stages through a clear CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--candidate-audit", type=Path)
    parser.add_argument("--stage", choices=("all", "a1", "a2", "a3", "a4", "single"), default="all")
    parser.add_argument("--selector", choices=tuple(item.selector for item in broad_configs()))
    parser.add_argument("--dedup-threshold", type=float, default=0.8)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Resolve defaults, execute the selected stage, and print its checkpoint."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    result = run_phase_a(
        root,
        (args.benchmark or root / "data/benchmarks/retrieval_benchmark_v1.jsonl").resolve(),
        (args.candidate_audit or root / "data/retrieval/candidate_complementarity_results.jsonl").resolve(),
        args.stage,
        args.selector,
        args.dedup_threshold,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
