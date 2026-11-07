"""Gold-blind source allocation, exact budgets, explicit weak evidence and ablation."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pytest

from textbook_audit.assessment_baselines import baseline_rankings
from textbook_audit.assessment_context import context_encoder, pack_units
from textbook_audit.assessment_selector import DEFAULT_SETTINGS, selected_context, selected_evidence
from textbook_audit.collection_index import CollectionIndex
from textbook_audit.source_provenance import ProvenanceText
from test_assessment_collections import Model, profile, sources


ROOT = Path(__file__).resolve().parents[1]


def test_selector_preserves_each_original_source_and_is_independent_of_labels() -> None:
    index = CollectionIndex.build(sources(), Model(), profile())
    ranked = baseline_rankings(index, "Plants and circuits?", Model())
    settings = {**DEFAULT_SETTINGS, "candidate_documents": 3}
    selected = selected_evidence(index, "Plants and circuits?", ranked, settings)
    altered = {**ranked, "answer": "An unrelated label", "supporting_facts": [["invented", 99]]}
    assert selected == selected_evidence(index, "Plants and circuits?", altered, settings)
    assert {item["document_id"] for item in selected} == set(index.catalog)
    for item in selected:
        ProvenanceText.from_dict(item["source_provenance"]).validate(index.catalog)


def test_named_ablation_is_exactly_standard_hybrid_with_the_shared_packer() -> None:
    index = CollectionIndex.build(sources(), Model(), profile())
    question = "Plants and circuits?"
    ranked = baseline_rankings(index, question, Model())
    encoder = context_encoder(ROOT)
    actual, evidence = selected_context(index, question, ranked, DEFAULT_SETTINGS, encoder, ablation=True)
    hybrid = ranked["hybrid_rrf"]
    expected = index.snapshot(question, hybrid["ranking"], hybrid["scores"], top_k=5)
    assert evidence == expected["evidence"]
    assert actual == pack_units(expected["evidence"], index.catalog, encoder)


def test_weak_evidence_does_not_force_two_sources_or_successful_context() -> None:
    index = CollectionIndex.build(sources(), Model(), profile())
    ranked = baseline_rankings(index, "Unanswerable?", Model())
    ranked["dense_top_k"]["scores"] = np.zeros(len(index.chunks))
    ranked["bm25"]["scores"] = np.zeros(len(index.chunks))
    packed, evidence = selected_context(index, "Unanswerable?", ranked, DEFAULT_SETTINGS, context_encoder(ROOT))
    assert evidence == []
    assert packed["segments"] == []
    assert packed["evidence_state"] == "insufficient_evidence"


def test_context_budget_and_source_scope_survive_source_selection() -> None:
    index = CollectionIndex.build(sources(), Model(), profile()).subset([document.document_id for document in sources()[:2]])
    ranked = baseline_rankings(index, "Plants and circuits?", Model())
    encoder = context_encoder(ROOT)
    packed, selected = selected_context(index, "Plants and circuits?", ranked, DEFAULT_SETTINGS, encoder)
    assert packed["token_count"] == len(encoder.encode(packed["rendered"])) <= 1024
    assert {item["document_id"] for item in selected} <= set(index.catalog)
    invalid = copy.deepcopy(DEFAULT_SETTINGS)
    invalid["candidate_documents"] = True
    with pytest.raises(ValueError, match="positive integer"):
        selected_evidence(index, "Plants?", ranked, invalid)
