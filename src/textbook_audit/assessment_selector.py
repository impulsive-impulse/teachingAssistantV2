"""Query-local, budgeted multi-document evidence allocation and its named ablation."""

from __future__ import annotations

import argparse
import itertools
import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from .assessment_baselines import baseline_rankings
from .assessment_context import context_encoder, pack_units, unit_parts, validate_context
from .assessment_ingestion import (
    RuntimeCorpus, load_assessment_model, read_evaluation_labels, validate_reference_alignment,
)
from .assessment_protocol import fingerprint
from .assessment_scoring import aggregate_scores, context_metrics
from .experiment_tracking import write_json
from .retrieval import BM25
from .source_provenance import ProvenanceText, require_retained_spans


SELECTOR_VERSION = "budgeted-cross-document-selection-v1"
DEFAULT_SETTINGS = {
    "version": SELECTOR_VERSION, "candidate_documents": 6, "units_per_document": 3,
    "title_link_weight": 0.2, "weak_dense_threshold": 0.25,
}


def validate_settings(settings: dict[str, Any]) -> None:
    if not isinstance(settings, dict) or set(settings) != set(DEFAULT_SETTINGS) or settings["version"] != SELECTOR_VERSION:
        raise ValueError("cross-document selector settings have invalid fields or version")
    for field in ("candidate_documents", "units_per_document"):
        value = settings[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"selector {field} must be a positive integer")
    for field in ("title_link_weight", "weak_dense_threshold"):
        value = settings[field]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not np.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"selector {field} must be a finite value between zero and one")


def _normalized(text: str) -> str:
    return " " + " ".join(re.findall(r"\w+", text.casefold())) + " "


def selected_evidence(
    index, question: str, ranked: dict[str, dict[str, Any]], settings: dict[str, Any],
) -> list[dict[str, Any]]:
    """Allocate source units without access to reference answers or support labels."""
    validate_settings(settings)
    if not isinstance(question, str) or not question.strip():
        raise ValueError("selector question must not be empty")
    dense = np.asarray(ranked["dense_top_k"]["scores"])
    lexical = np.asarray(ranked["bm25"]["scores"])
    if (
        dense.shape != (len(index.chunks),) or lexical.shape != dense.shape
        or not np.isfinite(dense).all() or not np.isfinite(lexical).all()
    ):
        raise ValueError("selector rankings do not match the source corpus")
    if float(dense.max()) < settings["weak_dense_threshold"] and float(lexical.max()) <= 0:
        return []
    candidates = {}
    for position, chunk_index in enumerate(ranked["hybrid_rrf"]["ranking"]):
        chunk = index.chunks[chunk_index]
        document_id = chunk["document_id"]
        candidates.setdefault(document_id, []).append((position, chunk))
    document_order = list(candidates)
    anchor_text = " ".join(
        chunk["text"] for document_id in document_order[:2] for _position, chunk in candidates[document_id][:1]
    )
    linked = {
        document_id for document_id in document_order
        if len(index.catalog[document_id].title.strip()) >= 4
        and _normalized(index.catalog[document_id].title) in _normalized(anchor_text)
        and document_id not in document_order[:2]
    }
    doc_scores = {
        document_id: 1 / (1 + candidates[document_id][0][0]) +
        settings["title_link_weight"] * (document_id in linked)
        for document_id in document_order
    }
    document_order.sort(key=lambda document_id: (-doc_scores[document_id], document_id))
    document_order = document_order[:settings["candidate_documents"]]
    by_document = {}
    for document_id in document_order:
        choices, seen = [], set()
        for position, chunk in candidates[document_id]:
            mapped = ProvenanceText.from_dict(chunk["source_provenance"])
            for unit_id, part in unit_parts(mapped):
                if part.evidence_id in seen:
                    continue
                seen.add(part.evidence_id)
                choices.append((position, unit_id, part, chunk))
        query = question + (" " + index.catalog[document_id].title if document_id in linked else "")
        scores = BM25((part.text for _position, _unit, part, _chunk in choices), k1=1.5, b=0.75).scores(query)
        order = sorted(range(len(choices)), key=lambda number: (
            -float(scores[number]), choices[number][0], choices[number][1], choices[number][2].evidence_id,
        ))
        by_document[document_id] = [choices[number] for number in order[:settings["units_per_document"]]]
    output = []
    for round_number in range(settings["units_per_document"]):
        for document_id in document_order:
            if round_number >= len(by_document[document_id]):
                continue
            _position, _unit_id, part, chunk = by_document[document_id][round_number]
            part.validate(index.catalog)
            require_retained_spans(part, [ProvenanceText.from_dict(chunk["source_provenance"])])
            output.append({
                "evidence_id": part.evidence_id, "chunk_id": chunk["chunk_id"],
                "document_id": document_id, "text": part.text, "rank": len(output) + 1,
                "source_provenance": part.to_dict(),
            })
    return output


