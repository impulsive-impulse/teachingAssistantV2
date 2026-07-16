"""Regression tests for the Phase E corpus, cache identity, and evaluation."""

from pathlib import Path

import numpy as np

from textbook_audit.embedding_bakeoff import (
    _sparse_scores, accepted_mapping, build_fixed_corpus, corpus_fingerprint,
    searchable_pages, select_retriever,
)


ROOT = Path(__file__).resolve().parents[1]


def test_phase_e_corpus_excludes_front_matter_and_is_deterministic() -> None:
    """The corrected corpus must exclude marked pages and rebuild identically."""
    pages = searchable_pages(ROOT)
    assert all("front_matter_or_cover" not in (page.get("extraction_notes") or [])
               for book_pages in pages.values() for page in book_pages)
    first = build_fixed_corpus(ROOT)
    second = build_fixed_corpus(ROOT)
    assert {book: len(chunks) for book, chunks in first.items()} == {
        "biology": 249, "physical_sciences": 295}
    assert {book: corpus_fingerprint(chunks) for book, chunks in first.items()} == {
        book: corpus_fingerprint(chunks) for book, chunks in second.items()}


def test_all_answerable_gold_maps_to_corrected_fixed_corpus() -> None:
    """The front-matter fix must preserve all 61 reviewed answerable mappings."""
    from textbook_audit.retrieval import read_jsonl

    questions = read_jsonl(ROOT / "data/benchmarks/retrieval_benchmark_v1.jsonl")
    pages = searchable_pages(ROOT)
    corpus = build_fixed_corpus(ROOT)
    mapped = [q["question_id"] for q in questions
              if q.get("gold_pdf_pages") and (q.get("gold_answer_span") or "").strip()
              and accepted_mapping(q, corpus[q["book_id"]], pages[q["book_id"]])["status"] == "mapped"]
    assert len(mapped) == 61


def test_fingerprint_changes_with_text() -> None:
    """An embedding cache cannot survive a retrieval-text change."""
    chunks = [{"chunk_id": "x", "text": "alpha", "pdf_pages": [1]}]
    changed = [{"chunk_id": "x", "text": "beta", "pdf_pages": [1]}]
    assert corpus_fingerprint(chunks) != corpus_fingerprint(changed)


def test_select_retriever_prioritizes_natural_student_quality() -> None:
    """Selection follows the preregistered natural-student-first ordering."""
    def result(natural_h1: int, overall_h1: int) -> dict:
        """Build one minimal dense/hybrid metric payload for selection."""
        block = {"hit_at_1_count": overall_h1, "hit_at_3_count": 2,
                 "hit_at_5_count": 3, "mrr": 0.2}
        natural = {**block, "hit_at_1_count": natural_h1}
        return {"overall": block, "slices": {"natural_student": natural}}
    assert select_retriever({"dense": result(0, 20),
                             "hybrid_rrf": result(1, 1)}) == "hybrid_rrf"


def test_sparse_scores_use_lexical_weight_dot_product() -> None:
    """Sparse scoring must match BGE-M3's documented shared-token product."""
    scores = _sparse_scores({"1": 2.0, "2": 3.0},
                            [{"1": 4.0}, {"2": 5.0}, {"3": 9.0}])
    np.testing.assert_allclose(scores, np.asarray([8.0, 15.0, 0.0]))
