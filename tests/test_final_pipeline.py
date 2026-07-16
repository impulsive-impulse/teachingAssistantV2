"""Regression tests for the arbitrary-query production pipeline wrapper."""

from unittest.mock import patch

import numpy as np

from textbook_audit.final_pipeline import query_pipeline


def test_query_pipeline_returns_ranked_metadata_and_merged_context() -> None:
    """The CLI wrapper must preserve source metadata and never require gold."""
    chunks = [{"chunk_id": f"c{i}", "text": f"text {i} supporting fact",
               "pdf_pages": [i + 1], "textbook_pages": [i],
               "chapter_title": "Chapter", "section_title": f"S{i}"}
              for i in range(5)]
    pipeline = {"profile": "balanced", "chunks": {"biology": chunks},
                "resources": {}, "matrices": {"biology": np.zeros((5, 2))},
                "loaded": type("Loaded", (), {"metadata": {"model_name": "test"}})(),
                "config": {}, "chunk_index": {}, "specialist_indexes": {}}
    ranked = {"processed_query": "student question", "activated_specialists": [],
              "scores": np.asarray([0.5, 0.4, 0.3, 0.2, 0.1]),
              "ranking": np.asarray([0, 1, 2, 3, 4]), "latency_ms": 1.0}
    with patch("textbook_audit.final_pipeline.rank_combined_query",
               return_value=ranked):
        result = query_pipeline(pipeline, "student question", "biology", 3)
    assert [item["chunk_id"] for item in result["retrieved"]] == ["c0", "c1", "c2"]
    assert result["retrieved"][0]["pdf_pages"] == [1]
    assert result["assembled_context"][0]["source_chunk_ids"] == ["c0", "c1", "c2", "c3", "c4"]


def test_query_pipeline_rejects_unknown_books_and_invalid_top_k() -> None:
    """User-facing input errors should fail before local inference begins."""
    pipeline = {"chunks": {"biology": []}}
    try:
        query_pipeline(pipeline, "q", "physics")
        assert False, "unknown book should fail"
    except ValueError as error:
        assert "book_id" in str(error)
    try:
        query_pipeline(pipeline, "q", "biology", 0)
        assert False, "zero top-k should fail"
    except ValueError as error:
        assert "top_k" in str(error)


def test_lightweight_profile_uses_bm25_without_a_model() -> None:
    """The lightweight recommendation must execute without neural inference."""
    chunks = [{"chunk_id": "plants", "text": "plants make food by photosynthesis",
               "pdf_pages": [2], "textbook_pages": [1],
               "chapter_title": "Nutrition", "section_title": "Photosynthesis"},
              {"chunk_id": "other", "text": "unrelated nervous system",
               "pdf_pages": [8], "textbook_pages": [7],
               "chapter_title": "Control", "section_title": "Nerves"}]
    pipeline = {"profile": "lightweight", "chunks": {"biology": chunks},
                "resources": {}, "matrices": {}, "loaded": None,
                "config": None, "chunk_index": {}, "specialist_indexes": {}}
    result = query_pipeline(pipeline, "photosynthesis food", "biology", 1)
    assert result["retrieved"][0]["chunk_id"] == "plants"
    assert result["model"] == {"model_name": None, "retriever": "BM25"}
