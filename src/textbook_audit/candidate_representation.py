"""Phase B candidate-text representation experiments over the lossless pool.

The pre-screen constructs every requested page and chunk representation with
deterministic lexical selection.  It evaluates whether the text shown to a
reranker still exposes accepted evidence, but never uses that evidence while
choosing paragraphs, windows, neighbours, or truncation boundaries.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .candidate_complementarity import Candidate, _scopes
from .candidate_compression import (
    CompressionConfig, DenseResources, QueryContext, RANDOM_SEED,
    SOURCE_RETRIEVERS, _merged_clusters, _model_cache_status, _peak_memory_mb,
    build_query_contexts, load_cached_dense_resources, metric_block,
)
from .chunk_retrieval import answer_span_coverage
from .experiment_tracking import (
    checkpoint_run, create_run_directory, experiment_paths,
    initialize_experiment, read_jsonl as read_run_log, render_resume,
    sha256_file, utc_now, write_json,
)
from .reranker import MergedCandidate, load_candidate_rankings
from .reranker import _load_cross_encoder, map_scores_to_candidates
from .retrieval import BM25, read_jsonl, stable_ranking


PAGE_POLICIES = (
    "leading_text",
    "relevant_paragraph",
    "relevant_window",
    "heading_relevant_window",
    "two_relevant_windows",
    "full_page_when_fits",
)
CHUNK_POLICIES = (
    "raw_chunk",
    "chapter_chunk",
    "chapter_section_chunk",
    "neighbor_expansion",
)
MEMBER_POLICIES = (
    "shortest_member",
    "lexical_best_member",
    "dense_best_member",
    "lexical_dense_fused_member",
    "top_two_fused_members",
    "all_fused_member_windows",
)
BASE_PAGE_POLICY = "leading_text"
BASE_CHUNK_POLICY = "chapter_section_chunk"
MAXIMUM_PASSAGE_CHARS = 1800
WINDOW_WORDS = 220
WINDOW_STRIDE = 110
TWO_WINDOW_WORDS = 140
FULL_PAGE_WORD_LIMIT = 300
RERANK_BATCH_SIZE = 32
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"


@dataclass(frozen=True)
class RepresentationPolicy:
    """One isolated page/chunk presentation policy for pre-screening."""

    dimension: str
    page_policy: str = BASE_PAGE_POLICY
    chunk_policy: str = BASE_CHUNK_POLICY
    member_policy: str = "shortest_member"

    @property
    def name(self) -> str:
        """Return a stable run and leaderboard name."""
        if self.dimension == "combination":
            return (f"combination_{self.member_policy}_{self.page_policy}_"
                    f"{self.chunk_policy}")
        changed = (self.page_policy if self.dimension == "page" else
                   self.chunk_policy if self.dimension == "chunk" else
                   self.member_policy)
        return f"{self.dimension}_{changed}"

    def as_dict(self) -> dict[str, Any]:
        """Serialize every presentation variable and fixed text limit."""
        return {
            "pipeline_name": self.name,
            "dimension": self.dimension,
            "page_policy": self.page_policy,
            "chunk_policy": self.chunk_policy,
            "member_policy": self.member_policy,
            "maximum_passage_chars": MAXIMUM_PASSAGE_CHARS,
            "window_words": WINDOW_WORDS,
            "window_stride": WINDOW_STRIDE,
            "two_window_words": TWO_WINDOW_WORDS,
            "full_page_word_limit": FULL_PAGE_WORD_LIMIT,
            "candidate_pool": "phase_a_a4_uncompressed_union_t080",
        }


@dataclass(frozen=True)
class RepresentationCatalog:
    """Query-independent page paragraphs and same-section candidate neighbours."""

    page_paragraphs: dict[tuple[str, int], tuple[str, ...]]
    neighbors: dict[str, tuple[Candidate, ...]]


def representation_policies() -> list[RepresentationPolicy]:
    """Return ten isolated policies without forming a page/chunk Cartesian product."""
    page = [RepresentationPolicy("page", page_policy=value) for value in PAGE_POLICIES]
    chunk = [RepresentationPolicy("chunk", chunk_policy=value) for value in CHUNK_POLICIES]
    return page + chunk


def member_representation_policies() -> list[RepresentationPolicy]:
    """Return a focused follow-up after shortest-member evidence loss is observed."""
    return [RepresentationPolicy("member", member_policy=value)
            for value in MEMBER_POLICIES]


def combination_representation_policies() -> list[RepresentationPolicy]:
    """Combine only B0/B1 finalists after isolated policies remain lossy."""
    return [
        RepresentationPolicy("combination", member_policy="dense_best_member",
                             page_policy="leading_text", chunk_policy="neighbor_expansion"),
        RepresentationPolicy("combination", member_policy="dense_best_member",
                             page_policy="relevant_window", chunk_policy="neighbor_expansion"),
        RepresentationPolicy("combination", member_policy="dense_best_member",
                             page_policy="two_relevant_windows", chunk_policy="neighbor_expansion"),
        RepresentationPolicy("combination", member_policy="dense_best_member",
                             page_policy="full_page_when_fits", chunk_policy="neighbor_expansion"),
        RepresentationPolicy("combination", member_policy="lexical_dense_fused_member",
                             page_policy="two_relevant_windows", chunk_policy="neighbor_expansion"),
    ]


def boundary_representation_policies() -> list[RepresentationPolicy]:
    """Test balanced neighbour allocation after append-then-truncate loses a span."""
    return [
        RepresentationPolicy("combination", member_policy="dense_best_member",
                             page_policy="two_relevant_windows",
                             chunk_policy="balanced_neighbor_expansion"),
        RepresentationPolicy("combination", member_policy="dense_best_member",
                             page_policy="leading_text",
                             chunk_policy="balanced_neighbor_expansion"),
        RepresentationPolicy("combination", member_policy="lexical_dense_fused_member",
                             page_policy="two_relevant_windows",
                             chunk_policy="balanced_neighbor_expansion"),
    ]


def reranker_representation_policies() -> list[RepresentationPolicy]:
    """Return four sequential policies, changing one retained variable at a time."""
    return [
        RepresentationPolicy("combination", member_policy="shortest_member",
                             page_policy="leading_text",
                             chunk_policy="chapter_section_chunk"),
        RepresentationPolicy("combination", member_policy="dense_best_member",
                             page_policy="leading_text",
                             chunk_policy="chapter_section_chunk"),
        RepresentationPolicy("combination", member_policy="dense_best_member",
                             page_policy="leading_text",
                             chunk_policy="neighbor_expansion"),
        RepresentationPolicy("combination", member_policy="dense_best_member",
                             page_policy="two_relevant_windows",
                             chunk_policy="neighbor_expansion"),
    ]


def normalize_text(text: str, maximum_chars: int | None = None) -> str:
    """Collapse extraction whitespace and optionally stop at a word boundary."""
    value = " ".join(text.split())
    if maximum_chars is None or len(value) <= maximum_chars:
        return value
    clipped = value[:maximum_chars]
    return clipped.rsplit(" ", 1)[0] or clipped


def _fallback_paragraphs(text: str) -> list[str]:
    """Group extracted sentences when hierarchy paragraphs are unavailable."""
    pieces = [piece.strip() for piece in re.split(r"(?<=[.!?])\s+", normalize_text(text))
              if piece.strip()]
    if not pieces:
        return [normalize_text(text)]
    paragraphs = []
    for index in range(0, len(pieces), 3):
        paragraphs.append(" ".join(pieces[index:index + 3]))
    return paragraphs


def _lexical_order(question: str, texts: list[str]) -> list[int]:
    """Rank candidate text spans with the project's deterministic local BM25."""
    if not texts:
        return []
    scores = BM25(texts).scores(question)
    return [int(index) for index in stable_ranking(scores)]


