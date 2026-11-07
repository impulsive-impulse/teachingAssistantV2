"""Explicit fresh inference, durable resumes and zero-call raw-output replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .assessment_baselines import baseline_rankings
from .assessment_budget import CallLedger
from .assessment_context import context_encoder, pack_units, validate_context
from .assessment_generation import validate_answer
from .assessment_inference import dispatch_paid, load_pipeline
from .assessment_ingestion import (
    ingest_benchmark, load_assessment_model, read_evaluation_labels, validate_reference_alignment,
)
from .assessment_protocol import fingerprint, read_json
from .assessment_scoring import aggregate_scores, context_metrics, paired_delta, score_official
from .assessment_selector import selected_context
from .experiment_tracking import write_json
from .source_provenance import ProvenanceText, SourceDocument


RUN_VERSION = "assessment-run-v1"
ARMS = ("dense_top_k", "hybrid_rrf", "proposed", "without_cross_document_selection")


def _raw_path(directory: Path, question_id: str, arm: str) -> Path:
    return directory / "raw" / (fingerprint({"question_id": question_id, "arm": arm}) + ".json")


def rebuild(directory: Path, root: Path) -> dict[str, Any]:
    manifest = read_json(directory / "run.json")
    if manifest["version"] != RUN_VERSION:
        raise ValueError("unsupported evaluation run version")
    labels = read_evaluation_labels(directory / "references.json")
    if labels["checksum"] != manifest["references_checksum"]:
        raise ValueError("cached evaluation references changed")
    split = "development" if manifest["phase"] == "development" else "held_out"
    if manifest["question_ids"] != [row["question_id"] for row in labels["references"] if row["split"] == split]:
        raise ValueError("cached report must include every selected question in its declared split")
    references = {row["question_id"]: row for row in labels["references"]}
    encoder = context_encoder(root)
    scored, failed, reused, costs, unknown_cost = [], 0, 0, [], 0
    for question_id in manifest["question_ids"]:
        reference = references[question_id]
        for arm in ARMS:
            path = _raw_path(directory, question_id, arm)
            if not path.is_file():
                raise FileNotFoundError("evaluation is incomplete; a selected question/arm has no raw result")
            row = read_json(path)
            if row["checksum"] != fingerprint({key: value for key, value in row.items() if key != "checksum"}):
                raise ValueError("raw result checksum changed")
            if row["question_id"] != question_id or row["arm"] != arm or row["run_id"] != manifest["run_id"]:
                raise ValueError("raw result belongs to a different question, arm or run")
            documents = [SourceDocument.from_dict(value) for value in row["snapshot"]["source_documents"]]
            catalog = {document.document_id: document for document in documents}
            validate_context(row["context"], catalog, row["selected_evidence"], encoder)
            generated = row["generation"]
            valid = generated.get("error_code") is None
            validation = validate_answer(generated["raw_text"], row["context"], catalog) if valid else {
                "valid": False, "short_answer": "", "supporting_facts": [],
            }
            valid = valid and validation["valid"]
            failed += not valid
            reused += generated["cache_reused"]
            if not generated["cache_reused"]:
                value = generated.get("estimated_api_cost_usd")
                if value is None:
                    unknown_cost += 1
                else:
                    costs.append(value)
            values = context_metrics(
                [ProvenanceText.from_dict(segment["source_provenance"]) for segment in row["context"]["segments"]],
                documents, reference,
            )
            values.update(score_official(
                validation.get("short_answer", ""), validation.get("supporting_facts", []),
                reference, valid_output=bool(valid),
            ))
            values.update({
                "context_tokens": row["context"]["token_count"],
                "invalid_output_rate": float(not valid),
                "false_abstention_rate": float(valid and validation.get("status") == "insufficient_evidence"),
                "factual_claim_citation_completeness": float(valid and validation.get("status") == "answered"),
            })
            scored.append({"question_id": question_id, "arm": arm, "metrics": values})
    ids = manifest["question_ids"]
    by_arm = {arm: [row for row in scored if row["arm"] == arm] for arm in ARMS}
    summaries = {arm: aggregate_scores(rows, ids) for arm, rows in by_arm.items()}
    selected_references = [references[question_id] for question_id in ids]
    comparisons = {
        baseline: {
            metric: paired_delta(by_arm["proposed"], by_arm[baseline], selected_references, metric)
            for metric in ("complete_supporting_document_recall", "answer_f1", "joint_f1")
        }
        for baseline in ("dense_top_k", "hybrid_rrf", "without_cross_document_selection")
    }
    report = {
        "version": RUN_VERSION, "run_id": manifest["run_id"], "phase": manifest["phase"],
        "pipeline_sha256": manifest["pipeline_sha256"], "protocol_sha256": manifest["protocol_sha256"],
        "question_ids": ids, "metrics": summaries, "paired_comparisons": comparisons,
        "failed_or_invalid_outputs": failed, "identical_request_reuses": reused,
        "known_token_based_cost_estimate_usd": sum(costs),
        "attempts_with_unknown_cost": unknown_cost, "cost_is_invoice": False,
        "rows": scored, "cached_rebuild_model_calls": 0,
    }
    write_json(directory / "metrics.json", {**report, "checksum": fingerprint(report)})
    return report


def run_fresh(
    root: Path, directory: Path, phase: str, ledger_path: Path,
    *, provider: Any | None = None,
) -> dict[str, Any]:
    pipeline = load_pipeline(root)
    if phase not in {"development", "final_evaluation", "fresh_final_rerun"}:
        raise ValueError("fresh evaluation phase is invalid")
    if phase != "development" and pipeline["status"] != "frozen":
        raise ValueError("final and fresh-rerun execution require a frozen development-selected pipeline")
    corpus = ingest_benchmark(root, root / "app_data" / "assessment" / "inputs-v1")
    labels = read_evaluation_labels(root / "app_data" / "assessment" / "inputs-v1" / "evaluation" / "labels.json")
    validate_reference_alignment(labels, corpus)
    split = "development" if phase == "development" else "held_out"
    ids = [row["question_id"] for row in labels["references"] if row["split"] == split]
    ledger = CallLedger(ledger_path, pipeline["protocol_sha256"])
    run_path = directory / "run.json"
    if run_path.is_file():
        manifest = read_json(run_path)
        if (
            manifest["phase"] != phase or manifest["question_ids"] != ids
            or manifest["pipeline_sha256"] != fingerprint(pipeline)
            or manifest["corpus_fingerprint"] != corpus.index.corpus_fingerprint
        ):
            raise ValueError("resume directory differs from its frozen pipeline/cohort")
    else:
        if directory.exists() and any(directory.iterdir()):
            raise FileExistsError("evaluation directory is not an owned resumable run")
        directory.mkdir(parents=True, exist_ok=True)
        manifest = {
            "version": RUN_VERSION, "run_id": phase + "-" + uuid4().hex, "phase": phase,
            "question_ids": ids, "arms": list(ARMS), "pipeline_sha256": fingerprint(pipeline),
            "protocol_sha256": pipeline["protocol_sha256"], "references_checksum": labels["checksum"],
            "corpus_fingerprint": corpus.index.corpus_fingerprint, "complete": False,
        }
        write_json(run_path, manifest)
        write_json(directory / "references.json", labels)
        write_json(directory / "pipeline.json", pipeline)
    encoder, model = context_encoder(root), load_assessment_model(root)
    for question_id in ids:
        question = corpus.question(question_id)
        index = corpus.for_question(question_id)
        ranked = baseline_rankings(index, question.question, model)
        for arm in ARMS:
            path = _raw_path(directory, question_id, arm)
            if path.is_file():
                existing = read_json(path)
                if existing["checksum"] != fingerprint({key: value for key, value in existing.items() if key != "checksum"}):
                    raise ValueError("resumed raw output changed")
                continue
            if arm in {"dense_top_k", "hybrid_rrf"}:
                order = ranked[arm]
                snapshot = index.snapshot(question.question, order["ranking"], order["scores"], top_k=5)
                evidence = snapshot["evidence"]
                context = pack_units(evidence, index.catalog, encoder)
            else:
                order = ranked["hybrid_rrf"]
                snapshot = index.snapshot(question.question, order["ranking"], order["scores"], top_k=len(index.chunks))
                context, evidence = selected_context(
                    index, question.question, ranked, pipeline["selector"], encoder,
                    ablation=arm == "without_cross_document_selection",
                )
            validate_context(context, index.catalog, evidence, encoder)
            generated = dispatch_paid(
                root, question.question, context, index.catalog, pipeline, ledger,
                manifest["run_id"], phase, encoder, provider=provider,
            )
            row = {
                "version": RUN_VERSION, "run_id": manifest["run_id"], "question_id": question_id,
                "question": question.question, "runtime_input_sha256": question.runtime_input_sha256,
                "arm": arm, "snapshot": snapshot, "context": context, "selected_evidence": evidence,
                "generation": generated,
            }
            write_json(path, {**row, "checksum": fingerprint(row)})
            print(json.dumps({
                "phase": phase, "question_id": question_id, "arm": arm,
                "valid": generated["validation"]["valid"], "cache_reused": generated["cache_reused"],
                "attempts": ledger.status()["reserved_or_attempted"],
            }), flush=True)
            if generated["error_code"] == "provider_dispatch_failed":
                raise RuntimeError("provider dispatch failed; raw failure retained, run is explicitly incomplete")
    report = rebuild(directory, root)
    write_json(run_path, {**manifest, "complete": True, "ledger_status": ledger.status()})
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--fresh", action="store_true", help="Explicit paid inference; all attempts use the durable ledger.")
    modes.add_argument("--cached", action="store_true", help="Rebuild strictly from saved raw outputs; no model dispatch.")
    parser.add_argument("--phase", choices=("development", "final_evaluation", "fresh_final_rerun"), default="development")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args(argv)
    root, directory = args.root.resolve(), args.output.resolve()
    if args.cached:
        report = rebuild(directory, root)
    else:
        ledger = args.ledger.resolve() if args.ledger else root / "app_data" / "assessment" / "call_ledger.sqlite"
        report = run_fresh(root, directory, args.phase, ledger)
    print(json.dumps({
        "phase": report["phase"], "metrics": report["metrics"],
        "cost_estimate_usd": report["known_token_based_cost_estimate_usd"],
        "cached_rebuild_model_calls": report["cached_rebuild_model_calls"],
    }, indent=2))


if __name__ == "__main__":
    main()
