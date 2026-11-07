"""Standard, collection-local dense, BM25 and RRF references; no proposed selector."""

from __future__ import annotations

import time
import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from .collection_index import CollectionIndex
from .retrieval import BM25, reciprocal_rank_fusion, stable_ranking


BASELINE_METHODS = ("dense_top_k", "hybrid_rrf", "bm25")


def baseline_rankings(
    index: CollectionIndex, question: str, model: Any,
    *, dense_scores: np.ndarray | None = None, rrf_k: int = 60,
) -> dict[str, dict[str, Any]]:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("baseline question must not be empty")
    if isinstance(rrf_k, bool) or not isinstance(rrf_k, int) or rrf_k < 1:
        raise ValueError("RRF constant must be positive")
    dense = index.dense_scores(question, model) if dense_scores is None else np.asarray(dense_scores)
    if dense.shape != (len(index.chunks),) or not np.isfinite(dense).all():
        raise ValueError("dense scores do not match this question scope")
    lexical = BM25((chunk["text"] for chunk in index.chunks), k1=1.5, b=0.75).scores(question)
    dense_order, lexical_order = stable_ranking(dense), stable_ranking(lexical)
    fused = reciprocal_rank_fusion([dense_order, lexical_order], len(index.chunks), rrf_k)
    return {
        "dense_top_k": {"ranking": dense_order.tolist(), "scores": dense},
        "bm25": {"ranking": lexical_order.tolist(), "scores": lexical},
        "hybrid_rrf": {"ranking": stable_ranking(fused).tolist(), "scores": fused},
    }


def retrieve_baseline(
    index: CollectionIndex, question: str, model: Any, method: str, *, top_k: int = 5,
) -> dict[str, Any]:
    if method not in BASELINE_METHODS:
        raise ValueError(f"unknown standard baseline: {method}")
    started = time.perf_counter()
    if method == "bm25":
        if not isinstance(question, str) or not question.strip():
            raise ValueError("baseline question must not be empty")
        scores = BM25((chunk["text"] for chunk in index.chunks), k1=1.5, b=0.75).scores(question)
        return index.snapshot(question, stable_ranking(scores).tolist(), scores, top_k, started=started)
    ranked = baseline_rankings(index, question, model)[method]
    return index.snapshot(question, ranked["ranking"], ranked["scores"], top_k, started=started)


def run_development_baselines(root: Path, output: Path) -> dict[str, Any]:
    from .assessment_context import context_encoder, pack_units, validate_context
    from .assessment_ingestion import (
        RuntimeCorpus, load_assessment_model, read_evaluation_labels, validate_reference_alignment,
    )
    from .assessment_protocol import fingerprint
    from .assessment_scoring import aggregate_scores, context_metrics
    from .experiment_tracking import write_json
    from .source_provenance import ProvenanceText

    if output.exists():
        raise FileExistsError("development baseline output already exists; choose a new output path")
    inputs = root / "app_data" / "assessment" / "inputs-v1"
    corpus = RuntimeCorpus.load(inputs / "runtime")
    labels = read_evaluation_labels(inputs / "evaluation" / "labels.json")
    validate_reference_alignment(labels, corpus)
    references = [row for row in labels["references"] if row["split"] == "development"]
    encoder, model = context_encoder(root), load_assessment_model(root)
    rows = []
    for reference in references:
        question = corpus.question(reference["question_id"])
        index = corpus.for_question(question.question_id)
        started = time.perf_counter()
        ranked = baseline_rankings(index, question.question, model)
        shared_latency = (time.perf_counter() - started) * 1000
        for method in BASELINE_METHODS:
            snapshot = index.snapshot(question.question, ranked[method]["ranking"], ranked[method]["scores"])
            packed = pack_units(snapshot["evidence"], index.catalog, encoder)
            validate_context(packed, index.catalog, snapshot["evidence"], encoder)
            metrics = context_metrics(
                [ProvenanceText.from_dict(segment["source_provenance"]) for segment in packed["segments"]],
                index.documents, reference,
            )
            rows.append({
                "question_id": question.question_id, "method": method,
                "runtime_input_sha256": question.runtime_input_sha256,
                "context": packed, "metrics": {**metrics, "context_tokens": packed["token_count"]},
                "shared_ranking_latency_ms": shared_latency,
            })
    ids = [reference["question_id"] for reference in references]
    report = {
        "version": "assessment-development-baselines-v1",
        "protocol_sha256": corpus.manifest["protocol_sha256"],
        "corpus_fingerprint": corpus.index.corpus_fingerprint,
        "split": "development", "question_ids": ids,
        "metrics": {
            method: aggregate_scores([row for row in rows if row["method"] == method], ids)
            for method in BASELINE_METHODS
        },
        "rows": rows, "paid_model_calls": 0,
    }
    write_json(output, {**report, "checksum": fingerprint(report)})
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.output.resolve() if args.output else root / "app_data" / "assessment" / "retrieval-development-v1.json"
    result = run_development_baselines(root, output)
    print(json.dumps({"split": result["split"], "metrics": result["metrics"], "paid_model_calls": 0}, indent=2))


if __name__ == "__main__":
    main()