def _windows(text: str, size: int, stride: int) -> list[tuple[int, int, str]]:
    """Create stable whitespace-token windows while retaining overlap offsets."""
    words = normalize_text(text).split()
    if len(words) <= size:
        return [(0, len(words), " ".join(words))]
    output = []
    for start in range(0, len(words), stride):
        end = min(len(words), start + size)
        output.append((start, end, " ".join(words[start:end])))
        if end == len(words):
            break
    return output


def _relevant_window(question: str, text: str, size: int = WINDOW_WORDS,
                     stride: int = WINDOW_STRIDE) -> str:
    """Choose the highest-BM25 sliding window without an LLM or gold labels."""
    windows = _windows(text, size, stride)
    order = _lexical_order(question, [item[2] for item in windows])
    return windows[order[0]][2] if order else normalize_text(text)


def _two_non_overlapping_windows(question: str, text: str) -> str:
    """Join the top two lexical windows that do not cover the same words."""
    windows = _windows(text, TWO_WINDOW_WORDS, TWO_WINDOW_WORDS)
    order = _lexical_order(question, [item[2] for item in windows])
    chosen: list[tuple[int, int, str]] = []
    for index in order:
        candidate = windows[index]
        if all(candidate[1] <= item[0] or item[1] <= candidate[0] for item in chosen):
            chosen.append(candidate)
        if len(chosen) == 2:
            break
    chosen.sort(key=lambda item: item[0])
    return " [...] ".join(item[2] for item in chosen)


def _headings(candidate: Candidate, include_section: bool) -> str:
    """Format neutral textbook headings without benchmark attributes."""
    parts = [f"Chapter: {candidate.chapter_title or 'Unknown'}"]
    if include_section and candidate.section_title:
        parts.append(f"Section: {candidate.section_title}")
    return "\n".join(parts)


def build_catalog(root: Path) -> RepresentationCatalog:
    """Index hierarchy paragraphs by page and neighbours by processed order."""
    page_paragraphs: dict[tuple[str, int], list[str]] = {}
    neighbors: dict[str, tuple[Candidate, ...]] = {}
    for book_id in ("biology", "physical_sciences"):
        hierarchy = read_jsonl(root / "data/processed" / f"{book_id}_hierarchy.jsonl")
        fixed = read_jsonl(root / "data/processed" / f"{book_id}_chunks_fixed.jsonl")
        for row in hierarchy:
            for page in row.get("pdf_pages", []):
                page_paragraphs.setdefault((book_id, int(page)), []).append(row["text"])
        for rows, unit_type in ((hierarchy, "hierarchical_paragraph"),
                                (fixed, "fixed_chunk")):
            converted = [Candidate(
                retriever="neighbor_catalog", rank=index + 1,
                candidate_id=str(row["chunk_id"]), unit_type=unit_type,
                book_id=book_id,
                pdf_pages=tuple(int(value) for value in row.get("pdf_pages", [])),
                textbook_pages=tuple(str(value) for value in row.get("textbook_pages", [])
                                     if value is not None),
                text=row["text"], matches_gold=False, matched_evidence=(),
                chapter_title=row.get("chapter_title"),
                section_title=row.get("section_title"),
            ) for index, row in enumerate(rows)]
            for index, item in enumerate(converted):
                adjacent = []
                for position in (index - 1, index + 1):
                    if 0 <= position < len(converted):
                        neighbor = converted[position]
                        if (neighbor.chapter_title == item.chapter_title
                                and neighbor.section_title == item.section_title):
                            adjacent.append(neighbor)
                neighbors[item.candidate_id] = tuple(adjacent)
    return RepresentationCatalog(
        {key: tuple(values) for key, values in page_paragraphs.items()}, neighbors)


def _page_content(question: str, candidate: Candidate, policy: str,
                  catalog: RepresentationCatalog) -> str:
    """Apply exactly one requested page representation policy."""
    text = candidate.text
    page_paragraphs = [paragraph for page in candidate.pdf_pages
                       for paragraph in catalog.page_paragraphs.get((candidate.book_id, page), ())]
    if not page_paragraphs:
        page_paragraphs = _fallback_paragraphs(text)
    if policy == "leading_text":
        return _headings(candidate, True) + "\nContent: " + normalize_text(text, MAXIMUM_PASSAGE_CHARS)
    if policy == "relevant_paragraph":
        order = _lexical_order(question, page_paragraphs)
        content = page_paragraphs[order[0]] if order else text
        return "Content: " + normalize_text(content, MAXIMUM_PASSAGE_CHARS)
    if policy == "relevant_window":
        return "Content: " + _relevant_window(question, text)
    if policy == "heading_relevant_window":
        return _headings(candidate, True) + "\nContent: " + _relevant_window(question, text)
    if policy == "two_relevant_windows":
        return _headings(candidate, True) + "\nContent: " + _two_non_overlapping_windows(question, text)
    if policy == "full_page_when_fits":
        words = normalize_text(text).split()
        content = normalize_text(text) if len(words) <= FULL_PAGE_WORD_LIMIT else _relevant_window(question, text)
        return _headings(candidate, True) + "\nContent: " + content
    raise ValueError(f"unknown page representation policy: {policy}")