def selected_context(index, question, ranked, settings, encoder, *, ablation: bool = False):
    validate_settings(settings)
    if not isinstance(ablation, bool):
        raise ValueError("ablation mode must be explicit")
    if ablation:
        ranking = ranked["hybrid_rrf"]
        evidence = index.snapshot(question, ranking["ranking"], ranking["scores"], top_k=5)["evidence"]
    else:
        evidence = selected_evidence(index, question, ranked, settings)
    packed = pack_units(evidence, index.catalog, encoder, budget=1024)
    validate_context(packed, index.catalog, evidence, encoder)
    return packed, evidence


def tune_development(root: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError("selector development output already exists")
    inputs = root / "app_data" / "assessment" / "inputs-v1"
    corpus = RuntimeCorpus.load(inputs / "runtime")
    labels = read_evaluation_labels(inputs / "evaluation" / "labels.json")
    validate_reference_alignment(labels, corpus)
    references = [row for row in labels["references"] if row["split"] == "development"]
    encoder, model = context_encoder(root), load_assessment_model(root)
    cache = {}
    for reference in references:
        question = corpus.question(reference["question_id"])
        index = corpus.for_question(question.question_id)
        cache[question.question_id] = (index, baseline_rankings(index, question.question, model), question.question)
    trials = []
    for doc_count, unit_count, link_weight in itertools.product((6, 8, 10), (1, 2, 3), (0.0, 0.2)):
        settings = {
            **DEFAULT_SETTINGS, "candidate_documents": doc_count,
            "units_per_document": unit_count, "title_link_weight": link_weight,
        }
        rows = []
        for reference in references:
            index, ranked, question = cache[reference["question_id"]]
            packed, _evidence = selected_context(index, question, ranked, settings, encoder)
            values = context_metrics(
                [ProvenanceText.from_dict(segment["source_provenance"]) for segment in packed["segments"]],
                index.documents, reference,
            )
            rows.append({
                "question_id": reference["question_id"],
                "metrics": {**values, "context_tokens": packed["token_count"]},
            })
        summary = aggregate_scores(rows, [reference["question_id"] for reference in references])
        trials.append({"settings": settings, "metrics": summary, "rows": rows})
    def key(trial):
        metrics = trial["metrics"]
        return (
            metrics["complete_supporting_document_recall"],
            metrics["complete_supporting_fact_context_recall"],
            metrics["supporting_fact_context_recall"], metrics["supporting_document_precision"],
            -metrics["context_tokens"], -trial["settings"]["title_link_weight"],
        )
    winner = max(trials, key=key)
    result = {
        "version": SELECTOR_VERSION, "split": "development",
        "question_ids": [reference["question_id"] for reference in references],
        "protocol_sha256": corpus.manifest["protocol_sha256"],
        "corpus_fingerprint": corpus.index.corpus_fingerprint,
        "selected_settings": winner["settings"], "selected_metrics": winner["metrics"], "trials": trials,
        "ablation": "bypass budgeted cross-document selection; retain standard hybrid ranking and the shared packer",
        "paid_model_calls": 0,
    }
    write_json(output, {**result, "checksum": fingerprint(result)})
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.output.resolve() if args.output else root / "app_data" / "assessment" / "selector-development-v1.json"
    result = tune_development(root, output)
    print(json.dumps({
        "split": result["split"], "selected_settings": result["selected_settings"],
        "selected_metrics": result["selected_metrics"], "paid_model_calls": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
