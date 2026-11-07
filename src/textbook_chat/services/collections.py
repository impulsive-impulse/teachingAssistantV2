"""Additive collection queries sharing the assessment context and citation layer."""

from __future__ import annotations

import threading
from typing import Any, Callable

from textbook_audit.assessment_baselines import baseline_rankings
from textbook_audit.assessment_budget import CallLedger
from textbook_audit.assessment_context import context_encoder, validate_context
from textbook_audit.assessment_generation import render_prompt, validate_answer
from textbook_audit.assessment_inference import dispatch_paid, load_pipeline
from textbook_audit.assessment_protocol import fingerprint
from textbook_audit.assessment_selector import selected_context
from textbook_audit.collection_index import CollectionIndex, collection_profile

from ..config import AppSettings
from ..domain import Backend
from ..repositories import CollectionQueryRepository, CollectionRepository


def public_query(row: dict[str, Any]) -> dict[str, Any]:
    payload = row["payload"]
    output = payload.get("validation", {})
    return {
        **{key: value for key, value in row.items() if key != "payload"},
        "output": output if output.get("valid") else None,
        "validation_errors": output.get("errors", []),
        "usage": payload.get("usage"), "timing": payload.get("timing"),
        "provider_identity": payload.get("provider_identity"),
    }


class CollectionService:
    def __init__(
        self, settings: AppSettings, repository: CollectionRepository,
        embedding: Callable[[], Any], offline_provider: Any, *, online_provider: Any | None = None,
    ):
        self.settings, self.repository = settings, repository
        self.queries = CollectionQueryRepository(repository.database)
        self.embedding, self.offline_provider, self.online_provider = embedding, offline_provider, online_provider
        self._lock = threading.RLock()
        self._indexes: dict[str, CollectionIndex] = {}

    def index(self, collection: dict[str, Any]) -> tuple[CollectionIndex, Any]:
        documents = self.repository.sources(collection["id"], collection["fingerprint"])
        profile = collection_profile(self.settings.root)
        key = fingerprint({"collection": collection["fingerprint"], "profile": fingerprint(profile)})
        with self._lock:
            model = self.embedding()
            if key not in self._indexes:
                directory = self.settings.data_dir / "assessment" / "collections" / key
                if directory.exists():
                    index = CollectionIndex.load(directory)
                    if index.collection_fingerprint != collection["fingerprint"] or index.profile != profile:
                        raise ValueError("collection index differs from its current sources/profile")
                else:
                    index = CollectionIndex.build(documents, model, profile)
                    index.save(directory)
                self._indexes[key] = index
            return self._indexes[key], model

    def ask(self, collection_id: str, question: str, backend: Backend, *, acknowledged: bool = False) -> dict[str, Any]:
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
            raise ValueError("question must contain 1-2000 characters")
        if backend is Backend.ONLINE and not acknowledged:
            raise PermissionError("Authorize sending the question and retrieved excerpts to OpenAI before online generation.")
        collection = self.repository.get(collection_id)
        if collection is None:
            raise LookupError("collection not found")
        query_id = self.queries.create(collection, question.strip(), backend)
        payload: dict[str, Any] = {}
        stage = "retrieving"
        try:
            index, model = self.index(collection)
            pipeline, encoder = load_pipeline(self.settings.root), context_encoder(self.settings.root)
            ranked = baseline_rankings(index, question, model)
            context, evidence = selected_context(index, question, ranked, pipeline["selector"], encoder)
            validate_context(context, index.catalog, evidence, encoder)
            ranking = ranked["hybrid_rrf"]
            snapshot = index.snapshot(question, ranking["ranking"], ranking["scores"], top_k=len(index.chunks))
            payload = {"snapshot": snapshot, "context": context, "selected_evidence": evidence}
            stage = "generating"
            self.queries.update(query_id, stage, payload)
            if backend is Backend.ONLINE:
                # One approval is shared with the benchmark; UI diagnostics cannot eat final/rerun reserves.
                ledger = CallLedger(
                    self.settings.root / "app_data" / "assessment" / "call_ledger.sqlite",
                    pipeline["protocol_sha256"],
                )
                generated = dispatch_paid(
                    self.settings.root, question, context, index.catalog, pipeline, ledger,
                    "collection-" + query_id, "contingency", encoder, provider=self.online_provider,
                )
            else:
                package, parts, completion = render_prompt(question, context), [], None
                for event in self.offline_provider.stream(package["prompt"]):
                    if event.type == "raw_delta":
                        parts.append(event.data["delta"])
                        payload["raw_text"] = "".join(parts)
                    elif event.type == "completed":
                        completion = event.data
                if completion is None or completion.get("response_status") != "completed":
                    raise RuntimeError("offline provider terminal completion is missing")
                validation = validate_answer(completion["raw_text"], context, index.catalog)
                generated = {
                    "raw_text": completion["raw_text"], "validation": validation,
                    "usage": completion.get("usage"), "provider_identity": completion.get("resolved_model"),
                    "timing": {"generation_latency_seconds": completion.get("latency_seconds")},
                    "prompt_checksum": package["checksum"],
                    "error_code": None if validation["valid"] else "claim_validation_failed",
                }
            payload.update(generated)
        except Exception as error:
            # Explicit durable failure boundary; never persist SDK exception strings or credential-bearing URLs.
            self.queries.update(query_id, "failed", {
                **payload, "failure_stage": stage, "failure_type": type(error).__name__,
            }, "collection_query_failed_" + stage)
            raise RuntimeError(f"Collection query failed during {stage} ({type(error).__name__}).") from None
        error_code = generated["error_code"]
        self.queries.update(query_id, "failed" if error_code else "completed", payload, error_code)
        return public_query(self.queries.get(query_id))