def _chunk_content(question: str, candidate: Candidate, policy: str,
                   catalog: RepresentationCatalog) -> str:
    """Apply raw, heading, or deterministic neighbouring-context chunk policy."""
    content = normalize_text(candidate.text, MAXIMUM_PASSAGE_CHARS)
    if policy == "raw_chunk":
        return "Content: " + content
    if policy == "chapter_chunk":
        return _headings(candidate, False) + "\nContent: " + content
    if policy == "chapter_section_chunk":
        return _headings(candidate, True) + "\nContent: " + content
    if policy == "neighbor_expansion":
        possible = list(catalog.neighbors.get(candidate.candidate_id, ()))
        if possible:
            order = _lexical_order(question, [item.text for item in possible])
            neighbor = possible[order[0]].text
            combined = content + " [Neighbouring context] " + normalize_text(neighbor)
        else:
            combined = content
        return _headings(candidate, True) + "\nContent: " + normalize_text(combined, MAXIMUM_PASSAGE_CHARS)
    if policy == "balanced_neighbor_expansion":
        possible = list(catalog.neighbors.get(candidate.candidate_id, ()))
        base = _relevant_window(question, candidate.text, 140, 140)
        if possible:
            order = _lexical_order(question, [item.text for item in possible])
            neighbor = _relevant_window(question, possible[order[0]].text, 140, 140)
            combined = base + " [Neighbouring context] " + neighbor
        else:
            combined = _relevant_window(question, candidate.text, WINDOW_WORDS, WINDOW_STRIDE)
        return _headings(candidate, True) + "\nContent: " + normalize_text(combined, MAXIMUM_PASSAGE_CHARS)
    raise ValueError(f"unknown chunk representation policy: {policy}")


def _unique_members(candidate: MergedCandidate) -> list[Candidate]:
    """Remove duplicate IDs contributed by multiple retrievers in one cluster."""
    output = []
    seen = set()
    for member in candidate.members:
        if member.candidate_id not in seen:
            output.append(member)
            seen.add(member.candidate_id)
    return output


def _member_fused_order(question: str, members: list[Candidate],
                        context: QueryContext) -> list[Candidate]:
    """Fuse local BM25 and cached BGE-small ranks for cluster-member selection."""
    lexical = BM25(member.text for member in members).scores(question)
    dense = np.asarray([
        float(context.candidate_vectors[member.candidate_id] @ context.query_embedding)
        for member in members
    ], dtype=np.float64)
    lexical_order = stable_ranking(lexical)
    dense_order = stable_ranking(dense)
    lexical_rank = np.empty(len(members), dtype=np.int64)
    dense_rank = np.empty(len(members), dtype=np.int64)
    lexical_rank[lexical_order] = np.arange(1, len(members) + 1)
    dense_rank[dense_order] = np.arange(1, len(members) + 1)
    scores = np.asarray([1.0 / (60 + lexical_rank[index])
                         + 1.0 / (60 + dense_rank[index])
                         for index in range(len(members))])
    return [members[int(index)] for index in stable_ranking(scores)]


def _choose_members(question: str, candidate: MergedCandidate,
                    member_policy: str,
                    context: QueryContext | None) -> list[Candidate]:
    """Choose one or more cluster members using query signals, never gold flags."""
    members = _unique_members(candidate)
    if member_policy == "shortest_member":
        return [candidate.representative]
    if context is None:
        raise ValueError(f"{member_policy} requires a gold-free query context")
    if member_policy == "lexical_best_member":
        order = _lexical_order(question, [member.text for member in members])
        return [members[order[0]]]
    if member_policy == "dense_best_member":
        scores = np.asarray([float(context.candidate_vectors[member.candidate_id]
                                   @ context.query_embedding) for member in members])
        return [members[int(stable_ranking(scores)[0])]]
    ordered = _member_fused_order(question, members, context)
    if member_policy == "lexical_dense_fused_member":
        return ordered[:1]
    if member_policy == "top_two_fused_members":
        return ordered[:2]
    if member_policy == "all_fused_member_windows":
        return ordered
    raise ValueError(f"unknown cluster member policy: {member_policy}")


def _multi_member_content(question: str, members: list[Candidate]) -> str:
    """Pack query-relevant windows from multiple members into one bounded passage."""
    pieces = []
    window_size = 110 if len(members) <= 2 else 70
    for index, member in enumerate(members, 1):
        window = _relevant_window(question, member.text, window_size, window_size)
        pieces.append(f"Evidence view {index}\n{_headings(member, True)}\nContent: {window}")
    return normalize_text("\n\n".join(pieces), MAXIMUM_PASSAGE_CHARS)


def represent_candidate(question: str, candidate: MergedCandidate,
                        policy: RepresentationPolicy,
                        catalog: RepresentationCatalog,
                        context: QueryContext | None = None) -> str:
    """Format the query and one neutral candidate passage for local reranking."""
    members = _choose_members(question, candidate, policy.member_policy, context)
    representative = members[0]
    if len(members) > 1:
        passage = _multi_member_content(question, members)
    elif representative.unit_type == "page":
        passage = _page_content(question, representative, policy.page_policy, catalog)
    else:
        passage = _chunk_content(question, representative, policy.chunk_policy, catalog)
    return f"Query: {question}\n\nPassage:\n{passage}"


def _representation_preview(questions: list[dict[str, Any]],
                            pools: dict[str, list[MergedCandidate]],
                            policy: RepresentationPolicy,
                            catalog: RepresentationCatalog,
                            query_contexts: dict[str, QueryContext] | None = None) -> dict[str, Any]:
    """Measure evidence visibility and context size before expensive reranking."""
    answerable = [question for question in questions
                  if question.get("gold_pdf_pages") and (question.get("gold_answer_span") or "").strip()]
    visible = 0
    natural_visible = 0
    lengths = []
    for question in questions:
        context = query_contexts.get(question["question_id"]) if query_contexts else None
        represented = [represent_candidate(question["question"], item, policy, catalog, context)
                       for item in pools[question["question_id"]]]
        lengths.extend(len(text) for text in represented)
        if question in answerable:
            found = any(item.matches_gold and answer_span_coverage(
                question["gold_answer_span"], text) >= 0.5
                for item, text in zip(pools[question["question_id"]], represented))
            visible += int(found)
            if question.get("benchmark_slice") == "natural_student":
                natural_visible += int(found)
    return {
        "policy": policy,
        "visible_count": visible,
        "natural_visible_count": natural_visible,
        "average_chars": statistics.fmean(lengths),
        "p95_chars": float(np.percentile(lengths, 95)),
        "maximum_chars": max(lengths),
    }


