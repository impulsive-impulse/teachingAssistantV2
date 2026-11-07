"""Official-score parity, fixed-budget references, failures and paired uncertainty."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pytest

from textbook_audit.assessment_baselines import baseline_rankings, retrieve_baseline
from textbook_audit.assessment_context import context_encoder, pack_units, validate_context
from textbook_audit.assessment_protocol import fingerprint
from textbook_audit.assessment_scoring import (
    aggregate_scores, context_metrics, official_scorer, paired_delta, score_official,
)
from textbook_audit.collection_index import CollectionIndex
from textbook_audit.retrieval import BM25, reciprocal_rank_fusion, stable_ranking
from textbook_audit.source_provenance import ProvenanceText, benchmark_document
from test_assessment_collections import Model, profile, sources


ROOT = Path(__file__).resolve().parents[1]


def test_standard_baselines_match_dense_bm25_and_unweighted_rrf() -> None:
    index = CollectionIndex.build(sources(), Model(), profile()).subset([document.document_id for document in sources()[:2]])
    expected_dense = index.dense_scores("plants", Model())
    expected_lexical = BM25((chunk["text"] for chunk in index.chunks), k1=1.5, b=0.75).scores("plants")
    expected_rrf = reciprocal_rank_fusion(
        [stable_ranking(expected_dense), stable_ranking(expected_lexical)], len(index.chunks), 60,
    )
    ranked = baseline_rankings(index, "plants", Model())
    np.testing.assert_allclose(ranked["dense_top_k"]["scores"], expected_dense)
    np.testing.assert_allclose(ranked["bm25"]["scores"], expected_lexical)
    np.testing.assert_allclose(ranked["hybrid_rrf"]["scores"], expected_rrf)
    for method in ranked:
        result = retrieve_baseline(index, "plants", Model(), method)
        index.validate_snapshot(result)
        assert set(result["document_ids"]) == set(index.catalog)
    with pytest.raises(ValueError, match="unknown standard"):
        retrieve_baseline(index, "plants", Model(), "proposed")


@pytest.mark.parametrize("predicted,expected", [
    ("The University of Oxford!", "University of Oxford"),
    ("yes", "no"), ("NO", "no"), ("", "correct"),
    ("United States", "United States of America"),
])
def test_official_answer_support_and_joint_metrics_are_upstream_exact(predicted, expected) -> None:
    scorer = official_scorer()
    reference = {"answer": expected, "supporting_facts": [["A", 0], ["B", 1]]}
    actual = score_official(predicted, [["A", 0], ["A", 0]], reference)
    metrics = {key: 0.0 for key in ("em", "f1", "prec", "recall", "sp_em", "sp_f1", "sp_prec", "sp_recall")}
    em, precision, recall = scorer.update_answer(metrics, predicted, expected)
    sp_em, sp_precision, sp_recall = scorer.update_sp(metrics, [["A", 0], ["A", 0]], reference["supporting_facts"])
    assert actual["answer_em"] == metrics["em"]
    assert actual["answer_f1"] == metrics["f1"]
    assert actual["supporting_fact_f1"] == metrics["sp_f1"]
    assert actual["joint_em"] == em * sp_em
    p, r = precision * sp_precision, recall * sp_recall
    assert actual["joint_f1"] == (2 * p * r / (p + r) if p + r else 0)


def test_invalid_provider_output_scores_zero_without_leaving_the_denominator() -> None:
    reference = {"answer": "correct", "supporting_facts": [["A", 0]]}
    perfect = score_official("correct", [["A", 0]], reference)
    failed = score_official("correct", [["A", 0]], reference, valid_output=False)
    assert perfect["joint_f1"] == 1
    assert failed["joint_f1"] == failed["answer_f1"] == failed["supporting_fact_f1"] == 0
    result = aggregate_scores([
        {"question_id": "one", "metrics": perfect},
        {"question_id": "two", "metrics": failed},
    ], ["one", "two"])
    assert result["questions"] == 2
    assert result["joint_f1"] == 0.5
    with pytest.raises(ValueError, match="all selected questions"):
        aggregate_scores([{"question_id": "one", "metrics": perfect}], ["one", "two"])
    with pytest.raises(ValueError, match="zero-based"):
        score_official("correct", [["A", True]], reference)


def test_complete_document_recall_does_not_inflate_partial_supporting_fact_coverage() -> None:
    first = benchmark_document("A", ["A complete supporting sentence."], "a" * 64)
    second = benchmark_document("B", ["Another complete supporting sentence."], "a" * 64)
    a = ProvenanceText.from_unit(first, "sentence:000000")
    b = ProvenanceText.from_unit(second, "sentence:000000")
    reference = {"supporting_facts": [["A", 0], ["B", 0]]}
    metrics = context_metrics([a, b.slice(0, 4)], [first, second], reference)
    assert metrics["complete_supporting_document_recall"] == 1
    assert metrics["supporting_fact_context_recall"] == 0.5
    assert metrics["complete_supporting_fact_context_recall"] == 0
    assert metrics["partial_supporting_fact_context_recall"] == 1
    assert context_metrics([a, b], [first, second], reference)["complete_supporting_fact_context_recall"] == 1
    assert context_metrics([], [first, second], reference)["complete_supporting_document_recall"] == 0


def test_paired_bootstrap_is_deterministic_and_preserves_question_type_strata() -> None:
    references = [
        {"question_id": "one", "question_type": "bridge"},
        {"question_id": "two", "question_type": "comparison"},
    ]
    proposed = [{"question_id": row["question_id"], "metrics": {"score": 1.0}} for row in references]
    baseline = [
        {"question_id": "one", "metrics": {"score": 0.0}},
        {"question_id": "two", "metrics": {"score": 1.0}},
    ]
    result = paired_delta(proposed, baseline, references, "score")
    assert result == paired_delta(proposed, list(reversed(baseline)), references, "score")
    assert result["delta"] == 0.5
    assert result["confidence_interval"] == [0.5, 0.5]
    assert result["resamples"] == 10000
    assert result["stratified_by_question_type"] is True


def test_exact_token_packing_counts_headings_and_retains_unicode_source_ranges() -> None:
    encoder = context_encoder(ROOT)
    document = benchmark_document("An exact source title", [
        "Plants \u03b2 \U0001f331 " + " ".join(f"word{number}" for number in range(100)),
        "A final source sentence.",
    ], "a" * 64)
    index = CollectionIndex.build([document], Model(), profile())
    evidence = index.retrieve("plants", Model())["evidence"]
    packed = pack_units(evidence, index.catalog, encoder, budget=47)
    validate_context(packed, index.catalog, evidence, encoder)
    assert packed["token_count"] == len(encoder.encode(packed["rendered"])) <= 47
    assert packed["segments"][-1]["truncated"] is True
    for segment in packed["segments"]:
        ProvenanceText.from_dict(segment["source_provenance"]).validate(index.catalog)
    empty = pack_units(evidence, index.catalog, encoder, budget=1)
    assert empty["segments"] == []
    assert empty["token_count"] == 0
    assert empty["evidence_state"] == "insufficient_evidence"


def test_changed_rendered_context_cannot_keep_an_old_source_map() -> None:
    encoder = context_encoder(ROOT)
    index = CollectionIndex.build(sources()[:2], Model(), profile())
    evidence = index.retrieve("Plants and circuits?", Model())["evidence"]
    packed = pack_units(evidence, index.catalog, encoder)
    altered = copy.deepcopy(packed)
    altered["segments"][0]["units"][0]["text"] = "Invented evidence."
    altered["checksum"] = fingerprint({key: value for key, value in altered.items() if key != "checksum"})
    with pytest.raises(ValueError, match="rendering"):
        validate_context(altered, index.catalog, evidence, encoder)
