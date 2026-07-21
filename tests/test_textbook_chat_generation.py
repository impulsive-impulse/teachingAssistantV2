"""Regression coverage for the production Generation Baseline v1 boundary."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from textbook_chat.generation.online import (
    IncrementalAnswerExtractor,
    OnlineGenerationProvider,
    OnlineProfile,
)
from textbook_chat.generation.prompt import build_prompt, validate_answer


ROOT = Path(__file__).resolve().parents[1]


def _snapshot() -> dict:
    evidence = []
    for rank, page in enumerate((30, 10, 20, 40, 50), 1):
        evidence.append({
            "rank": rank,
            "evidence_id": f"chunk-{rank}",
            "pdf_pages": [page],
            "textbook_pages": [page - 2],
            "evidence_text": f"Evidence from page {page}.",
        })
    return {"question": "What does the textbook explain?", "evidence": evidence}


def test_prompt_uses_exact_frozen_strategy_and_page_order() -> None:
    package = build_prompt(_snapshot())

    assert package.prompt.startswith("/no_think\nUse only the supplied textbook evidence.")
    assert "First select the relevant evidence IDs internally" in package.prompt
    assert [item["pdf_page"] for item in package.evidence_items] == [10, 20, 30, 40, 50]
    assert [item["evidence_id"] for item in package.evidence_items] == ["E1", "E2", "E3", "E4", "E5"]
    assert "Evidence from page 10" in package.prompt
    assert len(package.checksum) == 64


def test_frozen_validator_rejects_invented_citation_pages() -> None:
    package = build_prompt(_snapshot())
    raw = json.dumps({
        "status": "answered",
        "answer": "An answer.",
        "selected_evidence_ids": ["E1"],
        "citations": [{"evidence_id": "E1", "pdf_page": 999, "textbook_page": 8}],
        "missing_information": [],
    })

    result = validate_answer(raw, package)

    assert result["valid"] is False
    assert "citation page metadata does not match supplied evidence" in result["errors"]


def test_incremental_answer_extractor_handles_network_splits_and_escapes() -> None:
    extractor = IncrementalAnswerExtractor()
    chunks = ['{"status":"answered","ans', 'wer": "Line 1\\n', 'Line \\"two\\"', '","selected_evidence_ids":[]}']

    assert "".join(extractor.feed(chunk) for chunk in chunks) == 'Line 1\nLine "two"'


def test_online_stream_is_locked_and_emits_validated_raw_json() -> None:
    profile = OnlineProfile.load(ROOT)
    raw = json.dumps({
        "status": "answered",
        "answer": "The streamed answer.",
        "selected_evidence_ids": ["E1"],
        "citations": [{"evidence_id": "E1", "pdf_page": 10, "textbook_page": 8}],
        "missing_information": [],
    })
    response = SimpleNamespace(
        id="resp_123",
        status="completed",
        model="gpt-4o-2024-08-06",
        usage=SimpleNamespace(input_tokens=100, output_tokens=20, total_tokens=120),
    )
    events = [
        SimpleNamespace(type="response.output_text.delta", delta=raw[:50]),
        SimpleNamespace(type="response.output_text.delta", delta=raw[50:]),
        SimpleNamespace(type="response.completed", response=response),
    ]

    class FakeStream(list):
        closed = False

        def close(self):
            self.closed = True

    stream = FakeStream(events)

    class FakeResponses:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return stream

    responses = FakeResponses()
    provider = OnlineGenerationProvider(profile, client=SimpleNamespace(responses=responses))

    emitted = list(provider.stream("frozen prompt"))

    assert profile.model == "gpt-4o-2024-08-06"
    assert profile.max_output_tokens == 768
    assert profile.max_retries == 0
    assert responses.kwargs["model"] == "gpt-4o-2024-08-06"
    assert responses.kwargs["temperature"] == 0.0
    assert responses.kwargs["max_output_tokens"] == 768
    assert responses.kwargs["stream"] is True
    assert responses.kwargs["text"]["format"]["strict"] is True
    assert stream.closed is True
    assert "".join(event.data["delta"] for event in emitted if event.type == "answer_delta") == "The streamed answer."
    assert emitted[-1].data["raw_text"] == raw
    assert emitted[-1].data["usage"]["total_tokens"] == 120


def test_prompt_rejects_any_non_five_snapshot() -> None:
    snapshot = _snapshot()
    snapshot["evidence"] = snapshot["evidence"][:4]
    with pytest.raises(ValueError, match="exactly five"):
        build_prompt(snapshot)