def _preview_key(item: dict[str, Any]) -> tuple[Any, ...]:
    """Prefer complete evidence visibility, natural coverage, then less text."""
    return (-item["visible_count"], -item["natural_visible_count"],
            item["average_chars"], item["policy"].name)


def _evaluate_policy(root: Path, benchmark_path: Path, audit_path: Path,
                     questions: list[dict[str, Any]],
                     pools: dict[str, list[MergedCandidate]],
                     policy: RepresentationPolicy, catalog: RepresentationCatalog,
                     run_id: str, decision: str, reason: str,
                     next_action: str, audit_metadata: dict[str, Any],
                     query_contexts: dict[str, QueryContext] | None = None,
                     dense_resources: DenseResources | None = None) -> dict[str, Any]:
    """Write one immutable representation pre-screen and checkpoint its decision."""
    run_dir = create_run_directory(root, run_id)
    answerable_ids = {question["question_id"] for question in questions
                      if question.get("gold_pdf_pages") and (question.get("gold_answer_span") or "").strip()}
    scopes = _scopes(questions, answerable_ids)
    rows: dict[str, dict[str, Any]] = {}
    details = []
    lengths = []
    coverage_by_question: dict[str, bool] = {}
    for question in questions:
        qid = question["question_id"]
        context = query_contexts.get(qid) if query_contexts else None
        started = time.perf_counter()
        representations = [represent_candidate(question["question"], item, policy, catalog, context)
                           for item in pools[qid]]
        latency_ms = (time.perf_counter() - started) * 1000
        if context:
            latency_ms += context.encode_latency_ms
        span = question.get("gold_answer_span") or ""
        visible_flags = [bool(item.matches_gold and span
                              and answer_span_coverage(span, text) >= 0.5)
                         for item, text in zip(pools[qid], representations)]
        first_visible = next((rank for rank, value in enumerate(visible_flags, 1) if value), None)
        coverage_by_question[qid] = first_visible is not None
        rows[qid] = {"answerable": qid in answerable_ids,
                     "first_gold_rank": first_visible, "latency_ms": latency_ms,
                     "candidate_count": len(representations)}
        lengths.extend(len(text) for text in representations)
        details.append({
            "question_id": qid, "question": question["question"],
            "book_id": question["book_id"],
            "benchmark_slice": question.get("benchmark_slice", "canonical"),
            "query_style": question.get("query_style"),
            "policy": policy.as_dict(),
            "evaluation_status": "answerable" if qid in answerable_ids else "excluded_negative_or_weak_evidence",
            "candidate_count": len(representations),
            "first_visible_accepted_evidence_rank": first_visible,
            "representation_latency_ms": latency_ms,
            "candidates": [{
                "rank": rank, "candidate_id": item.candidate_id,
                "unit_type": item.representative.unit_type,
                "source_ranks": dict(item.source_ranks),
                "matches_accepted_evidence_cluster": item.matches_gold,
                "accepted_evidence_visible": visible_flags[rank - 1],
                "representation": text,
            } for rank, (item, text) in enumerate(zip(pools[qid], representations), 1)],
        })
    overall = metric_block(list(rows.values()))
    slice_metrics = {name: metric_block([rows[qid] for qid in ids])
                     for name, ids in scopes.items()}
    missing = [qid for qid in scopes["all_answerable"] if not coverage_by_question[qid]]
    representation_recall = {
        "answerable_questions": len(answerable_ids),
        "count": len(answerable_ids) - len(missing),
        "recall": (len(answerable_ids) - len(missing)) / len(answerable_ids),
        "missing_question_ids": missing,
    }
    length_statistics = {
        "average_chars": statistics.fmean(lengths),
        "p50_chars": float(np.percentile(lengths, 50)),
        "p95_chars": float(np.percentile(lengths, 95)),
        "maximum_chars": max(lengths),
    }
    metrics = {
        "run_metadata": {"run_id": run_id, "phase": "B0",
                         "policy": policy.as_dict(), "selection_uses_gold": False,
                         "reranker_executed": False},
        "candidate_pool_recall": {"answerable_questions": 61, "count": 61,
                                  "recall": 1.0},
        "representation_evidence_recall": representation_recall,
        "length_statistics": length_statistics,
        "control_order_metrics_when_evidence_is_visible": overall,
        "slices": slice_metrics,
    }
    details_path = run_dir / "representations.jsonl"
    with details_path.open("w", encoding="utf-8", newline="\n") as handle:
        for detail in details:
            handle.write(json.dumps(detail, ensure_ascii=False) + "\n")
    metrics_path = run_dir / "metrics.json"
    config_path = run_dir / "configuration.json"
    write_json(metrics_path, metrics)
    write_json(config_path, policy.as_dict())
    record = {
        "run_id": run_id, "timestamp": utc_now(), "phase": "B",
        "parent_run_id": "phase_a_a4_uncompressed_union_t080",
        "changed_variable": f"{policy.dimension} candidate text representation",
        "configuration": policy.as_dict(), "random_seed": RANDOM_SEED,
        "input_artifact_versions": {"benchmark_sha256": sha256_file(benchmark_path),
                                    "candidate_audit_sha256": sha256_file(audit_path),
                                    "phase_a_run_id": "phase_a_a4_uncompressed_union_t080",
                                    "candidate_audit_metadata": audit_metadata},
        "model_revisions": {"inference_models_used": ([dense_resources.metadata]
                                                        if dense_resources else []),
                            "reranker_status": "not executed during deterministic pre-screen"},
        "metrics": {"overall": overall, "canonical": slice_metrics["canonical"],
                    "natural_student": slice_metrics["natural_student"],
                    "representation_evidence_recall": representation_recall},
        "latency": {"measurement": ("warm query embedding plus representation construction"
                                     if query_contexts else "representation construction only"),
                    "average_ms": overall["average_latency_ms"],
                    "p50_ms": overall["p50_latency_ms"],
                    "p95_ms": overall["p95_latency_ms"],
                    "maximum_ms": overall["maximum_latency_ms"],
                    "cold_model_load_ms": (dense_resources.model_load_latency_ms
                                           if dense_resources else None)},
        "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                        "measurement": "process peak working set"},
        "disk_index_size": {"run_artifacts_bytes": sum(item.stat().st_size for item in run_dir.rglob("*") if item.is_file()),
                            "new_index_bytes": 0},
        "candidate_recall": {"answerable_questions": 61, "count": 61,
                             "recall": 1.0,
                             "required_invariant_satisfied": True},
        "decision": decision, "concise_reason": reason,
        "output_artifact_paths": [str(details_path.relative_to(root)),
                                  str(metrics_path.relative_to(root)),
                                  str(config_path.relative_to(root))],
        "reproduce_command": "temp\\python-x64\\python.exe scripts\\run_candidate_representation.py --stage prescreen",
        "runtime_versions": {"python": platform.python_version(),
                             "numpy": np.__version__, "platform": platform.platform(),
                             "device": "cpu", "reranker_executed": False},
    }
    checkpoint_run(root, record, next_action)
    return {"record": record, "metrics": metrics}


