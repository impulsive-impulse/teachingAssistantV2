"""Explicit generator dispatch with durable accounting and secret-safe failures."""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

from .assessment_budget import CallLedger, request_fingerprint
from .assessment_generation import render_prompt, validate_answer
from .assessment_protocol import fingerprint, load_protocol, read_json
from .assessment_selector import validate_settings
from .source_provenance import SourceDocument


def load_pipeline(root: Path) -> dict[str, Any]:
    pipeline = read_json(root / "config" / "assessment_pipeline_v1.json")
    protocol = load_protocol(root / "config" / "assessment_protocol_v1.json")
    if (
        pipeline.get("version") != "assessment-pipeline-v1"
        or pipeline.get("status") not in {"development", "frozen"}
        or pipeline.get("protocol_sha256") != fingerprint(protocol)
        or pipeline.get("generator") != protocol["shared_constraints"]["generator"]
        or pipeline.get("temperature") != 0 or pipeline.get("sdk_retries") != 0
        or pipeline.get("max_output_tokens") != 768 or pipeline.get("context_token_budget") != 1024
    ):
        raise ValueError("assessment pipeline differs from its declared fair-comparison protocol")
    for field, expected in {
        "temperature": 0, "sdk_retries": 0, "max_output_tokens": 768,
        "context_token_budget": 1024, "maximum_input_tokens": 8192,
    }.items():
        if isinstance(pipeline.get(field), bool) or not isinstance(pipeline.get(field), int) or pipeline[field] != expected:
            raise ValueError(f"assessment pipeline has an invalid frozen {field}")
    for field, expected in {
        "usd_per_million_input_tokens": 2.5, "usd_per_million_cached_input_tokens": 1.25,
        "usd_per_million_output_tokens": 10, "maximum_estimated_usd_for_500_attempts": 14.08,
    }.items():
        value = pipeline.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value != expected:
            raise ValueError(f"assessment pipeline has an invalid declared price/bound: {field}")
    validate_settings(pipeline["selector"])
    return pipeline


def online_provider(root: Path, pipeline: dict[str, Any]):
    from dotenv import load_dotenv
    from textbook_chat.generation.online import OnlineGenerationProvider, OnlineProfile

    load_dotenv(root / ".env", override=False)
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise RuntimeError("OPENAI_API_KEY is required for explicit paid assessment execution")
    profile = OnlineProfile(
        model=pipeline["generator"], max_output_tokens=pipeline["max_output_tokens"],
        temperature=0, timeout_seconds=120, max_retries=0,
        api_key_environment_variable="OPENAI_API_KEY", base_url_environment_variable="OPENAI_BASE_URL",
    )
    return OnlineGenerationProvider(profile)


def estimated_cost(usage: dict[str, Any], pipeline: dict[str, Any]) -> float | None:
    input_tokens, output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if (
        any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in (input_tokens, output_tokens))
        or input_tokens == 0
    ):
        return None
    return (
        input_tokens * pipeline["usd_per_million_input_tokens"] +
        output_tokens * pipeline["usd_per_million_output_tokens"]
    ) / 1_000_000


def dispatch_paid(
    root: Path, question: str, context: dict[str, Any], catalog: dict[str, SourceDocument],
    pipeline: dict[str, Any], ledger: CallLedger, run_id: str, phase: str, encoder: Any,
    *, provider: Any | None = None,
) -> dict[str, Any]:
    if ledger.protocol_sha256 != pipeline["protocol_sha256"]:
        raise ValueError("paid dispatch ledger belongs to a different protocol approval")
    package = render_prompt(question, context)
    input_tokens = len(encoder.encode(package["prompt"])) + len(encoder.encode(json.dumps(package["schema"])))
    if input_tokens > pipeline["maximum_input_tokens"]:
        raise ValueError("full generation input exceeds the approved cost-estimation token bound")
    request_sha256 = request_fingerprint(package, pipeline["generator"], pipeline["max_output_tokens"])
    cached = ledger.cached(run_id, request_sha256)
    if cached is not None:
        result = cached["result"]
        result["validation"] = validate_answer(result["raw_text"], context, catalog)
        result["error_code"] = None if result["validation"]["valid"] else "claim_validation_failed"
        return {**result, "attempt_id": cached["attempt_id"], "cache_reused": True, "request_sha256": request_sha256}
    resolved = provider if provider is not None else online_provider(root, pipeline)
    attempt_id = ledger.reserve(run_id, phase, request_sha256)
    ledger.start(attempt_id)
    started, raw_parts, completion = time.perf_counter(), [], None
    try:
        for event in resolved.stream(package["prompt"], json_schema=package["schema"]):
            if event.type == "raw_delta":
                raw_parts.append(event.data["delta"])
            elif event.type == "completed":
                completion = event.data
        if completion is None:
            raise RuntimeError("provider_terminal_response_missing")
        if completion.get("response_status") != "completed" or completion.get("resolved_model") != pipeline["generator"]:
            raise RuntimeError("provider_model_or_status_mismatch")
        raw = completion["raw_text"]
        validation = validate_answer(raw, context, catalog)
        result = {
            "raw_text": raw, "validation": validation, "provider_identity": completion["resolved_model"],
            "usage": completion.get("usage") or {},
            "timing": {
                "generation_latency_seconds": completion.get("latency_seconds"),
                "time_to_first_token_seconds": completion.get("time_to_first_token_seconds"),
            },
            "estimated_api_cost_usd": estimated_cost(completion.get("usage") or {}, pipeline),
            "prompt_checksum": package["checksum"],
            "error_code": None if validation["valid"] else "claim_validation_failed",
        }
    except Exception as error:
        result = {
            "raw_text": "".join(raw_parts), "validation": {"valid": False, "errors": ["provider dispatch failed"]},
            "provider_identity": None, "usage": {}, "estimated_api_cost_usd": None,
            "timing": {"generation_latency_seconds": time.perf_counter() - started},
            "prompt_checksum": package["checksum"], "error_code": "provider_dispatch_failed",
            "provider_error_type": type(error).__name__,
            "provider_http_status": getattr(error, "status_code", None),
        }
    ledger.finish(attempt_id, result, error_code=result["error_code"])
    return {**result, "attempt_id": attempt_id, "cache_reused": False, "request_sha256": request_sha256}
