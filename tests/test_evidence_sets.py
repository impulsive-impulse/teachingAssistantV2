"""Regression tests for gold-blind distributed evidence selectors."""

from textbook_audit.evidence_sets import METHODS, select_evidence


def chunks() -> list[dict]:
    """Build linked chunks spanning pages and sections for selector tests."""
    return [
        {"chunk_id": "a", "pdf_pages": [1], "chapter_title": "C1", "section_title": "S1",
         "previous_chunk_id": None, "next_chunk_id": "b"},
        {"chunk_id": "b", "pdf_pages": [1, 2], "chapter_title": "C1", "section_title": "S1",
         "previous_chunk_id": "a", "next_chunk_id": "c"},
        {"chunk_id": "c", "pdf_pages": [2], "chapter_title": "C1", "section_title": "S2",
         "previous_chunk_id": "b", "next_chunk_id": "d"},
        {"chunk_id": "d", "pdf_pages": [3], "chapter_title": "C2", "section_title": "S3",
         "previous_chunk_id": "c", "next_chunk_id": "e"},
        {"chunk_id": "e", "pdf_pages": [4], "chapter_title": "C2", "section_title": "S3",
         "previous_chunk_id": "d", "next_chunk_id": None},
    ]


def test_every_selector_is_deterministic_unique_and_budgeted() -> None:
    """No selector may duplicate candidates or exceed the hard context budget."""
    ranking = [2, 0, 4, 1, 3]
    for method in METHODS:
        first = select_evidence(method, ranking, chunks(), 4)
        second = select_evidence(method, ranking, chunks(), 4)
        assert first == second
        assert len(first) == len(set(first)) == 4


def test_neighbor_and_page_expansion_follow_metadata_not_gold() -> None:
    """Expansion uses links/pages and can surface a lower-ranked related chunk."""
    ranking = [2, 4, 0, 1, 3]
    assert select_evidence("neighbor_expansion", ranking, chunks(), 3) == [2, 1, 3]
    assert select_evidence("same_page_expansion", ranking, chunks(), 3) == [2, 1, 4]


def test_distinct_page_selector_increases_early_page_coverage() -> None:
    """Multi-stage selection prefers candidates introducing unseen source pages."""
    ranking = [0, 1, 2, 3, 4]
    selected = select_evidence("multi_stage_distinct_pages", ranking, chunks(), 3)
    assert selected == [0, 1, 3]