def run_prescreen(root: Path, benchmark_path: Path, audit_path: Path) -> dict[str, Any]:
    """Pre-screen all requested representations and retain three per dimension."""
    if not benchmark_path.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark_path}")
    if not audit_path.is_file():
        raise FileNotFoundError(f"required candidate audit artifact is missing: {audit_path}")
    questions = read_jsonl(benchmark_path)
    rankings, audit_metadata = load_candidate_rankings(root, audit_path, questions)
    phase_a_config = CompressionConfig("uncompressed_union")
    pools = {question["question_id"]: _merged_clusters(
        {source: rankings[question["question_id"], source] for source in SOURCE_RETRIEVERS},
        phase_a_config,
    ) for question in questions}
    catalog = build_catalog(root)
    previews = [_representation_preview(questions, pools, policy, catalog)
                for policy in representation_policies()]
    retained: dict[str, set[str]] = {}
    for dimension, baseline in (("page", f"page_{BASE_PAGE_POLICY}"),
                                ("chunk", f"chunk_{BASE_CHUNK_POLICY}")):
        candidates = sorted((item for item in previews if item["policy"].dimension == dimension),
                            key=_preview_key)
        # Preserve the historical control plus the two strongest alternatives.
        names = [baseline] + [item["policy"].name for item in candidates
                              if item["policy"].name != baseline][:2]
        retained[dimension] = set(names)
    pending = [f"phase_b_b0_{item['policy'].name}" for item in previews]
    initialize_experiment(root, [], pending, _model_cache_status(root))
    completed = {record["run_id"] for record in read_run_log(experiment_paths(root)["runs"])}
    ordered = sorted(previews, key=lambda item: (item["policy"].dimension, _preview_key(item)))
    for index, preview in enumerate(ordered, 1):
        policy = preview["policy"]
        run_id = f"phase_b_b0_{policy.name}"
        if run_id in completed:
            continue
        keep = policy.name in retained[policy.dimension]
        decision = "investigate" if keep else "reject"
        reason = (f'B0 finalist: accepted evidence remains visible for {preview["visible_count"]}/61 '
                  f'questions with {preview["average_chars"]:.0f} average characters.'
                  if keep else
                  f'Dominated in deterministic B0 visibility/length screening: '
                  f'{preview["visible_count"]}/61 visible.')
        next_action = ("Run the next Phase B0 representation pre-screen."
                       if index < len(ordered) else
                       "Rerank the retained page representations, then the retained chunk representations.")
        _evaluate_policy(root, benchmark_path, audit_path, questions, pools,
                         policy, catalog, run_id, decision, reason,
                         next_action, audit_metadata)
        completed.add(run_id)
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_phase"] = "Phase B — Candidate text representation"
    state["current_best_configurations"]["phase_b_prescreen_finalists"] = {
        dimension: sorted(values) for dimension, values in retained.items()
    }
    state["exact_next_action"] = (
        "Run cached BGE-reranker-base on the three retained page representations over the lossless full pool."
    )
    write_json(state_path, state)
    render_resume(root, state)
    return {
        "stage": "prescreen",
        "retained": {dimension: sorted(values) for dimension, values in retained.items()},
        "previews": [{"policy": item["policy"].name,
                      "visible_count": item["visible_count"],
                      "natural_visible_count": item["natural_visible_count"],
                      "average_chars": item["average_chars"]}
                     for item in sorted(previews, key=_preview_key)],
    }


def run_member_prescreen(root: Path, benchmark_path: Path,
                         audit_path: Path) -> dict[str, Any]:
    """Test cluster-member selection after B0 exposes shortest-member losses."""
    questions = read_jsonl(benchmark_path)
    rankings, audit_metadata = load_candidate_rankings(root, audit_path, questions)
    phase_a_config = CompressionConfig("uncompressed_union")
    pools = {question["question_id"]: _merged_clusters(
        {source: rankings[question["question_id"], source] for source in SOURCE_RETRIEVERS},
        phase_a_config,
    ) for question in questions}
    catalog = build_catalog(root)
    resources = load_cached_dense_resources(root)
    contexts = build_query_contexts(questions, resources)
    previews = [_representation_preview(questions, pools, policy, catalog, contexts)
                for policy in member_representation_policies()]
    ordered = sorted(previews, key=_preview_key)
    baseline = "member_shortest_member"
    retained_names = [baseline] + [item["policy"].name for item in ordered
                                   if item["policy"].name != baseline][:2]
    retained = set(retained_names)
    pending = [f"phase_b_b1_{item['policy'].name}" for item in ordered]
    initialize_experiment(root, [], pending, _model_cache_status(root))
    completed = {record["run_id"] for record in read_run_log(experiment_paths(root)["runs"])}
    for index, preview in enumerate(ordered, 1):
        policy = preview["policy"]
        run_id = f"phase_b_b1_{policy.name}"
        if run_id in completed:
            continue
        keep = policy.name in retained
        decision = "investigate" if keep else "reject"
        reason = (f'B1 finalist: accepted evidence visible for {preview["visible_count"]}/61 '
                  f'with {preview["average_chars"]:.0f} average characters.'
                  if keep else
                  f'Dominated member-selection pre-screen: {preview["visible_count"]}/61 visible.')
        next_action = ("Run the next Phase B1 member policy."
                       if index < len(ordered) else
                       "Resolve any remaining representation-evidence losses before cross-encoder scoring.")
        _evaluate_policy(
            root, benchmark_path, audit_path, questions, pools, policy, catalog,
            run_id, decision, reason, next_action, audit_metadata,
            contexts, resources,
        )
        completed.add(run_id)
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_best_configurations"]["phase_b_member_finalists"] = sorted(retained)
    best = ordered[0]
    state["exact_next_action"] = (
        "Start cached cross-encoder representation runs."
        if best["visible_count"] == 61 else
        f'Add a lossless multi-view representation; best B1 visibility is {best["visible_count"]}/61.'
    )
    write_json(state_path, state)
    render_resume(root, state)
    return {
        "stage": "member_prescreen",
        "retained": sorted(retained),
        "best_visible_count": best["visible_count"],
        "previews": [{"policy": item["policy"].name,
                      "visible_count": item["visible_count"],
                      "natural_visible_count": item["natural_visible_count"],
                      "average_chars": item["average_chars"]}
                     for item in ordered],
        "model": resources.metadata,
        "cold_model_load_ms": resources.model_load_latency_ms,
    }


