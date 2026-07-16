"""Regression tests for deterministic, gold-blind context assembly."""

from textbook_audit.context_assembly import (
    METHODS,
    _hard_budget,
    _overlap_join,
    assemble_context,
)


def chunks() -> list[dict]:
    """Create ranked chunks with overlap, repetition, and source metadata."""
    return [
        {"chunk_id": "a", "text": "one two three four five six seven eight nine",
         "pdf_pages": [2], "textbook_pages": [1], "chapter_title": "C", "section_title": "S"},
        {"chunk_id": "b", "text": "two three four five six seven eight nine ten",
         "pdf_pages": [2, 3], "textbook_pages": [1, 2], "chapter_title": "C", "section_title": "S"},
        {"chunk_id": "c", "text": "an unrelated supporting explanation",
         "pdf_pages": [9], "textbook_pages": [8], "chapter_title": "D", "section_title": "T"},
        {"chunk_id": "d", "text": "another different fact",
         "pdf_pages": [10], "textbook_pages": [9], "chapter_title": "D", "section_title": "U"},
        {"chunk_id": "e", "text": "final context fact",
         "pdf_pages": [11], "textbook_pages": [10], "chapter_title": "E", "section_title": "V"},
    ]


def test_all_assemblers_are_deterministic_and_gold_blind() -> None:
    """Every registered method must return stable segments from metadata alone."""
    for method in METHODS:
        assert assemble_context(method, list(range(5)), chunks()) == assemble_context(
            method, list(range(5)), chunks())


def test_hard_budget_never_exceeds_ceiling() -> None:
    """The last segment is truncated so fixed budgets are genuinely fixed."""
    segments = assemble_context("top5_relevance", list(range(5)), chunks())
    output = _hard_budget(segments, 12)
    assert sum(len(item["text"].split()) for item in output) == 12
    assert output[-1]["truncated"] is True


def test_overlap_join_removes_repeated_window_words() -> None:
    """Overlapping fixed chunks should not repeat the shared token window."""
    joined = _overlap_join(chunks()[0]["text"], chunks()[1]["text"])
    assert joined == "one two three four five six seven eight nine ten"


def test_overlap_merge_preserves_metadata_for_every_source_chunk() -> None:
    """Merged text must retain page/section provenance per contributing chunk."""
    output = assemble_context("overlap_merge_metadata_preserving",
                              list(range(5)), chunks())
    assert len(output) == 1
    assert [item["chunk_id"] for item in output[0]["source_metadata"]] == [
        "a", "b", "c", "d", "e"]
    assert output[0]["source_metadata"][2]["section_title"] == "T"


def test_textbook_order_changes_presentation_not_membership() -> None:
    """Source-order rendering must retain exactly the same top-five chunks."""
    ranking = [4, 2, 0, 3, 1]
    output = assemble_context("textbook_order", ranking, chunks())
    assert [item["source_chunk_ids"][0] for item in output] == ["a", "b", "c", "d", "e"]
    assert {item["source_chunk_ids"][0] for item in output} == {"a", "b", "c", "d", "e"}
