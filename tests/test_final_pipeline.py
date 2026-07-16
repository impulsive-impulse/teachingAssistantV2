"""Compatibility tests for callers of the pre-freeze final-pipeline module."""

from pathlib import Path

from textbook_audit.final_pipeline import query_pipeline
from textbook_audit.retrieval_baseline import (RetrievalBaseline, load_config)


ROOT = Path(__file__).resolve().parents[1]


def test_compatibility_query_delegates_to_frozen_runtime(monkeypatch) -> None:
    """The legacy helper must expose v1 evidence without implementing ranking."""
    pipeline = RetrievalBaseline.__new__(RetrievalBaseline)
    pipeline.config = load_config(root=ROOT)
    expected = type("Result", (), {"to_dict": lambda self: {
        "evidence": [{"evidence_id": "biology:fixed:00000"}],
        "assembled_context": [],
    }})()
    monkeypatch.setattr(pipeline, "retrieve", lambda question, book, include: expected)
    result = query_pipeline(pipeline, "How do plants eat?", "biology", 5)
    assert result["retrieved"] == [{"evidence_id": "biology:fixed:00000"}]
    assert result["profile"] == "balanced"


def test_compatibility_query_rejects_nonfrozen_top_k() -> None:
    """The facade may not override the canonical final result count."""
    pipeline = RetrievalBaseline.__new__(RetrievalBaseline)
    pipeline.config = load_config(root=ROOT)
    try:
        query_pipeline(pipeline, "question", "biology", 3)
        assert False, "non-v1 top_k should fail"
    except ValueError as error:
        assert "top_k" in str(error)
