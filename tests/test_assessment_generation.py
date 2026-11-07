"""Claim-level source contracts without inference or paid requests."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from textbook_audit.assessment_context import context_encoder, pack_units
from textbook_audit.assessment_generation import answer_schema, render_prompt, validate_answer
from textbook_audit.collection_index import CollectionIndex
from textbook_audit.source_provenance import benchmark_document
from test_assessment_collections import Model, profile, sources


ROOT = Path(__file__).resolve().parents[1]


def evidence():
    index = CollectionIndex.build(sources()[:2], Model(), profile())
    snapshot = index.retrieve("Plants and circuits?", Model())
    return index, pack_units(snapshot["evidence"], index.catalog, context_encoder(ROOT))


def response(context):
    segment = next(segment for segment in context["segments"] if segment["document_title"] == "Plants")
    return {
        "status": "answered", "short_answer": "Plants",
        "claims": [{
            "text": "Plants absorb light and grow.",
            "citations": [{
                "evidence_id": segment["evidence_id"], "unit_id": segment["units"][0]["unit_id"],
                "quote": "Plants absorb light and grow.",
            }],
        }],
        "missing_information": [],
    }


def test_claims_resolve_original_title_sentence_and_exact_retained_source_ranges() -> None:
    index, context = evidence()
    result = validate_answer(json.dumps(response(context)), context, index.catalog)
    assert result["valid"]
    assert result["answer"] == "Plants absorb light and grow."
    assert result["supporting_facts"] == [["Plants", 0]]
    source = result["claims"][0]["citations"][0]["source"]
    assert source["document_title"] == "Plants"
    assert source["sentence_index"] == 0
    assert source["pdf_page"] is None
    assert source["char_ranges"]
    assert "entailment" in result["semantic_support"]
    payload = response(context)
    payload["claims"][0]["text"] = "Plants absorb light."
    payload["claims"][0]["citations"][0]["quote"] = "Plants absorb light"
    narrowed = validate_answer(json.dumps(payload), context, index.catalog)
    assert narrowed["valid"]
    assert max(end for _start, end in narrowed["claims"][0]["citations"][0]["source"]["char_ranges"]) == len("Plants absorb light")


@pytest.mark.parametrize("mutation", ["empty_claims", "empty_citations", "unknown_evidence", "unknown_unit", "bad_quote", "extra_prose"])
def test_nonempty_answers_cannot_pass_without_complete_resolvable_citations(mutation) -> None:
    index, context = evidence()
    payload = response(context)
    if mutation == "empty_claims":
        payload["claims"] = []
    elif mutation == "empty_citations":
        payload["claims"][0]["citations"] = []
    elif mutation == "unknown_evidence":
        payload["claims"][0]["citations"][0]["evidence_id"] = "invented"
    elif mutation == "unknown_unit":
        payload["claims"][0]["citations"][0]["unit_id"] = "sentence:999999"
    elif mutation == "bad_quote":
        payload["claims"][0]["citations"][0]["quote"] = "Not in the source."
    else:
        payload["answer"] = "An unsupported extra claim."
    assert not validate_answer(json.dumps(payload), context, index.catalog)["valid"]


def test_insufficient_evidence_has_no_factual_answer_or_forced_citations() -> None:
    index, context = evidence()
    payload = {
        "status": "insufficient_evidence", "short_answer": "", "claims": [],
        "missing_information": ["The required source facts are missing."],
    }
    assert validate_answer(json.dumps(payload), context, index.catalog)["valid"]
    payload["short_answer"] = "A guess"
    assert not validate_answer(json.dumps(payload), context, index.catalog)["valid"]


def test_unsupported_numbers_and_low_lexical_support_are_explicit_failures() -> None:
    document = benchmark_document("Original date", ["The institution was founded in 1971."], "a" * 64)
    index = CollectionIndex.build([document], Model(), profile())
    context = pack_units(index.retrieve("Founded?", Model())["evidence"], index.catalog, context_encoder(ROOT))
    segment = context["segments"][0]
    payload = {
        "status": "answered", "short_answer": "1970",
        "claims": [{"text": "The institution was founded in 1970.", "citations": [{
            "evidence_id": segment["evidence_id"], "unit_id": segment["units"][0]["unit_id"],
            "quote": "The institution was founded in 1971.",
        }]}], "missing_information": [],
    }
    result = validate_answer(json.dumps(payload), context, index.catalog)
    assert not result["valid"]
    assert any("number absent" in message for message in result["errors"])


def test_prompt_is_shared_and_marks_document_content_as_untrusted_data() -> None:
    _index, context = evidence()
    package = render_prompt("A source question?", context)
    assert "untrusted data" in package["prompt"]
    assert "Do not force citations" in package["prompt"]
    assert "supporting_facts" not in package["prompt"]
    assert package["schema"] == answer_schema()
    assert package == render_prompt("A source question?", copy.deepcopy(context))


@pytest.mark.parametrize("raw", ['[]', '{"status":[],"short_answer":"","claims":[],"missing_information":[]}', "not JSON"])
def test_malformed_output_is_invalid_not_a_success_shaped_fallback(raw) -> None:
    index, context = evidence()
    assert not validate_answer(raw, context, index.catalog)["valid"]
