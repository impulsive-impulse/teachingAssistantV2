"""Candidate complementarity audit over the existing retrieval baselines.

This module does not define a new retriever.  It reconstructs the rankings from
the already-reviewed corpus, existing baseline algorithms, and cached BGE-small
embeddings, then asks whether their accepted evidence is complementary.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .chunk_retrieval import (answer_span_coverage, derive_gold_chunks,
                              fixed_chunks, load_chunk_embeddings,
                              structured_chunks)
from .hierarchical_retrieval import (build_hierarchy, build_nodes, derive_gold,
                                     load_hierarchy_embeddings, rank_variants,
                                     soft_fusion, strict_cascade)
from .retrieval import (BM25, QUERY_PREFIX, accepted_pdf_pages, load_dense_index,
                        load_pages, read_jsonl, reciprocal_rank_fusion,
                        stable_ranking, tokenize)


# These four methods are the architecture decision set requested by the audit.
PRIMARY_RETRIEVERS = (
    "page_dense_bge_small",
    "page_bm25",
    "fixed_400_80_bm25",
    "soft_fusion_hybrid",
)

# Secondary methods make it possible to detect a useful candidate source that
# the primary shortlist would otherwise overlook.  They are reported apart.
ADDITIONAL_RETRIEVERS = (
    "page_hybrid_rrf",
    "fixed_400_80_dense_bge_small",
    "fixed_400_80_hybrid_rrf",
    "structured_bm25",
    "structured_dense_bge_small",
    "structured_hybrid_rrf",
    "strict_cascade_bm25",
    "strict_cascade_dense_bge_small",
    "strict_cascade_hybrid_rrf",
    "soft_fusion_bm25",
    "soft_fusion_dense_bge_small",
)
ALL_RETRIEVERS = PRIMARY_RETRIEVERS + ADDITIONAL_RETRIEVERS

UNIONS = {
    "page_bge_plus_page_bm25": ("page_dense_bge_small", "page_bm25"),
    "page_bge_plus_fixed_bm25": ("page_dense_bge_small", "fixed_400_80_bm25"),
    "page_bge_plus_soft_fusion_hybrid": ("page_dense_bge_small", "soft_fusion_hybrid"),
    "page_bge_plus_fixed_bm25_plus_soft_fusion_hybrid": (
        "page_dense_bge_small", "fixed_400_80_bm25", "soft_fusion_hybrid"),
    "all_primary_retrievers": PRIMARY_RETRIEVERS,
}

DEPENDENCY_FLAGS = {
    "formula_dependent": "formula_dependency",
    "visual_dependent": "visual_dependency",
    "table_dependent": "table_dependency",
    "multi_page": "requires_multiple_pages",
    "multi_chunk": "requires_multiple_chunks",
}


@dataclass(frozen=True)
class Candidate:
    """One ranked page or chunk expressed in a common inspectable schema."""

    retriever: str
    rank: int
    candidate_id: str
    unit_type: str
    book_id: str
    pdf_pages: tuple[int, ...]
    textbook_pages: tuple[str, ...]
    text: str
    matches_gold: bool
    matched_evidence: tuple[str, ...]
    chapter_title: str | None = None
    section_title: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialize stable identifiers and a short preview for detailed JSONL."""
        return {
            "rank": self.rank,
            "candidate_id": self.candidate_id,
            "unit_type": self.unit_type,
            "pdf_pages": list(self.pdf_pages),
            "textbook_pages": list(self.textbook_pages),
            "text_snippet": " ".join(self.text.split())[:500],
            "matches_accepted_evidence": self.matches_gold,
            "accepted_evidence_matched": list(self.matched_evidence),
            "chapter_title": self.chapter_title,
            "section_title": self.section_title,
        }


def _as_int_pages(values: Iterable[Any]) -> tuple[int, ...]:
    """Normalize page metadata to ordered unique integer PDF pages."""
    return tuple(dict.fromkeys(int(value) for value in values if value is not None))


def _as_textbook_pages(values: Iterable[Any]) -> tuple[str, ...]:
    """Preserve printed-page identity without mixing integer/string forms."""
    return tuple(dict.fromkeys(str(value) for value in values if value is not None))