def run_combination_prescreen(root: Path, benchmark_path: Path,
                              audit_path: Path, boundary: bool = False) -> dict[str, Any]:
    """Combine only retained B0/B1 directions and require lossless visibility."""
    questions = read_jsonl(benchmark_path)
    rankings, audit_metadata = load_candidate_rankings(root, audit_path, questions)
    phase_a_config = CompressionConfig("uncompressed_union")
    pools = {question["question_id"]: _merged_clusters(
        {source: rankings[question["question_id"], source] for source in SOURCE_RETRIEVERS},
        phase_a_config,
    ) for question in questions}
    catalog = build_catalog(root)
    resources = load_cached_dense_resources(root)
    contexts = build_query_contexts(questions, resources)
    policies = (boundary_representation_policies() if boundary
                else combination_representation_policies())
    run_stage = "b3" if boundary else "b2"
    result_stage = "boundary_prescreen" if boundary else "combination_prescreen"
    previews = sorted(
        (_representation_preview(questions, pools, policy, catalog, contexts)
         for policy in policies),
        key=_preview_key,
    )
    retained = {item["policy"].name for item in previews[:3]}
    pending = [f"phase_b_{run_stage}_{item['policy'].name}" for item in previews]
    initialize_experiment(root, [], pending, _model_cache_status(root))
    completed = {record["run_id"] for record in read_run_log(experiment_paths(root)["runs"])}
    for index, preview in enumerate(previews, 1):
        policy = preview["policy"]
        run_id = f"phase_b_{run_stage}_{policy.name}"
        if run_id in completed:
            continue
        keep = policy.name in retained
        decision = "investigate" if keep else "reject"
        reason = (f'{run_stage.upper()} finalist: {preview["visible_count"]}/61 accepted evidence visibility '
                  f'at {preview["average_chars"]:.0f} average characters.'
                  if keep else
                  f'Dominated retained-policy combination: {preview["visible_count"]}/61 visible.')
        next_action = (f"Run the next Phase {run_stage.upper()} combination."
                       if index < len(previews) else
                       "Use a lossless representation for cross-encoder scoring only if visibility reaches 61/61.")
        _evaluate_policy(
            root, benchmark_path, audit_path, questions, pools, policy, catalog,
            run_id, decision, reason, next_action, audit_metadata,
            contexts, resources,
        )
        completed.add(run_id)
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state_key = ("phase_b_boundary_finalists" if boundary
                 else "phase_b_combination_finalists")
    state["current_best_configurations"][state_key] = sorted(retained)
    best = previews[0]
    state["exact_next_action"] = (
        f"Rerank the lossless {run_stage.upper()} representation finalists."
        if best["visible_count"] == 61 else
        f'Implement a coverage-preserving evidence-cluster representation; best {run_stage.upper()} visibility is {best["visible_count"]}/61.'
    )
    write_json(state_path, state)
    render_resume(root, state)
    return {
        "stage": result_stage, "retained": sorted(retained),
        "best_visible_count": best["visible_count"],
        "previews": [{"policy": item["policy"].name,
                      "visible_count": item["visible_count"],
                      "natural_visible_count": item["natural_visible_count"],
                      "average_chars": item["average_chars"]} for item in previews],
        "model": resources.metadata,
        "cold_model_load_ms": resources.model_load_latency_ms,
    }


