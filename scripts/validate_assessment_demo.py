"""Validate the two-PDF demo; online generation requires explicit transmission permission."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.assessment_protocol import fingerprint, read_json
from textbook_audit.assessment_generation import validate_answer
from textbook_audit.experiment_tracking import write_json
from textbook_audit.source_provenance import SourceDocument
from textbook_chat.config import AppSettings
from textbook_chat.database import Database
from textbook_chat.domain import Backend
from textbook_chat.generation.offline import OfflineRuntimeManager
from textbook_chat.models.embedding import EmbeddingArtifactRegistry
from textbook_chat.models.offline import OfflineArtifactRegistry
from textbook_chat.repositories import CollectionQueryRepository, CollectionRepository
from textbook_chat.retrieval.registry import RetrievalRuntimeRegistry
from textbook_chat.services.collections import CollectionService, public_query


def verify_review(receipt: dict, review: dict) -> None:
    if review.get("version") != "assessment-demo-source-review-v1" or review.get("reviewer_kind") not in {
        "assistant source inspection", "human source inspection",
    }:
        raise ValueError("A separately identified source review is required.")
    judgments = review.get("outcomes", [])
    if not isinstance(judgments, list) or len(judgments) != len(receipt["outcomes"]):
        raise ValueError("Source review must cover every demonstration question.")
    by_case = {row["case_id"]: row for row in judgments}
    if len(by_case) != len(judgments):
        raise ValueError("Source review has duplicate question IDs.")
    for result in receipt["outcomes"]:
        judgment = by_case.get(result["case_id"])
        if (
            result["state"] != "completed" or not result["both_sources_cited"] or judgment is None
            or judgment.get("query_id") != result["query_id"]
            or judgment.get("raw_output_sha256") != result["raw_output_sha256"]
            or judgment.get("verdict") != "supported"
            or judgment.get("checks") != {
                "answers_requested_question": True, "both_source_roles_supported": True,
                "short_answer_supported": True, "valid_locations": True,
            }
        ):
            raise ValueError("Demo source review is incomplete, unsupported, or belongs to another answer.")


def verify_retained_query(query: dict, collection: dict, question: str, backend: str) -> None:
    if (
        query["question"] != question or query["backend"] != backend or query["state"] != "completed"
        or query["collection_fingerprint"] != collection["fingerprint"] or query["collection_id"] != collection["id"]
    ):
        raise ValueError("A retained answer is incomplete or belongs to another demonstration.")
    payload = query["payload"]
    documents = [SourceDocument.from_dict(row) for row in payload["snapshot"]["source_documents"]]
    validated = validate_answer(
        payload["raw_text"], payload["context"], {document.document_id: document for document in documents},
    )
    cited = {
        citation["source"]["document_id"]
        for claim in validated.get("claims", []) for citation in claim["citations"]
    }
    if not validated["valid"] or validated.get("status") != "answered" or cited != set(collection["document_ids"]):
        raise ValueError("A retained demonstration no longer has valid claims from both sources.")


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify the retained answers and separate local source review; no generation.")
    parser.add_argument("--backend", choices=("offline", "online"), default="offline")
    parser.add_argument("--authorize-online-transmission", action="store_true")
    parser.add_argument("--reuse-query", action="append", default=[], help="Explicitly reuse one already completed, revalidated question by ID.")
    parser.add_argument("--replay-query", action="append", default=[], help="Reapply the PDF adapter to retained native output; no provider call.")
    args = parser.parse_args(argv)
    if args.backend == "online" and not args.check and not args.authorize_online_transmission and not args.replay_query:
        parser.error("Online generation requires permission to transmit both textbooks' excerpts and --authorize-online-transmission.")
    if args.check and (args.reuse_query or args.replay_query):
        parser.error("--check cannot also generate or select a different receipt with --reuse-query.")
    return args


def main() -> None:
    args = arguments()
    config = read_json(ROOT / "config" / "assessment_demo_v1.json")
    settings = AppSettings.load()
    database = Database(settings.database_path)
    database.initialize()
    store = CollectionRepository(database)
    collection = next((row for row in store.list() if row["title"] == "Assessment textbooks"), None)
    if collection is None or len(collection["document_ids"]) != 2:
        raise RuntimeError("Run authorized two-PDF demo ingestion first.")
    suffix = "online-v1" if args.backend == "online" else "v1"
    receipt_path = settings.data_dir / "assessment" / ("demo-" + suffix + ".json")
    if args.check:
        receipt = read_json(receipt_path)
        if (
            receipt["checksum"] != fingerprint({key: value for key, value in receipt.items() if key != "checksum"})
            or receipt["configuration_sha256"] != fingerprint(config)
            or receipt["collection_fingerprint"] != collection["fingerprint"] or receipt["backend"] != args.backend
            or [row["case_id"] for row in receipt["outcomes"]] != [case["id"] for case in config["questions"]]
        ):
            raise ValueError("The demo receipt differs from its current configuration or sources.")
        queries = CollectionQueryRepository(database)
        for case, row in zip(config["questions"], receipt["outcomes"]):
            query = queries.get(row["query_id"])
            verify_retained_query(query, collection, case["question"], args.backend)
            if hashlib.sha256(query["payload"]["raw_text"].encode("utf-8")).hexdigest() != row.get("raw_output_sha256"):
                raise ValueError("A retained answer changed or belongs to another demonstration.")
        review_path = settings.data_dir / "assessment" / ("demo-source-review-" + suffix + ".json")
        if not review_path.is_file():
            raise FileNotFoundError("Inspect each retained answer against both PDFs and record demo-source-review-v1.json before claiming completion.")
        verify_review(receipt, read_json(review_path))
        print("Both demonstrations have exact-address checks and a separately recorded source-support review.")
        return
    queries, retained = CollectionQueryRepository(database), {}
    for query_id in args.reuse_query:
        query = queries.get(query_id)
        case = next((case for case in config["questions"] if case["question"] == query["question"]), None)
        if case is None or case["id"] in retained:
            raise ValueError("Retained query IDs must match distinct configured demo questions.")
        verify_retained_query(query, collection, case["question"], args.backend)
        retained[case["id"]] = query
    registry = RetrievalRuntimeRegistry(settings, EmbeddingArtifactRegistry(settings))
    runtime = OfflineRuntimeManager(settings, OfflineArtifactRegistry(settings)) if args.backend == "offline" else None
    service = CollectionService(settings, store, registry.embedding, runtime)
    for query_id in args.replay_query:
        original = queries.get(query_id)
        case = next((case for case in config["questions"] if case["question"] == original["question"]), None)
        if case is None or case["id"] in retained or original["backend"] != args.backend:
            raise ValueError("Replay IDs must match distinct configured questions and the selected backend.")
        replayed = service.replay_pdf_query(query_id)
        retained[case["id"]] = queries.get(replayed["id"])
    if args.backend == "online" and not args.authorize_online_transmission and len(retained) != len(config["questions"]):
        raise PermissionError("Without transmission permission every configured question must use an explicit retained query.")
    outcomes = []
    try:
        for case in config["questions"]:
            reused = case["id"] in retained
            if reused:
                saved = retained[case["id"]]
                result = public_query(saved)
            else:
                result = service.ask(
                    collection["id"], case["question"], Backend(args.backend),
                    acknowledged=args.authorize_online_transmission,
                )
                saved = service.queries.get(result["id"])
            output = result["output"]
            documents = sorted({
                citation["source"]["document_id"]
                for claim in (output["claims"] if output else []) for citation in claim["citations"]
            })
            row = {
                "case_id": case["id"], "query_id": result["id"], "state": result["state"],
                "raw_output_sha256": hashlib.sha256(saved["payload"]["raw_text"].encode("utf-8")).hexdigest(),
                "local_profile": saved["payload"].get("local_profile"),
                "attempt_id": saved["payload"].get("attempt_id"),
                "reused_query": reused,
                "execution_mode": saved["payload"].get("execution_mode", "generated"),
                "replay_of_query_id": saved["payload"].get("replay_of_query_id"),
                "estimated_api_cost_usd": saved["payload"].get("estimated_api_cost_usd"),
                "cited_document_ids": documents, "validation_errors": result["validation_errors"],
                "source_locations": [
                    {"document_id": citation["source"]["document_id"], "pdf_page": citation["source"]["pdf_page"],
                     "char_ranges": citation["source"]["char_ranges"]}
                    for claim in (output["claims"] if output else []) for citation in claim["citations"]
                ],
                "both_sources_cited": set(documents) == set(collection["document_ids"]),
            }
            outcomes.append(row)
            print(json.dumps(row), flush=True)
    finally:
        if runtime is not None:
            runtime.shutdown()
    receipt = {
        "version": config["version"], "configuration_sha256": fingerprint(config),
        "collection_fingerprint": collection["fingerprint"], "backend": args.backend,
        "local_generation": {"thinking": False, "max_output_tokens": 768} if args.backend == "offline" else None,
        "external_pdf_transmission_acknowledged": args.backend == "online" and args.authorize_online_transmission,
        "paid_calls": sum(bool(row["attempt_id"]) and not row["reused_query"] for row in outcomes), "outcomes": outcomes,
        "semantic_review": "required separately; address validity is not entailment proof",
    }
    write_json(receipt_path, {**receipt, "checksum": fingerprint(receipt)})
    if not all(row["state"] == "completed" and row["both_sources_cited"] for row in outcomes):
        raise SystemExit("Demo is incomplete; inspect the retained local raw answers instead of claiming success.")
    print("Address checks passed; semantic source review is still required. Use --check after recording it.")


if __name__ == "__main__":
    main()