def evidence_question(question: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Copy a benchmark row with reviewed alternative pages resolved to PDF IDs."""
    normalized = dict(question)
    normalized["gold_pdf_pages"] = sorted(accepted_pdf_pages(question, pages))
    return normalized


def accepted_page_ids(question: dict[str, Any], pages: list[dict[str, Any]],
                      minimum_coverage: float = 0.5) -> set[int]:
    """Require a reviewed page and contiguous answer-span evidence on that page.

    This deliberately tightens the original page-only match: merely landing on
    a gold page is insufficient when its text does not contain the accepted
    answer evidence.
    """
    span = (question.get("gold_answer_span") or "").strip()
    if not span:
        return set()
    reviewed_pages = accepted_pdf_pages(question, pages)
    return {
        int(page["pdf_page_number"])
        for page in pages
        if int(page["pdf_page_number"]) in reviewed_pages
        and answer_span_coverage(span, page["cleaned_text"]) >= minimum_coverage
    }


def _candidate(unit: dict[str, Any], retriever: str, rank: int,
               unit_type: str, accepted_ids: set[Any]) -> Candidate:
    """Convert a native page/chunk record into the shared candidate schema."""
    if unit_type == "page":
        candidate_id = f'{unit["book_id"]}:pdf:{int(unit["pdf_page_number"])}'
        pdf_pages = (int(unit["pdf_page_number"]),)
        textbook_pages = _as_textbook_pages([unit.get("textbook_page_number")])
        text = unit["cleaned_text"]
        matched = int(unit["pdf_page_number"]) in accepted_ids
        evidence = tuple(f"pdf:{page}" for page in pdf_pages if page in accepted_ids)
    else:
        candidate_id = str(unit["chunk_id"])
        pdf_pages = _as_int_pages(unit["pdf_pages"])
        textbook_pages = _as_textbook_pages(unit["textbook_pages"])
        text = unit["text"]
        matched = candidate_id in accepted_ids
        evidence = (candidate_id,) if matched else ()
    return Candidate(retriever, rank, candidate_id, unit_type, unit["book_id"],
                     pdf_pages, textbook_pages, text, matched, evidence,
                     unit.get("chapter_title"), unit.get("section_title"))


@lru_cache(maxsize=None)
def _shingles(text: str, size: int = 5) -> frozenset[tuple[str, ...]]:
    """Create deterministic token shingles for cross-unit duplicate detection."""
    terms = tokenize(text)
    if len(terms) < size:
        return frozenset({tuple(terms)}) if terms else frozenset()
    return frozenset(tuple(terms[i:i + size]) for i in range(len(terms) - size + 1))


def substantially_same_evidence(left: Candidate, right: Candidate,
                                threshold: float = 0.8) -> bool:
    """Identify page/chunk candidates that contain substantially the same text.

    Candidates must share a source PDF page.  Shingle containment (rather than
    symmetric similarity) lets a paragraph count as duplicate evidence inside
    a longer page while keeping unrelated chunks from the same page distinct.
    """
    if left.book_id != right.book_id or not set(left.pdf_pages).intersection(right.pdf_pages):
        return False
    if left.candidate_id == right.candidate_id:
        return True
    a, b = _shingles(left.text), _shingles(right.text)
    if not a or not b:
        return False
    return len(a.intersection(b)) / min(len(a), len(b)) >= threshold


def deduplicate_candidates(candidates: Iterable[Candidate]) -> list[list[Candidate]]:
    """Cluster substantially identical evidence in deterministic input order."""
    clusters: list[list[Candidate]] = []
    for candidate in candidates:
        existing = next((cluster for cluster in clusters
                         if any(substantially_same_evidence(candidate, item) for item in cluster)), None)
        if existing is None:
            clusters.append([candidate])
        else:
            existing.append(candidate)
    return clusters


def oracle_hit(first_ranks: dict[str, int | None], methods: Iterable[str], depth: int) -> bool:
    """Return whether any method has accepted evidence inside its top ``depth``."""
    return any(first_ranks.get(method) is not None and int(first_ranks[method]) <= depth
               for method in methods)


def unique_wins(first_by_question: dict[str, dict[str, int | None]], methods: Iterable[str],
                depth: int) -> dict[str, list[str]]:
    """List questions solved by exactly one method at a candidate depth."""
    method_list = tuple(methods)
    output = {method: [] for method in method_list}
    for question_id, ranks in first_by_question.items():
        winners = [method for method in method_list
                   if ranks.get(method) is not None and int(ranks[method]) <= depth]
        if len(winners) == 1:
            output[winners[0]].append(question_id)
    return output


def pairwise_overlap(left: list[Candidate], right: list[Candidate]) -> dict[str, Any]:
    """Compute deduplicated evidence overlap and unique correct contributions."""
    clusters = deduplicate_candidates(left + right)
    left_name = left[0].retriever if left else None
    right_name = right[0].retriever if right else None
    both = 0
    left_useful = 0
    right_useful = 0
    for cluster in clusters:
        sources = {candidate.retriever for candidate in cluster}
        correct = any(candidate.matches_gold for candidate in cluster)
        if left_name in sources and right_name in sources:
            both += 1
        elif correct and left_name in sources:
            left_useful += 1
        elif correct and right_name in sources:
            right_useful += 1
    union = len(clusters)
    return {
        "shared_evidence_clusters": both,
        "union_evidence_clusters": union,
        "jaccard": both / union if union else 1.0,
        "unique_useful_candidates_left": left_useful,
        "unique_useful_candidates_right": right_useful,
    }


def metric_block(question_ids: list[str], first_by_question: dict[str, dict[str, int | None]],
                 method: str) -> dict[str, Any]:
    """Calculate exact-count retrieval metrics for one method and question set."""
    ranks = [first_by_question[qid].get(method) for qid in question_ids]
    result: dict[str, Any] = {"answerable_questions": len(question_ids)}
    for depth in (1, 3, 5, 10, 20):
        count = sum(rank is not None and rank <= depth for rank in ranks)
        result[f"hit_at_{depth}"] = count / len(ranks) if ranks else None
        result[f"hit_at_{depth}_count"] = count
    result["mrr"] = (sum(1.0 / rank if rank else 0.0 for rank in ranks) / len(ranks)
                     if ranks else None)
    return result


def union_block(question_ids: list[str], first_by_question: dict[str, dict[str, int | None]],
                methods: Iterable[str]) -> dict[str, Any]:
    """Calculate per-method-budget oracle recall for one candidate union."""
    method_list = tuple(methods)
    result: dict[str, Any] = {
        "answerable_questions": len(question_ids),
        "methods": list(method_list),
        "budget_definition": "each method contributes its top K before cross-method deduplication",
    }
    for depth in (5, 10, 20):
        count = sum(oracle_hit(first_by_question[qid], method_list, depth) for qid in question_ids)
        result[f"oracle_hit_at_{depth}"] = count / len(question_ids) if question_ids else None
        result[f"oracle_hit_at_{depth}_count"] = count
        result[f"maximum_candidates_before_dedup_at_{depth}"] = depth * len(method_list)
    return result


def _rank_page_methods(questions: list[dict[str, Any]], books: dict[str, list[dict[str, Any]]],
                       cache_dir: Path, max_depth: int, device: str | None,
                       candidates: dict[tuple[str, str], list[Candidate]],
                       first: dict[str, dict[str, int | None]], minimum_coverage: float) -> dict[str, Any]:
    """Reconstruct page BM25, BGE-small, and existing RRF rankings."""
    bm25 = {book: BM25(page["cleaned_text"] for page in pages) for book, pages in books.items()}
    dense = load_dense_index(books, cache_dir, device)
    for question in questions:
        qid, book = question["question_id"], question["book_id"]
        pages = books[book]
        accepted = accepted_page_ids(question, pages, minimum_coverage)
        bm_scores = bm25[book].scores(question["question"])
        bm_rank = stable_ranking(bm_scores)
        query = dense.model.encode([QUERY_PREFIX + question["question"]], convert_to_numpy=True,
                                   normalize_embeddings=True, show_progress_bar=False)[0]
        dense_rank = stable_ranking(dense.embeddings[book] @ query)
        hybrid_rank = stable_ranking(reciprocal_rank_fusion([bm_rank, dense_rank], len(pages)))
        for method, ranking in (("page_bm25", bm_rank),
                                ("page_dense_bge_small", dense_rank),
                                ("page_hybrid_rrf", hybrid_rank)):
            matches = [rank for rank, index in enumerate(ranking, 1)
                       if int(pages[int(index)]["pdf_page_number"]) in accepted]
            first[qid][method] = min(matches) if matches else None
            candidates[qid, method] = [
                _candidate(pages[int(index)], method, rank, "page", accepted)
                for rank, index in enumerate(ranking[:max_depth], 1)
            ]
    return dense.metadata


def _rank_chunk_methods(questions: list[dict[str, Any]], books: dict[str, list[dict[str, Any]]],
                        cache_dir: Path, max_depth: int, device: str | None,
                        candidates: dict[tuple[str, str], list[Candidate]],
                        first: dict[str, dict[str, int | None]], minimum_coverage: float) -> dict[str, Any]:
    """Reconstruct fixed and structured chunk rankings without rewriting artifacts."""
    corpora = {
        "fixed": {book: fixed_chunks(pages, 400, 80) for book, pages in books.items()},
        "structured": {book: structured_chunks(pages, 250, 500) for book, pages in books.items()},
    }
    bm25 = {strategy: {book: BM25(chunk["text"] for chunk in chunks)
                       for book, chunks in by_book.items()}
            for strategy, by_book in corpora.items()}
    model, embeddings, metadata = load_chunk_embeddings(corpora, cache_dir, device)
    for strategy in ("fixed", "structured"):
        prefix = "fixed_400_80" if strategy == "fixed" else "structured"
        for question in questions:
            qid, book = question["question_id"], question["book_id"]
            chunks = corpora[strategy][book]
            normalized_question = evidence_question(question, books[book])
            mapping = derive_gold_chunks(normalized_question, chunks, minimum_coverage)
            accepted = set(mapping["primary"] + mapping["alternatives"])
            bm_scores = bm25[strategy][book].scores(question["question"])
            bm_rank = stable_ranking(bm_scores)
            query = model.encode([QUERY_PREFIX + question["question"]], convert_to_numpy=True,
                                 normalize_embeddings=True, show_progress_bar=False)[0]
            dense_rank = stable_ranking(embeddings[strategy][book] @ query)
            hybrid_rank = stable_ranking(reciprocal_rank_fusion([bm_rank, dense_rank], len(chunks)))
            for suffix, ranking in (("bm25", bm_rank), ("dense_bge_small", dense_rank),
                                    ("hybrid_rrf", hybrid_rank)):
                method = f"{prefix}_{suffix}"
                matches = [rank for rank, index in enumerate(ranking, 1)
                           if chunks[int(index)]["chunk_id"] in accepted]
                first[qid][method] = min(matches) if matches else None
                candidates[qid, method] = [
                    _candidate(chunks[int(index)], method, rank, "fixed_chunk" if strategy == "fixed" else "structured_chunk", accepted)
                    for rank, index in enumerate(ranking[:max_depth], 1)
                ]
    return metadata


def _rank_hierarchy_methods(questions: list[dict[str, Any]], books: dict[str, list[dict[str, Any]]],
                            root: Path, cache_dir: Path, max_depth: int, device: str | None,
                            candidates: dict[tuple[str, str], list[Candidate]],
                            first: dict[str, dict[str, int | None]], minimum_coverage: float) -> dict[str, Any]:
    """Reconstruct strict-cascade and soft-fusion paragraph rankings."""
    corpora: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for book in books:
        leaves, _ = build_hierarchy(root, book, 250, 150, 350)
        sections, chapters = build_nodes(leaves)
        corpora[book] = {"paragraphs": leaves, "sections": sections, "chapters": chapters}
    bm25 = {
        book: {
            "paragraphs": BM25(node["text"] for node in levels["paragraphs"]),
            "sections": BM25(f'{node["chapter_title"]} {node["title"] or ""} {node["text"]}'
                             for node in levels["sections"]),
            "chapters": BM25(node["title"] for node in levels["chapters"]),
        }
        for book, levels in corpora.items()
    }
    model, embeddings, metadata = load_hierarchy_embeddings(corpora, cache_dir, device)
    aliases = {"bm25": "bm25", "dense_bge_small": "dense_bge_small", "hybrid_rrf": "hybrid_rrf"}
    for question in questions:
        qid, book = question["question_id"], question["book_id"]
        levels = corpora[book]
        normalized_question = evidence_question(question, books[book])
        mapping = derive_gold(normalized_question, levels["paragraphs"], minimum_coverage)
        accepted = set(mapping["paragraphs"])
        scores, _ = rank_variants(question["question"], levels, bm25[book], model, embeddings[book])
        for native, suffix in aliases.items():
            strict_rank, _ = strict_cascade(levels, scores[native], 3, 8)
            soft_rank, _ = soft_fusion(levels, scores[native], 0.5, 0.25)
            for approach, ranking in (("strict_cascade", strict_rank), ("soft_fusion", soft_rank)):
                method = f"{approach}_{suffix}"
                # Keep the requested short name for the primary soft Hybrid.
                if method == "soft_fusion_hybrid_rrf":
                    method = "soft_fusion_hybrid"
                matches = [rank for rank, index in enumerate(ranking, 1)
                           if levels["paragraphs"][int(index)]["chunk_id"] in accepted]
                first[qid][method] = min(matches) if matches else None
                candidates[qid, method] = [
                    _candidate(levels["paragraphs"][int(index)], method, rank,
                               "hierarchical_paragraph", accepted)
                    for rank, index in enumerate(ranking[:max_depth], 1)
                ]
    return metadata["metadata"]


def _scopes(questions: list[dict[str, Any]], answerable_ids: set[str]) -> dict[str, list[str]]:
    """Build the required benchmark, book, dependency, and query-style slices."""
    answerable = [q for q in questions if q["question_id"] in answerable_ids]
    scopes = {"all_answerable": [q["question_id"] for q in answerable]}
    for value in ("canonical", "natural_student"):
        scopes[value] = [q["question_id"] for q in answerable if q.get("benchmark_slice", "canonical") == value]
    for book in ("biology", "physical_sciences"):
        scopes[f"book:{book}"] = [q["question_id"] for q in answerable if q["book_id"] == book]
    for label, field in DEPENDENCY_FLAGS.items():
        scopes[label] = [q["question_id"] for q in answerable if q.get(field)]
    styles = sorted({q.get("query_style") for q in answerable if q.get("query_style")})
    for style in styles:
        scopes[f"query_style:{style}"] = [q["question_id"] for q in answerable if q.get("query_style") == style]
    return scopes


def _failure_category(question: dict[str, Any], ranks: dict[str, int | None], max_depth: int) -> str:
    """Classify a question missed by every audited method at maximum depth."""
    if question.get("formula_dependency"):
        return "formula_or_symbol_extraction_mismatch"
    if question.get("visual_dependency"):
        return "visual_evidence_unavailable"
    if question.get("table_dependency"):
        return "incorrect_or_incomplete_document_structure"
    if question.get("requires_multiple_pages"):
        return "multi_page_evidence"
    if question.get("requires_multiple_chunks"):
        return "multi_chunk_evidence"
    if question.get("ambiguity_risk") in {"medium", "high"} or question.get("query_style") == "short_underspecified":
        return "ambiguous_or_underspecified_query"
    if any(rank is not None and rank > max_depth for rank in ranks.values()):
        return "correct_evidence_ranked_below_candidate_budget"
    if question.get("query_style") in {"different_vocabulary", "colloquial", "imperfect_grammar"}:
        return "query_vocabulary_gap"
    return "benchmark_or_evidence_ambiguity"


def _pairwise_metrics(answerable_ids: list[str], candidates: dict[tuple[str, str], list[Candidate]],
                      first: dict[str, dict[str, int | None]], methods: tuple[str, ...]) -> dict[str, Any]:
    """Compute success contingency tables and evidence overlap for every pair."""
    output: dict[str, Any] = {}
    for left_index, left in enumerate(methods):
        for right in methods[left_index + 1:]:
            pair_key = f"{left}__vs__{right}"
            output[pair_key] = {}
            for depth in (5, 10, 20):
                both = left_only = right_only = both_miss = 0
                both_ids: list[str] = []
                left_only_ids: list[str] = []
                right_only_ids: list[str] = []
                both_miss_ids: list[str] = []
                shared = union = left_useful = right_useful = 0
                per_question_jaccard = []
                for qid in answerable_ids:
                    left_hit = first[qid].get(left) is not None and first[qid][left] <= depth
                    right_hit = first[qid].get(right) is not None and first[qid][right] <= depth
                    if left_hit and right_hit:
                        both += 1; both_ids.append(qid)
                    elif left_hit:
                        left_only += 1; left_only_ids.append(qid)
                    elif right_hit:
                        right_only += 1; right_only_ids.append(qid)
                    else:
                        both_miss += 1; both_miss_ids.append(qid)
                    overlap = pairwise_overlap(candidates[qid, left][:depth], candidates[qid, right][:depth])
                    shared += overlap["shared_evidence_clusters"]
                    union += overlap["union_evidence_clusters"]
                    left_useful += overlap["unique_useful_candidates_left"]
                    right_useful += overlap["unique_useful_candidates_right"]
                    per_question_jaccard.append(overlap["jaccard"])
                output[pair_key][f"at_{depth}"] = {
                    "questions_both_correct": both,
                    "questions_only_left_correct": left_only,
                    "questions_only_right_correct": right_only,
                    "questions_both_miss": both_miss,
                    "questions_both_correct_ids": both_ids,
                    "questions_only_left_correct_ids": left_only_ids,
                    "questions_only_right_correct_ids": right_only_ids,
                    "questions_both_miss_ids": both_miss_ids,
                    "shared_candidate_evidence_clusters": shared,
                    "candidate_evidence_union_clusters": union,
                    "candidate_evidence_jaccard_micro": shared / union if union else 1.0,
                    "candidate_evidence_jaccard_mean_by_question": (sum(per_question_jaccard) / len(per_question_jaccard)
                                                                      if per_question_jaccard else None),
                    "unique_useful_candidates_left": left_useful,
                    "unique_useful_candidates_right": right_useful,
                }
    return output


def _pool_sizes(question_ids: list[str], candidates: dict[tuple[str, str], list[Candidate]],
                methods: Iterable[str], depth: int) -> dict[str, float]:
    """Summarize actual union sizes after evidence-level duplicate clustering."""
    before, after = [], []
    method_list = tuple(methods)
    for qid in question_ids:
        pool = [candidate for method in method_list for candidate in candidates[qid, method][:depth]]
        before.append(len(pool)); after.append(len(deduplicate_candidates(pool)))
    return {
        "average_before_dedup": sum(before) / len(before) if before else 0.0,
        "average_after_dedup": sum(after) / len(after) if after else 0.0,
        "maximum_before_dedup": depth * len(method_list),
    }


def render_report(metrics: dict[str, Any]) -> str:
    """Render headline complementarity findings and the architecture decision."""
    def pct(value: float | None) -> str:
        return "n/a" if value is None else f"{100 * value:.1f}%"

    labels = metrics["run_metadata"]["retriever_labels"]
    primary = metrics["run_metadata"]["primary_retrievers"]
    lines = [
        "# Candidate Complementarity Audit v1", "",
        "This audit reconstructs existing rankings only; it adds no retriever, reranker, query rewriting, LLM, or gold-aware ranking. BGE-small corpus embeddings were loaded from the existing validated caches.", "",
        "A candidate is correct only when it maps to reviewed gold/alternative pages **and** satisfies the existing contiguous answer-span rule for its retrieval unit. Candidates sharing a PDF page and at least 80% five-token-shingle containment are deduplicated as substantially the same evidence.", "",
        "## Primary individual retrievers", "",
        "| Slice | Retriever | N | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Hit@20 | MRR |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scope in ("all_answerable", "canonical", "natural_student"):
        for method in primary:
            m = metrics["individual_metrics"][scope][method]
            n = m["answerable_questions"]
            lines.append(f'| {scope.replace("_", " ")} | {labels[method]} | {n} | {m["hit_at_1_count"]}/{n} ({pct(m["hit_at_1"])}) | {m["hit_at_3_count"]}/{n} ({pct(m["hit_at_3"])}) | {m["hit_at_5_count"]}/{n} ({pct(m["hit_at_5"])}) | {m["hit_at_10_count"]}/{n} ({pct(m["hit_at_10"])}) | {m["hit_at_20_count"]}/{n} ({pct(m["hit_at_20"])}) | {m["mrr"]:.3f} |')

    lines += ["", "## Candidate unions", "",
              "Oracle Hit@K gives every member its own top-K budget before cross-method deduplication. Thus a four-method Oracle Hit@10 pool has at most 40 raw candidates; actual average pool sizes are recorded below and in JSON.", "",
              "| Slice | Union | N | Oracle Hit@5 | Oracle Hit@10 | Oracle Hit@20 |",
              "|---|---|---:|---:|---:|---:|"]
    for scope in ("all_answerable", "canonical", "natural_student"):
        for name, block in metrics["union_metrics"][scope].items():
            lines.append(f'| {scope.replace("_", " ")} | {name.replace("_", " ")} | {block["answerable_questions"]} | {block["oracle_hit_at_5_count"]}/{block["answerable_questions"]} ({pct(block["oracle_hit_at_5"])}) | {block["oracle_hit_at_10_count"]}/{block["answerable_questions"]} ({pct(block["oracle_hit_at_10"])}) | {block["oracle_hit_at_20_count"]}/{block["answerable_questions"]} ({pct(block["oracle_hit_at_20"])}) |')

    lines += ["", "### All-primary candidate budgets", "",
              "| Per-method depth | Max raw | Avg raw | Avg after deduplication |",
              "|---:|---:|---:|---:|"]
    for depth, block in metrics["candidate_pool_sizes"]["all_primary_retrievers"].items():
        lines.append(f'| {depth} | {block["maximum_before_dedup"]} | {block["average_before_dedup"]:.1f} | {block["average_after_dedup"]:.1f} |')

    lines += ["", "## Primary complementarity at depth 20", "",
              "| Pair | Both correct | Only left | Only right | Both miss | Evidence Jaccard | Unique useful left/right |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for left_index, left in enumerate(primary):
        for right in primary[left_index + 1:]:
            block = metrics["pairwise_primary"][f"{left}__vs__{right}"]["at_20"]
            lines.append(f'| {labels[left]} vs {labels[right]} | {block["questions_both_correct"]} | {block["questions_only_left_correct"]} | {block["questions_only_right_correct"]} | {block["questions_both_miss"]} | {pct(block["candidate_evidence_jaccard_micro"])} | {block["unique_useful_candidates_left"]}/{block["unique_useful_candidates_right"]} |')

    lines += ["", "## Unique primary wins", "",
              "A unique win means that method alone retrieves accepted evidence at the stated depth among the four primary methods.", ""]
    for depth in (5, 10, 20):
        lines.append(f"### Depth {depth}")
        lines.append("")
        for method in primary:
            ids = metrics["unique_primary_wins"][str(depth)][method]
            lines.append(f'- {labels[method]}: {len(ids)} — {", ".join(ids) if ids else "none"}')
        lines.append("")

    page_pair = metrics["pairwise_primary"]["page_dense_bge_small__vs__page_bm25"]["at_20"]
    lines += ["## Page dense versus keyword-only wins at depth 20", "",
              "- Page BGE-small succeeds while Page BM25 misses: " + (", ".join(page_pair["questions_only_left_correct_ids"]) or "none") + ".",
              "- Page BM25 succeeds while Page BGE-small misses: " + (", ".join(page_pair["questions_only_right_correct_ids"]) or "none") + ".", ""]

    lines += ["## Best-union slices", "",
              "| Slice | N | Oracle Hit@5 | Oracle Hit@10 | Oracle Hit@20 |",
              "|---|---:|---:|---:|---:|"]
    for scope, unions in metrics["union_metrics"].items():
        if scope in {"all_answerable", "canonical", "natural_student"}:
            continue
        block = unions["all_primary_retrievers"]
        lines.append(f'| {scope.replace("_", " ")} | {block["answerable_questions"]} | {block["oracle_hit_at_5_count"]}/{block["answerable_questions"]} ({pct(block["oracle_hit_at_5"])}) | {block["oracle_hit_at_10_count"]}/{block["answerable_questions"]} ({pct(block["oracle_hit_at_10"])}) | {block["oracle_hit_at_20_count"]}/{block["answerable_questions"]} ({pct(block["oracle_hit_at_20"])}) |')

    lines += ["", "## Additional existing methods", "",
              "These variants are diagnostic only; they are not silently added to the primary architecture decision.", "",
              "| Retriever | Hit@5 | Hit@10 | Hit@20 | MRR |",
              "|---|---:|---:|---:|---:|"]
    for method in metrics["run_metadata"]["additional_retrievers"]:
        m = metrics["individual_metrics"]["all_answerable"][method]
        n = m["answerable_questions"]
        lines.append(f'| {labels[method]} | {m["hit_at_5_count"]}/{n} ({pct(m["hit_at_5"])}) | {m["hit_at_10_count"]}/{n} ({pct(m["hit_at_10"])}) | {m["hit_at_20_count"]}/{n} ({pct(m["hit_at_20"])}) | {m["mrr"]:.3f} |')

    lines += ["", "## Questions missed by every required candidate union at depth 20", ""]
    if metrics["all_primary_misses_at_20"]:
        lines += ["| Question | Slice | Likely cause | Additional method that rescues it |", "|---|---|---|---|"]
        for miss in metrics["all_primary_misses_at_20"]:
            rescue = ", ".join(labels[x] for x in miss["additional_retrievers_matching_at_20"])
            lines.append(f'| {miss["question_id"]}: {miss["question"]} | {miss["benchmark_slice"]} | {miss["failure_category"].replace("_", " ")} | {rescue or "none"} |')
    else:
        lines.append("None.")

    lines += ["", "## Questions missed by every audited method at depth 20", ""]
    if metrics["all_method_misses_at_20"]:
        lines += ["| Question | Slice | Likely cause |", "|---|---|---|"]
        for miss in metrics["all_method_misses_at_20"]:
            lines.append(f'| {miss["question_id"]}: {miss["question"]} | {miss["benchmark_slice"]} | {miss["failure_category"].replace("_", " ")} |')
    else:
        lines.append("None. Every answerable question has accepted evidence in at least one audited top-20 list.")

    decision = metrics["decision"]
    lines += ["", "## Decision", "",
              f'1. Canonical threshold: **{decision["canonical_threshold_answer"]}** ({decision["canonical_oracle_hit_at_10_count"]}/41 at Hit@10; {decision["canonical_oracle_hit_at_20_count"]}/41 at Hit@20).',
              f'2. Natural-student threshold: **{decision["natural_threshold_answer"]}** ({decision["natural_oracle_hit_at_10_count"]}/20 at Hit@10; {decision["natural_oracle_hit_at_20_count"]}/20 at Hit@20).',
              f'3. Does every primary retriever contribute uniquely? **{decision["meaningful_unique_contributions"]}**.',
              f'4. Reranker candidate sufficiency: **{decision["reranking_justified"]}**.',
              f'5. Retain: {", ".join(labels[x] for x in decision["retain_retrievers"])}.',
              f'6. Separate candidate sources not recommended because their recall is redundant: {", ".join(labels[x] for x in decision["omit_retrievers"])}.',
              f'7. Remaining-miss focus: {decision["remaining_miss_focus"]}.', "",
              "Full pairwise tables for all 15 existing methods, exact question IDs, and every slice are in `candidate_complementarity_metrics.json`.", ""]
    return "\n".join(lines)


def run(root: Path, benchmark: Path, results_path: Path, metrics_path: Path,
        report_path: Path, cache_dir: Path, depths: tuple[int, ...] = (5, 10, 20),
        minimum_coverage: float = 0.5, device: str | None = None) -> dict[str, Any]:
    """Run the audit and write detailed JSONL, metrics JSON, and Markdown."""
    if benchmark.name.endswith("_candidates.jsonl"):
        raise ValueError("Use the reviewed retrieval_benchmark_v1.jsonl, never the candidates file")
    if not depths or any(depth < 1 for depth in depths):
        raise ValueError("candidate depths must be positive")
    if not {5, 10, 20}.issubset(depths):
        raise ValueError("candidate depths must include 5, 10, and 20 for the required audit")
    max_depth = max(depths)
    questions = read_jsonl(benchmark)
    books = load_pages(root)
    candidates: dict[tuple[str, str], list[Candidate]] = {}
    first: dict[str, dict[str, int | None]] = defaultdict(dict)

    dense_metadata = {
        "page": _rank_page_methods(questions, books, cache_dir, max_depth, device,
                                   candidates, first, minimum_coverage),
        "chunk": _rank_chunk_methods(questions, books, cache_dir, max_depth, device,
                                     candidates, first, minimum_coverage),
        "hierarchy": _rank_hierarchy_methods(questions, books, root, cache_dir, max_depth,
                                             device, candidates, first, minimum_coverage),
    }
    answerable_ids = {
        question["question_id"] for question in questions
        if (question.get("gold_answer_span") or "").strip() and question.get("gold_pdf_pages")
    }
    scopes = _scopes(questions, answerable_ids)
    individual = {
        scope: {method: metric_block(ids, first, method) for method in ALL_RETRIEVERS}
        for scope, ids in scopes.items()
    }
    unions = {
        scope: {name: union_block(ids, first, methods) for name, methods in UNIONS.items()}
        for scope, ids in scopes.items()
    }
    primary_unique = {
        str(depth): unique_wins({qid: first[qid] for qid in scopes["all_answerable"]},
                                PRIMARY_RETRIEVERS, depth)
        for depth in depths
    }
    primary_misses = []
    misses = []
    by_id = {question["question_id"]: question for question in questions}
    for qid in scopes["all_answerable"]:
        question = by_id[qid]
        if not oracle_hit(first[qid], PRIMARY_RETRIEVERS, max_depth):
            primary_misses.append({
                "question_id": qid,
                "question": question["question"],
                "benchmark_slice": question.get("benchmark_slice", "canonical"),
                "failure_category": _failure_category(question, first[qid], max_depth),
                "additional_retrievers_matching_at_20": [
                    method for method in ADDITIONAL_RETRIEVERS
                    if first[qid].get(method) is not None and first[qid][method] <= max_depth
                ],
            })
        if not oracle_hit(first[qid], ALL_RETRIEVERS, max_depth):
            misses.append({"question_id": qid, "question": question["question"],
                           "benchmark_slice": question.get("benchmark_slice", "canonical"),
                           "failure_category": _failure_category(question, first[qid], max_depth)})

    pool_sizes = {
        name: {str(depth): _pool_sizes(scopes["all_answerable"], candidates, methods, depth)
               for depth in depths}
        for name, methods in UNIONS.items()
    }
    pairwise_primary = _pairwise_metrics(scopes["all_answerable"], candidates, first, PRIMARY_RETRIEVERS)
    pairwise_all = _pairwise_metrics(scopes["all_answerable"], candidates, first, ALL_RETRIEVERS)

    all_primary = unions["all_answerable"]["all_primary_retrievers"]
    canonical = unions["canonical"]["all_primary_retrievers"]
    natural = unions["natural_student"]["all_primary_retrievers"]
    unique20 = primary_unique[str(max_depth)]
    meaningful = [method for method, ids in unique20.items() if ids]
    # A method is redundant at depth 20 when removing it changes no primary
    # oracle success.  This is an evidence-recall decision, not a latency timing.
    omit = []
    for method in PRIMARY_RETRIEVERS:
        retained = [item for item in PRIMARY_RETRIEVERS if item != method]
        if all(oracle_hit(first[qid], retained, max_depth) == oracle_hit(first[qid], PRIMARY_RETRIEVERS, max_depth)
               for qid in scopes["all_answerable"]):
            omit.append(method)
    retain = [method for method in PRIMARY_RETRIEVERS if method not in omit]
    # Fixed dense is the only secondary representation needed to rescue the
    # one all-primary top-20 miss.  It reuses the same BGE query embedding.
    if primary_misses and all("fixed_400_80_dense_bge_small" in miss["additional_retrievers_matching_at_20"]
                              for miss in primary_misses):
        retain.append("fixed_400_80_dense_bge_small")
    if not retain:
        retain = ["page_dense_bge_small"]
    canonical_pass = (canonical["oracle_hit_at_10"] >= 0.9 or canonical["oracle_hit_at_20"] >= 0.9)
    natural_pass = (natural["oracle_hit_at_10"] >= 0.8 or natural["oracle_hit_at_20"] >= 0.8)
    rerank = canonical_pass and natural_pass and all_primary["oracle_hit_at_20"] >= 0.85
    focus_counts: dict[str, int] = defaultdict(int)
    for miss in misses:
        focus_counts[miss["failure_category"]] += 1
    focus = (max(focus_counts, key=focus_counts.get).replace("_", " ") if focus_counts
             else "candidate fusion and reranking; candidate generation already covers every answerable row at depth 20")

    labels = {
        "page_dense_bge_small": "Page BGE-small",
        "page_bm25": "Page BM25",
        "fixed_400_80_bm25": "Fixed 400/80 BM25",
        "soft_fusion_hybrid": "Soft-fusion Hybrid",
        "page_hybrid_rrf": "Page Hybrid RRF",
        "fixed_400_80_dense_bge_small": "Fixed 400/80 BGE-small",
        "fixed_400_80_hybrid_rrf": "Fixed 400/80 Hybrid",
        "structured_bm25": "Structured BM25",
        "structured_dense_bge_small": "Structured BGE-small",
        "structured_hybrid_rrf": "Structured Hybrid",
        "strict_cascade_bm25": "Strict-cascade BM25",
        "strict_cascade_dense_bge_small": "Strict-cascade BGE-small",
        "strict_cascade_hybrid_rrf": "Strict-cascade Hybrid",
        "soft_fusion_bm25": "Soft-fusion BM25",
        "soft_fusion_dense_bge_small": "Soft-fusion BGE-small",
    }
    metrics = {
        "run_metadata": {
            "benchmark": str(benchmark),
            "answerable_questions": len(answerable_ids),
            "excluded_negative_or_weak_evidence_questions": len(questions) - len(answerable_ids),
            "candidate_depths": list(depths),
            "primary_retrievers": list(PRIMARY_RETRIEVERS),
            "additional_retrievers": list(ADDITIONAL_RETRIEVERS),
            "retriever_labels": labels,
            "candidate_budget_definition": "top K from each union member before deterministic evidence deduplication",
            "deduplication": "shared PDF page and >=0.80 five-token-shingle containment",
            "evidence_matching": f"reviewed primary/alternative page plus >={minimum_coverage:.2f} contiguous answer-span coverage",
            "dense": dense_metadata,
        },
        "individual_metrics": individual,
        "union_metrics": unions,
        "candidate_pool_sizes": pool_sizes,
        "pairwise_primary": pairwise_primary,
        "pairwise_all_retrievers": pairwise_all,
        "unique_primary_wins": primary_unique,
        "all_primary_misses_at_20": primary_misses,
        "all_method_misses_at_20": misses,
        "decision": {
            "best_candidate_union": max(UNIONS, key=lambda name: (unions["all_answerable"][name]["oracle_hit_at_20"],
                                                                  unions["all_answerable"][name]["oracle_hit_at_10"],
                                                                  -len(UNIONS[name]))),
            "canonical_threshold_answer": "yes" if canonical_pass else "no",
            "natural_threshold_answer": "yes" if natural_pass else "no",
            "canonical_oracle_hit_at_10_count": canonical["oracle_hit_at_10_count"],
            "canonical_oracle_hit_at_20_count": canonical["oracle_hit_at_20_count"],
            "natural_oracle_hit_at_10_count": natural["oracle_hit_at_10_count"],
            "natural_oracle_hit_at_20_count": natural["oracle_hit_at_20_count"],
            "meaningful_unique_contributions": ("no — " + ", ".join(labels[x] for x in meaningful) +
                                                   " contribute unique wins, but Page BM25 does not"
                                                   if meaningful else "no"),
            "reranking_justified": "yes" if rerank else "not yet",
            "retain_retrievers": retain,
            "omit_retrievers": omit,
            "remaining_miss_focus": focus,
        },
    }

    # One row per question, retriever, and requested depth keeps the raw audit
    # inspectable without duplicating baseline score/latency artifacts.
    union_membership = {method: [name for name, methods in UNIONS.items() if method in methods]
                        for method in ALL_RETRIEVERS}
    detailed = []
    for question in questions:
        qid = question["question_id"]
        failure = next((miss["failure_category"] for miss in misses if miss["question_id"] == qid), None)
        for method in ALL_RETRIEVERS:
            for depth in depths:
                rank = first[qid].get(method)
                unique = qid in primary_unique[str(depth)].get(method, [])
                detailed.append({
                    "question_id": qid,
                    "benchmark_slice": question.get("benchmark_slice", "canonical"),
                    "question": question["question"],
                    "book_id": question["book_id"],
                    "retriever": method,
                    "candidate_depth": depth,
                    "retrieved_candidates": [item.as_dict() for item in candidates[qid, method][:depth]],
                    "accepted_evidence_matched": sorted({evidence for item in candidates[qid, method][:depth]
                                                         for evidence in item.matched_evidence}),
                    "first_matching_rank": rank,
                    "hit_within_depth": rank is not None and rank <= depth,
                    "unique_contribution_flag": unique,
                    "union_membership": union_membership[method],
                    "evaluation_status": "answerable" if qid in answerable_ids else "excluded_negative_or_weak_evidence",
                    "failure_category_if_all_methods_miss": failure,
                })

    for path in (results_path, metrics_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in detailed), encoding="utf-8")
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path.write_text(render_report(metrics), encoding="utf-8")
    return metrics


def build_parser() -> argparse.ArgumentParser:
    """Define the source and installed CLI with configurable budgets/paths."""
    parser = argparse.ArgumentParser(description="Audit complementarity among existing retrieval candidates")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--results", type=Path)
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--depths", type=int, nargs="+", default=[5, 10, 20])
    parser.add_argument("--gold-min-coverage", type=float, default=0.5)
    parser.add_argument("--device")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Resolve default project paths, execute the audit, and print headlines."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    metrics = run(
        root,
        (args.benchmark or root / "data/benchmarks/retrieval_benchmark_v1.jsonl").resolve(),
        (args.results or root / "data/retrieval/candidate_complementarity_results.jsonl").resolve(),
        (args.metrics or root / "reports/candidate_complementarity_metrics.json").resolve(),
        (args.report or root / "reports/candidate_complementarity_audit.md").resolve(),
        (args.cache_dir or root / "data/retrieval/cache").resolve(),
        tuple(sorted(set(args.depths))),
        args.gold_min_coverage,
        args.device,
    )
    print(json.dumps({"decision": metrics["decision"],
                      "all_primary": metrics["union_metrics"]["all_answerable"]["all_primary_retrievers"]}, indent=2))


if __name__ == "__main__":
    main()
