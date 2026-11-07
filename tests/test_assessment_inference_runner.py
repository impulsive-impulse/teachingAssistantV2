"""Counted dispatch, secret-safe failures and replay without a provider call."""

from __future__ import annotations

import json
from unittest.mock import patch

from textbook_audit.assessment_budget import CallLedger
from textbook_audit.assessment_context import context_encoder
from textbook_audit.assessment_inference import dispatch_paid, load_pipeline
from textbook_audit.assessment_ingestion import LABEL_VERSION
from textbook_audit.assessment_protocol import fingerprint
from textbook_audit.assessment_runner import ARMS, RUN_VERSION, _raw_path, rebuild
from textbook_audit.experiment_tracking import write_json
from textbook_chat.generation.online import ProviderStreamEvent
from test_assessment_generation import ROOT, evidence, response
from test_assessment_collections import Model


class Provider:
    def __init__(self, raw):
        self.raw, self.calls = raw, 0

    def stream(self, _prompt, **kwargs):
        self.calls += 1
        assert kwargs["json_schema"]["additionalProperties"] is False
        yield ProviderStreamEvent("raw_delta", {"delta": self.raw})
        yield ProviderStreamEvent("completed", {
            "raw_text": self.raw, "resolved_model": "gpt-4o-2024-08-06",
            "response_status": "completed", "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            "latency_seconds": 0.1,
        })


def test_dispatch_counts_before_call_and_reuses_only_an_identical_run_request(tmp_path) -> None:
    index, context = evidence()
    pipeline = load_pipeline(ROOT)
    ledger = CallLedger(tmp_path / "ledger.db", pipeline["protocol_sha256"])
    provider = Provider(json.dumps(response(context)))
    first = dispatch_paid(ROOT, "Plants?", context, index.catalog, pipeline, ledger, "dev", "development", context_encoder(ROOT), provider=provider)
    same = dispatch_paid(ROOT, "Plants?", context, index.catalog, pipeline, ledger, "dev", "development", context_encoder(ROOT), provider=provider)
    fresh = dispatch_paid(ROOT, "Plants?", context, index.catalog, pipeline, ledger, "rerun", "fresh_final_rerun", context_encoder(ROOT), provider=provider)
    assert first["validation"]["valid"]
    assert same["cache_reused"] is True
    assert fresh["cache_reused"] is False
    assert provider.calls == 2
    assert ledger.status()["reserved_or_attempted"] == 2
    assert first["estimated_api_cost_usd"] == 0.00045


def test_provider_failure_is_retained_and_never_logs_exception_secret_text(tmp_path) -> None:
    index, context = evidence()
    class FailedProvider:
        def stream(self, *_args, **_kwargs):
            raise RuntimeError("SENSITIVE_CREDENTIAL_MUST_NOT_APPEAR")
    pipeline = load_pipeline(ROOT)
    ledger = CallLedger(tmp_path / "ledger.db", pipeline["protocol_sha256"])
    result = dispatch_paid(ROOT, "Plants?", context, index.catalog, load_pipeline(ROOT), ledger,
                           "dev", "development", context_encoder(ROOT), provider=FailedProvider())
    assert result["error_code"] == "provider_dispatch_failed"
    assert not result["validation"]["valid"]
    assert "SENSITIVE_CREDENTIAL" not in json.dumps(result)
    assert ledger.status()["failed"] == 1
    assert ledger.status()["dispatched_upper_bound"] == 1


def test_raw_output_rebuild_has_zero_inference_calls_and_preserves_failures(tmp_path) -> None:
    index, context = evidence()
    pipeline = load_pipeline(ROOT)
    ledger = CallLedger(tmp_path / "ledger.db", pipeline["protocol_sha256"])
    provider = Provider(json.dumps(response(context)))
    generated = dispatch_paid(ROOT, "Plants?", context, index.catalog, pipeline, ledger,
                              "fixture", "development", context_encoder(ROOT), provider=provider)
    label_core = {
        "version": LABEL_VERSION, "protocol_sha256": "a" * 64, "selection_sha256": "b" * 64,
        "source_sha256": "a" * 64, "dataset_license": "CC-BY-SA-4.0",
        "references": [{
            "question_id": "one", "split": "development", "question_type": "bridge", "answer": "Plants",
            "supporting_facts": [["Plants", 0], ["Circuits", 0]], "source_row_sha256": "c" * 64,
        }],
    }
    labels = {**label_core, "checksum": fingerprint(label_core)}
    directory = tmp_path / "raw-run"
    write_json(directory / "references.json", labels)
    write_json(directory / "run.json", {
        "version": RUN_VERSION, "run_id": "fixture", "phase": "development",
        "question_ids": ["one"], "pipeline_sha256": fingerprint(pipeline), "protocol_sha256": "a" * 64,
        "references_checksum": labels["checksum"],
    })
    snapshot = index.retrieve("Plants?", Model())
    for arm in ARMS:
        result = generated if arm != "dense_top_k" else {
            **generated, "error_code": "claim_validation_failed", "raw_text": "{}",
        }
        row = {
            "question_id": "one", "arm": arm, "run_id": "fixture", "snapshot": snapshot,
            "context": context, "selected_evidence": snapshot["evidence"], "generation": result,
        }
        write_json(_raw_path(directory, "one", arm), {**row, "checksum": fingerprint(row)})
    before = ledger.status()
    with patch("socket.socket.connect", side_effect=AssertionError("network is forbidden during replay")):
        report = rebuild(directory, ROOT)
    assert provider.calls == 1
    assert ledger.status() == before
    assert report["failed_or_invalid_outputs"] == 1
    assert report["metrics"]["dense_top_k"]["answer_f1"] == 0
    assert report["metrics"]["proposed"]["answer_f1"] == 1
    assert report["cached_rebuild_model_calls"] == 0