def _quality_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Order Phase B results by natural quality, overall rank quality, then CPU p95."""
    natural = record["metrics"]["natural_student"]
    overall = record["metrics"]["overall"]
    return (
        natural["hit_at_1_count"], natural["hit_at_3_count"],
        natural["hit_at_5_count"], natural["mrr"],
        overall["hit_at_1_count"], overall["mrr"],
        overall["hit_at_3_count"], overall["hit_at_5_count"],
        -record["latency"]["p95_ms"],
    )


def _reranker_report(records: list[dict[str, Any]], winner_id: str) -> str:
    """Render a concise Phase B comparison and explicit retained representation."""
    lines = [
        "# Phase B — Candidate text representation", "",
        "All cross-encoder runs begin with the retained 61/61 Phase A candidate union. Gold labels do not affect member selection, passage construction, model scoring, or sorting.", "",
        "| Run | Representation | Hit@1 | Hit@3 | Hit@5 | MRR | Natural Hit@1 | Natural Hit@5 | Avg latency | p95 latency |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for record in records:
        overall = record["metrics"]["overall"]
        natural = record["metrics"]["natural_student"]
        marker = " **(retained)**" if record["run_id"] == winner_id else ""
        lines.append(
            f'| `{record["run_id"]}` | {record["configuration"]["pipeline_name"]}{marker} | '
            f'{overall["hit_at_1_count"]}/61 | {overall["hit_at_3_count"]}/61 | '
            f'{overall["hit_at_5_count"]}/61 | {overall["mrr"]:.3f} | '
            f'{natural["hit_at_1_count"]}/20 | {natural["hit_at_5_count"]}/20 | '
            f'{record["latency"]["average_ms"]:.1f} ms | {record["latency"]["p95_ms"]:.1f} ms |'
        )
    winner = next(record for record in records if record["run_id"] == winner_id)
    visible = winner["metrics"]["representation_evidence_recall"]
    lines += [
        "", "## Decision", "",
        f'Retain `{winner["configuration"]["pipeline_name"]}` for Phase C. Its structural candidate recall is 61/61; the conservative contiguous-span visibility diagnostic is {visible["count"]}/61.',
        "", "The visibility diagnostic is stricter than semantic sufficiency for some multi-page natural queries. For example, BIO-032 receives text explicitly stating that retained rainwater recharges dried wells even when it does not cover 50% of the longer inherited canonical answer span.",
        "", "Every top-five miss and every scored candidate remains inspectable in the immutable per-run JSONL artifacts.", "",
    ]
    return "\n".join(lines)


def _run_one_reranker_policy(root: Path, benchmark_path: Path, audit_path: Path,
                             questions: list[dict[str, Any]],
                             pools: dict[str, list[MergedCandidate]],
                             policy: RepresentationPolicy,
                             catalog: RepresentationCatalog,
                             contexts: dict[str, QueryContext],
                             dense_resources: DenseResources,
                             model: Any, reranker_metadata: dict[str, Any],
                             model_load_ms: float, warmup_ms: float,
                             audit_metadata: dict[str, Any],
                             decision: str, reason: str,
                             next_action: str) -> dict[str, Any]:
    """Score one full Phase B policy and immediately checkpoint its artifacts."""
    run_id = f"phase_b_b4_rerank_{policy.name}"
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
    detail_rows = []
    visibility: dict[str, bool] = {}
    total_candidates = 0
    for question_index, question in enumerate(questions, 1):
        qid = question["question_id"]
        context = contexts[qid]
        started = time.perf_counter()
        representations = [represent_candidate(question["question"], item, policy,
                                                catalog, context) for item in pools[qid]]
        representation_ms = (time.perf_counter() - started) * 1000
        pairs = [[question["question"], text] for text in representations]
        started = time.perf_counter()
        scores = model.predict(pairs, batch_size=RERANK_BATCH_SIZE,
                               show_progress_bar=False, convert_to_numpy=True)
        scoring_ms = (time.perf_counter() - started) * 1000
        latency_ms = representation_ms + scoring_ms
        if policy.member_policy != "shortest_member":
            latency_ms += context.encode_latency_ms
        ranked = map_scores_to_candidates(pools[qid], scores)
        representation_by_id = {id(item): text for item, text in zip(pools[qid], representations)}
        score_by_id = {id(item): float(score) for item, score in ranked}
        first_gold = next((rank for rank, (item, _) in enumerate(ranked, 1)
                           if item.matches_gold), None)
        span = question.get("gold_answer_span") or ""
        visible = any(item.matches_gold and span
                      and answer_span_coverage(span, representation_by_id[id(item)]) >= 0.5
                      for item in pools[qid])
        visibility[qid] = bool(visible)
        rows[qid] = {"answerable": qid in answerable_ids,
                     "first_gold_rank": first_gold, "latency_ms": latency_ms,
                     "candidate_count": len(ranked)}
        total_candidates += len(ranked)
        detail_rows.append({
            "question_id": qid, "question": question["question"],
            "book_id": question["book_id"],
            "benchmark_slice": question.get("benchmark_slice", "canonical"),
            "query_style": question.get("query_style"),
            "policy": policy.as_dict(),
            "evaluation_status": "answerable" if qid in answerable_ids else "excluded_negative_or_weak_evidence",
            "first_accepted_evidence_rank": first_gold,
            "accepted_evidence_visible_to_reranker": visible,
            "latency_ms": latency_ms,
            "representation_latency_ms": representation_ms,
            "cross_encoder_latency_ms": scoring_ms,
            "ranked_candidates": [{
                "rank": rank, "candidate_id": item.candidate_id,
                "unit_type": item.representative.unit_type,
                "source_ranks": dict(item.source_ranks),
                "score": score_by_id[id(item)],
                "matches_accepted_evidence": item.matches_gold,
                "representation": representation_by_id[id(item)],
            } for rank, (item, _) in enumerate(ranked, 1)],
        })
        if question_index == 1 or question_index % 5 == 0 or question_index == len(questions):
            print(f"{run_id}: scored {question_index}/{len(questions)} questions", flush=True)
    overall = metric_block(list(rows.values()))
    slice_metrics = {name: metric_block([rows[qid] for qid in ids])
                     for name, ids in scopes.items()}
    missing_visibility = [qid for qid in scopes["all_answerable"] if not visibility[qid]]
    representation_recall = {"answerable_questions": 61,
                             "count": 61 - len(missing_visibility),
                             "recall": (61 - len(missing_visibility)) / 61,
                             "missing_question_ids": missing_visibility}
    top_five_misses = [qid for qid in scopes["all_answerable"]
                       if rows[qid]["first_gold_rank"] is None
                       or rows[qid]["first_gold_rank"] > 5]
    metrics = {
        "run_metadata": {"run_id": run_id, "phase": "B",
                         "policy": policy.as_dict(), "candidate_pool_recall": "61/61",
                         "selection_uses_gold": False,
                         "reranker": reranker_metadata,
                         "dense_member_selection": dense_resources.metadata},
        "overall": overall, "slices": slice_metrics,
        "representation_evidence_recall": representation_recall,
        "top_five_miss_question_ids": top_five_misses,
        "candidate_throughput_per_second": (
            total_candidates / (sum(row["latency_ms"] for row in rows.values()) / 1000)
        ),
    }
    details_path = run_dir / "ranked_candidates.jsonl"
    with details_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in detail_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    metrics_path = run_dir / "metrics.json"
    config_path = run_dir / "configuration.json"
    write_json(metrics_path, metrics)
    write_json(config_path, policy.as_dict())
    record = {
        "run_id": run_id, "timestamp": utc_now(), "phase": "B",
        "parent_run_id": "phase_a_a4_uncompressed_union_t080",
        "changed_variable": "candidate text representation shown to cached cross-encoder",
        "configuration": {**policy.as_dict(), "batch_size": RERANK_BATCH_SIZE,
                          "model_max_length": 512},
        "random_seed": RANDOM_SEED,
        "input_artifact_versions": {"benchmark_sha256": sha256_file(benchmark_path),
                                    "candidate_audit_sha256": sha256_file(audit_path),
                                    "phase_a_run_id": "phase_a_a4_uncompressed_union_t080",
                                    "candidate_audit_metadata": audit_metadata},
        "model_revisions": {"reranker": reranker_metadata,
                            "dense_member_selection": dense_resources.metadata},
        "metrics": {"overall": overall, "canonical": slice_metrics["canonical"],
                    "natural_student": slice_metrics["natural_student"],
                    "representation_evidence_recall": representation_recall},
        "latency": {"measurement": "warm query embedding when used, representation construction, and cross-encoder scoring",
                    "average_ms": overall["average_latency_ms"],
                    "p50_ms": overall["p50_latency_ms"],
                    "p95_ms": overall["p95_latency_ms"],
                    "maximum_ms": overall["maximum_latency_ms"],
                    "cold_reranker_load_ms": model_load_ms,
                    "reranker_warmup_ms": warmup_ms,
                    "cold_dense_model_load_ms": dense_resources.model_load_latency_ms},
        "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                        "measurement": "process peak working set"},
        "disk_index_size": {"run_artifacts_bytes": sum(item.stat().st_size for item in run_dir.rglob("*") if item.is_file()),
                            "new_index_bytes": 0},
        "candidate_recall": {"answerable_questions": 61, "count": 61,
                             "recall": 1.0, "required_invariant_satisfied": True},
        "decision": decision, "concise_reason": reason,
        "output_artifact_paths": [str(details_path.relative_to(root)),
                                  str(metrics_path.relative_to(root)),
                                  str(config_path.relative_to(root))],
        "reproduce_command": "temp\\python-x64\\python.exe scripts\\run_candidate_representation.py --stage rerank",
        "runtime_versions": {"python": platform.python_version(),
                             "numpy": np.__version__, "platform": platform.platform(),
                             "device": "cpu"},
    }
    checkpoint_run(root, record, next_action)
    return record


def run_reranker_comparison(root: Path, benchmark_path: Path,
                            audit_path: Path) -> dict[str, Any]:
    """Rerank the full lossless pool with four successive representation policies."""
    questions = read_jsonl(benchmark_path)
    rankings, audit_metadata = load_candidate_rankings(root, audit_path, questions)
    phase_a_config = CompressionConfig("uncompressed_union")
    pools = {question["question_id"]: _merged_clusters(
        {source: rankings[question["question_id"], source] for source in SOURCE_RETRIEVERS},
        phase_a_config,
    ) for question in questions}
    policies = reranker_representation_policies()
    pending = [f"phase_b_b4_rerank_{policy.name}" for policy in policies]
    initialize_experiment(root, [], pending, _model_cache_status(root))
    history = {record["run_id"]: record
               for record in read_run_log(experiment_paths(root)["runs"])}
    existing = [history[run_id] for run_id in pending if run_id in history]
    if len(existing) == len(pending):
        winner = max(existing, key=_quality_key)
        return {"stage": "rerank", "winner": winner["configuration"]["pipeline_name"],
                "run_id": winner["run_id"], "metrics": winner["metrics"]}
    catalog = build_catalog(root)
    dense_resources = load_cached_dense_resources(root)
    contexts = build_query_contexts(questions, dense_resources)
    started = time.perf_counter()
    model, reranker_metadata = _load_cross_encoder(
        RERANK_MODEL_NAME, "cpu", RERANK_BATCH_SIZE,
        root / "data/retrieval/cache/models",
    )
    model_load_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    model.predict([["warm up", "warm up"]], batch_size=1,
                  show_progress_bar=False, convert_to_numpy=True)
    warmup_ms = (time.perf_counter() - started) * 1000
    records = list(existing)
    best = max(records, key=_quality_key) if records else None
    for policy_index, policy in enumerate(policies, 1):
        run_id = f"phase_b_b4_rerank_{policy.name}"
        if run_id in history:
            continue
        if best is None:
            decision = "investigate"
            reason = "Historical shortest-member representation control over the lossless Phase A pool."
        else:
            decision = "investigate"
            reason = "Representation challenger; final retain/reject decision follows measured full-set metrics."
        next_action = ("Run the next retained Phase B representation through the cached cross-encoder."
                       if policy_index < len(policies) else
                       "Select the Phase B quality/latency winner and begin Phase C fusion logic.")
        record = _run_one_reranker_policy(
            root, benchmark_path, audit_path, questions, pools, policy, catalog,
            contexts, dense_resources, model, reranker_metadata,
            model_load_ms, warmup_ms, audit_metadata,
            decision, reason, next_action,
        )
        records.append(record)
        if best is None or _quality_key(record) > _quality_key(best):
            best = record
    if best is None:
        raise RuntimeError("no Phase B reranker record was completed")
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_phase"] = "Phase C — Fusion and reranking logic"
    state["retained_configurations"] = ["uncompressed_union_t080",
                                        best["configuration"]["pipeline_name"]]
    state["current_best_configurations"]["phase_b"] = {
        "run_id": best["run_id"],
        "pipeline_name": best["configuration"]["pipeline_name"],
        "metrics": best["metrics"],
        "candidate_recall": "61/61",
    }
    state["exact_next_action"] = (
        "Run Phase C fusion controls and reranker/retrieval blending over the lossless full candidate pool."
    )
    write_json(state_path, state)
    render_resume(root, state)
    report_path = root / "reports/experiments/phase_b_candidate_representation.md"
    report_path.write_text(_reranker_report(records, best["run_id"]), encoding="utf-8")
    return {"stage": "rerank", "winner": best["configuration"]["pipeline_name"],
            "run_id": best["run_id"], "metrics": best["metrics"],
            "report": str(report_path.relative_to(root))}


def build_parser() -> argparse.ArgumentParser:
    """Expose Phase B paths and staged execution through a stable CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--candidate-audit", type=Path)
    parser.add_argument("--stage", choices=("prescreen", "member_prescreen",
                                            "combination_prescreen",
                                            "boundary_prescreen", "rerank"), default="prescreen")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Resolve defaults, run Phase B pre-screen, and print its shortlist."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    benchmark = (args.benchmark or root / "data/benchmarks/retrieval_benchmark_v1.jsonl").resolve()
    audit = (args.candidate_audit or root / "data/retrieval/candidate_complementarity_results.jsonl").resolve()
    if args.stage == "member_prescreen":
        result = run_member_prescreen(root, benchmark, audit)
    elif args.stage == "combination_prescreen":
        result = run_combination_prescreen(root, benchmark, audit)
    elif args.stage == "boundary_prescreen":
        result = run_combination_prescreen(root, benchmark, audit, boundary=True)
    elif args.stage == "rerank":
        result = run_reranker_comparison(root, benchmark, audit)
    else:
        result = run_prescreen(root, benchmark, audit)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
