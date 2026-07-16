"""Regression tests for Phase F corpus construction and metadata."""

import numpy as np

from pathlib import Path

from textbook_audit.chunking_bakeoff import (
    STRATEGIES,
    _quality_key,
    build_corpora,
    expand_neighbor_ranking,
    lift_page_ranking,
    select_page_windows,
)


ROOT = Path(__file__).resolve().parents[1]


def test_all_phase_f_base_corpora_are_deterministic_and_front_matter_free() -> None:
    """Every strategy must build both books without any roman front-matter pages."""
    first, second = build_corpora(ROOT), build_corpora(ROOT)
    assert tuple(first) == STRATEGIES
    for strategy in STRATEGIES:
        assert set(first[strategy]) == {"biology", "physical_sciences"}
        assert {book: [chunk["chunk_id"] for chunk in chunks]
                for book, chunks in first[strategy].items()} == {
                    book: [chunk["chunk_id"] for chunk in chunks]
                    for book, chunks in second[strategy].items()}
        assert all(all(isinstance(page, int) for page in chunk["pdf_pages"])
                   for chunks in first[strategy].values() for chunk in chunks)


def test_heading_strategy_preserves_sources_and_adds_retrieval_headings() -> None:
    """Heading variants may change text/IDs but not the source-page mapping."""
    corpora = build_corpora(ROOT)
    for book in corpora["fixed_400_80"]:
        plain = corpora["fixed_400_80"][book]
        headed = corpora["fixed_400_80_headings"][book]
        assert len(plain) == len(headed)
        assert [chunk["pdf_pages"] for chunk in plain] == [chunk["pdf_pages"] for chunk in headed]
        assert all(chunk["text"].startswith("Chapter:") for chunk in headed)


def test_parent_page_ranking_is_lifted_to_multi_page_children() -> None:
    """A child inherits the best rank among every parent page it spans."""
    pages = [{"pdf_pages": [10]}, {"pdf_pages": [11]}, {"pdf_pages": [12]}]
    chunks = [{"pdf_pages": [10]}, {"pdf_pages": [11, 12]}, {"pdf_pages": [12]}]
    ranking = lift_page_ranking(chunks, pages, np.asarray([2, 0, 1]))
    assert ranking.tolist() == [1, 2, 0]


def test_neighbor_expansion_is_stable_and_deduplicated() -> None:
    """Each hit is followed by linked neighbours and emitted only once."""
    chunks = [
        {"chunk_id": "a", "previous_chunk_id": None, "next_chunk_id": "b"},
        {"chunk_id": "b", "previous_chunk_id": "a", "next_chunk_id": "c"},
        {"chunk_id": "c", "previous_chunk_id": "b", "next_chunk_id": None},
    ]
    assert expand_neighbor_ranking(np.asarray([1, 2, 0]), chunks).tolist() == [1, 0, 2]


def test_query_window_selection_uses_stable_ties_within_each_page() -> None:
    """Window scores are compared only among windows from the same page."""
    scores = np.asarray([0.4, 0.7, 0.5, 0.5])
    selected = select_page_windows(scores, [{}, {}, {}, {}],
                                   {10: [0, 1], 11: [2, 3]})
    assert selected == {10: 1, 11: 2}


def test_quality_key_accepts_legacy_phase_e_configuration() -> None:
    """Older immutable run records may identify 400-token corpora without counts."""
    block = {"hit_at_1_count": 1, "hit_at_3_count": 2,
             "hit_at_5_count": 3, "mrr": 0.5}
    record = {"configuration": {"fixed_chunk_target": 400},
              "metrics": {"natural_student": block, "overall": block}}
    assert _quality_key(record)[-1] == -544
