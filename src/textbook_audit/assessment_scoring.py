"""Pinned official answer/support scoring and explicitly named custom metrics."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any, Sequence

import numpy as np

from .experiment_tracking import sha256_file
from .source_provenance import ProvenanceText, SourceDocument


SCORER_SHA256 = "d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0"
SCORER_LICENSE_SHA256 = "9c264489d021e5905c0544f75e292c63f78dca56acd2aec395dd36dcc41940c7"


@lru_cache(maxsize=1)
def official_scorer() -> ModuleType:
    directory = Path(__file__).parent / "vendor"
    if (
        sha256_file(directory / "hotpot_evaluate_v1.py") != SCORER_SHA256
        or sha256_file(directory / "HOTPOT-LICENSE.txt") != SCORER_LICENSE_SHA256
    ):
        raise ValueError("vendored HotpotQA scorer or license differs from the pinned upstream bytes")
    from .vendor import hotpot_evaluate_v1
    return hotpot_evaluate_v1


def _support_pairs(value: Sequence[Sequence[Any]]) -> list[list[Any]]:
    if not isinstance(value, (tuple, list)):
        raise ValueError("supporting facts must be title/sentence pairs")
    pairs = []
    for pair in value:
        if (
            not isinstance(pair, (tuple, list)) or len(pair) != 2
            or not isinstance(pair[0], str) or not pair[0].strip()
            or isinstance(pair[1], bool) or not isinstance(pair[1], int) or pair[1] < 0
        ):
            raise ValueError("supporting fact must retain an exact title and zero-based sentence index")
        pairs.append([pair[0], pair[1]])
    return pairs


def score_official(
    short_answer: str, supporting_facts: Sequence[Sequence[Any]], reference: dict[str, Any],
    *, valid_output: bool = True,
) -> dict[str, float]:
    if not isinstance(short_answer, str) or not isinstance(reference["answer"], str):
        raise ValueError("official answer predictions and references must be strings")
    predicted = _support_pairs(supporting_facts)
    gold = _support_pairs(reference["supporting_facts"])
    if not isinstance(valid_output, bool):
        raise ValueError("output validity must be explicit")
    if not valid_output:
        short_answer, predicted = "", []
    scorer = official_scorer()
    metrics = {key: 0.0 for key in ("em", "f1", "prec", "recall", "sp_em", "sp_f1", "sp_prec", "sp_recall")}
    em, precision, recall = scorer.update_answer(metrics, short_answer, reference["answer"])
    sp_em, sp_precision, sp_recall = scorer.update_sp(metrics, predicted, gold)
    joint_precision, joint_recall = precision * sp_precision, recall * sp_recall
    return {
        "answer_em": metrics["em"], "answer_f1": metrics["f1"],
        "answer_precision": metrics["prec"], "answer_recall": metrics["recall"],
        "supporting_fact_em": metrics["sp_em"], "supporting_fact_f1": metrics["sp_f1"],
        "supporting_fact_precision": metrics["sp_prec"], "supporting_fact_recall": metrics["sp_recall"],
        "joint_em": float(em * sp_em),
        "joint_f1": 2 * joint_precision * joint_recall / (joint_precision + joint_recall)
        if joint_precision + joint_recall else 0.0,
    }


def context_metrics(
    context: Sequence[ProvenanceText], documents: Sequence[SourceDocument], reference: dict[str, Any],
) -> dict[str, float]:
    catalog = {document.document_id: document for document in documents}
    if len(catalog) != len(documents):
        raise ValueError("context metric sources must have distinct document IDs")
    gold = set(map(tuple, _support_pairs(reference["supporting_facts"])))
    if not gold:
        raise ValueError("context metrics require annotated supporting facts")
    gold_documents = {title for title, _index in gold}
    by_title = {document.title: document for document in documents}
    if len(by_title) != len(documents) or gold_documents - set(by_title):
        raise ValueError("context references do not match distinct original source titles")
    for title, index in gold:
        by_title[title].unit(f"sentence:{index:06d}")
    retained: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for text in context:
        text.validate(catalog)
        for span in text.spans:
            if text.text[span.text_start:span.text_end].strip():
                retained.setdefault((span.document_id, span.unit_id), []).append((span.source_start, span.source_end))
    selected_documents, complete_facts, partial_facts = set(), set(), set()
    for (document_id, unit_id), ranges in retained.items():
        document = catalog[document_id]
        if document.kind != "hotpotqa":
            raise ValueError("HotpotQA context metrics require benchmark sentence sources")
        unit = document.unit(unit_id)
        sentence_index = int(unit_id.split(":")[1])
        pair = (document.title, sentence_index)
        selected_documents.add(document.title)
        partial_facts.add(pair)
        covered = bytearray(len(unit.text))
        for start, end in ranges:
            covered[start:end] = b"\1" * (end - start)
        if any(not char.isspace() for char in unit.text) and all(
            char.isspace() or covered[index] for index, char in enumerate(unit.text)
        ):
            complete_facts.add(pair)
    document_hits = len(selected_documents & gold_documents)
    fact_hits = len(complete_facts & gold)
    return {
        "complete_supporting_document_recall": float(gold_documents <= selected_documents),
        "supporting_document_precision": document_hits / len(selected_documents) if selected_documents else 0.0,
        "supporting_document_recall": document_hits / len(gold_documents),
        "supporting_fact_context_precision": fact_hits / len(complete_facts) if complete_facts else 0.0,
        "supporting_fact_context_recall": fact_hits / len(gold),
        "complete_supporting_fact_context_recall": float(gold <= complete_facts),
        "partial_supporting_fact_context_recall": len(partial_facts & gold) / len(gold),
    }


def aggregate_scores(rows: Sequence[dict[str, Any]], question_ids: Sequence[str]) -> dict[str, float | int]:
    if not question_ids or len(set(question_ids)) != len(question_ids):
        raise ValueError("aggregate denominator must contain distinct selected questions")
    by_id = {row["question_id"]: row for row in rows}
    if len(by_id) != len(rows) or set(by_id) != set(question_ids):
        raise ValueError("all selected questions, including failures, must be present exactly once")
    fields = set(rows[0]["metrics"])
    if any(set(row["metrics"]) != fields for row in rows):
        raise ValueError("per-question metric shapes differ")
    result = {"questions": len(question_ids)}
    for field in sorted(fields):
        values = [by_id[question_id]["metrics"][field] for question_id in question_ids]
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) for value in values):
            raise ValueError(f"invalid metric value: {field}")
        result[field] = float(np.mean(values))
    return result


def paired_delta(
    proposed: Sequence[dict[str, Any]], baseline: Sequence[dict[str, Any]],
    references: Sequence[dict[str, Any]], metric: str, *, resamples: int = 10000, seed: int = 1729,
) -> dict[str, Any]:
    ids = [reference["question_id"] for reference in references]
    aggregate_scores(proposed, ids)
    aggregate_scores(baseline, ids)
    if isinstance(resamples, bool) or not isinstance(resamples, int) or resamples < 1:
        raise ValueError("bootstrap resample count must be positive")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("bootstrap seed must be a non-negative integer")
    p, b = {row["question_id"]: row for row in proposed}, {row["question_id"]: row for row in baseline}
    differences = np.asarray([p[question_id]["metrics"][metric] - b[question_id]["metrics"][metric] for question_id in ids])
    types = [reference["question_type"] for reference in references]
    if any(kind not in {"bridge", "comparison"} for kind in types):
        raise ValueError("bootstrap requires the frozen bridge/comparison strata")
    rng, bootstrap = np.random.default_rng(seed), np.zeros(resamples, dtype=np.float64)
    for kind in ("bridge", "comparison"):
        positions = np.asarray([index for index, value in enumerate(types) if value == kind])
        if len(positions):
            draws = rng.choice(positions, size=(resamples, len(positions)), replace=True)
            bootstrap += differences[draws].sum(axis=1)
    bootstrap /= len(ids)
    return {
        "metric": metric, "questions": len(ids), "delta": float(differences.mean()),
        "confidence_level": 0.95,
        "confidence_interval": np.quantile(bootstrap, [0.025, 0.975]).tolist(),
        "resamples": resamples, "seed": seed, "stratified_by_question_type": True,
        "wins": int((differences > 0).sum()), "ties": int((differences == 0).sum()),
        "losses": int((differences < 0).sum()),
    }
