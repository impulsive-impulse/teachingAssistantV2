"""Regression tests for the zero-surprise OpenAI generation runner."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from textbook_audit.generation_benchmark import read_jsonl
from textbook_audit.generation_experiments import ROOT, load_experiment_config
from textbook_audit.openai_generation import (
    OpenAIResponsesGenerator,
    PlannedRequest,
    answer_json_schema,
    build_plan,
    build_preflight,
    load_env_file,
    load_online_config,
    _result_row,
    run_experiment,
)
from textbook_audit.openai_generation_report import build_labeled_packet, build_review_packet


CONFIG_PATH = ROOT / "config/openai_generation_experiments_v1.json"


class FakeResponses:
    """Record request arguments and return one valid, non-network response."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        """Return a Responses API-shaped object without contacting OpenAI."""
        self.calls.append(kwargs)
        raw = json.dumps({
            "status": "answered",
            "answer": "A supported answer.",
            "selected_evidence_ids": [],
            "citations": [],
            "missing_information": [],
        })
        return SimpleNamespace(
            id="resp_test", status="completed", model="gpt-4o-test",
            output_text=raw,
            usage=SimpleNamespace(input_tokens=20, output_tokens=10, total_tokens=30),
        )


class FakeClient:
    """Expose the minimal client surface accepted by the provider protocol."""

    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_strict_schema_has_no_optional_top_level_fields() -> None:
    """Keep online output identical to the existing five-field parser contract."""
    schema = answer_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["status"]["enum"] == ["answered", "insufficient_evidence"]


def test_provider_uses_responses_structured_output_without_retries() -> None:
    """Verify request construction with a fake client and no paid API call."""
    config = load_online_config(CONFIG_PATH)
    client = FakeClient()
    generation = OpenAIResponsesGenerator(config, client=client).generate("prompt")
    request = client.responses.calls[0]
    assert request["model"] == "gpt-4o"
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["strict"] is True
    assert generation["usage"] == {
        "prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30
    }


def test_smoke_plan_is_exactly_sixteen_unique_requests() -> None:
    """Protect the approved 8 questions x 2 evidence modes first-stage budget."""
    online = load_online_config(CONFIG_PATH)
    local = load_experiment_config(ROOT / online["local_experiment_config"])
    rows = read_jsonl(ROOT / local["frozen_inputs"]["generation_benchmark"])
    plan = build_plan(
        root=ROOT, online_config=online, local_config=local, rows=rows,
        split_name="smoke", modes=("gold", "retrieved"),
    )
    assert len(plan) == 16
    assert len({item.request_sha256 for item in plan}) == 16
    assert {item.evaluation_mode for item in plan} == {"gold", "retrieved"}
    retry_plan = build_plan(
        root=ROOT, online_config=online, local_config=local, rows=rows,
        split_name="smoke", modes=("gold", "retrieved"),
        question_ids={"GEN-BIO-012", "GEN-PSC-002", "GEN-PSC-015"},
    )
    assert len(retry_plan) == 6


def test_preflight_counts_cache_hits_without_calls(tmp_path: Path) -> None:
    """Ensure an existing response cache removes a request from the paid count."""
    config = load_online_config(CONFIG_PATH)
    plan = [
        PlannedRequest("Q1", "gold", "one", [], "a"),
        PlannedRequest("Q1", "retrieved", "two", [], "b"),
    ]
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    preflight = build_preflight(plan, tmp_path, config)
    assert preflight["planned_requests"] == 2
    assert preflight["cache_hits"] == 1
    assert preflight["new_calls_required"] == 1


def test_env_file_loads_secret_without_overriding_process_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Support a Git-ignored local key while keeping process variables authoritative."""
    env_file = tmp_path / ".env"
    env_file.write_text("# secret\nOPENAI_API_KEY=file-value\n", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert load_env_file(env_file) == ["OPENAI_API_KEY"]
    assert os.environ["OPENAI_API_KEY"] == "file-value"
    monkeypatch.setenv("OPENAI_API_KEY", "process-value")
    assert load_env_file(env_file) == []
    assert os.environ["OPENAI_API_KEY"] == "process-value"


def test_paid_run_rejects_a_non_exact_call_approval(tmp_path: Path) -> None:
    """Fail before client construction when the approved cap differs by one."""
    with pytest.raises(ValueError, match="--approved-new-calls 16"):
        run_experiment(
            root=ROOT,
            config_path=CONFIG_PATH,
            output_dir=tmp_path,
            split_name="smoke",
            modes=("gold", "retrieved"),
            execute_paid=True,
            approved_new_calls=15,
            client=FakeClient(),
        )


def test_blinded_packet_contains_four_answers_and_separate_key() -> None:
    """Keep provider identities out of answer labels while preserving traceability."""
    benchmark = [{
        "question_id": "Q1", "normalized_question": "Question?",
        "required_answer_points": ["required"], "optional_answer_points": [],
        "prohibited_or_unsupported_claims": [],
    }]
    result = {
        "evaluation_mode": "gold", "supplied_evidence": [], "status": "completed",
        "parsed_output": {"answer": "Answer", "citations": []}, "evaluation": {},
    }
    sources = {name: {"Q1": {**result, "evaluation_mode": name.split("_")[-1]}}
               for name in ("local_gold", "local_retrieved", "openai_gold", "openai_retrieved")}
    packet, key = build_review_packet(benchmark, sources)
    assert [answer["label"] for answer in packet[0]["answers"]] == [
        "Answer A", "Answer B", "Answer C", "Answer D"
    ]
    assert set(key["questions"]["Q1"].values()) == set(sources)
    labeled = build_labeled_packet(benchmark, sources)
    assert [answer["label"] for answer in labeled[0]["answers"]] == [
        "Local Qwen — Gold evidence", "GPT-4o API — Gold evidence",
        "Local Qwen — Retrieved evidence", "GPT-4o API — Retrieved evidence",
    ]


def test_provider_incomplete_is_not_counted_as_completed() -> None:
    """Classify output-limit truncation separately from a valid answer row."""
    online = load_online_config(CONFIG_PATH)
    local = load_experiment_config(ROOT / online["local_experiment_config"])
    benchmark = {
        "question_id": "Q1", "normalized_question": "Question?", "book_id": "biology",
        "difficulty": "easy", "requires_formula": False, "requires_visual": False,
        "requires_table": False, "requires_multiple_passages": False,
        "required_answer_points": ["supported"], "prohibited_or_unsupported_claims": [],
    }
    request = PlannedRequest("Q1", "gold", "prompt", [], "hash")
    generation = {
        "raw_text": "", "response_status": "incomplete",
        "usage": {"completion_tokens": online["frozen_configuration"]["max_output_tokens"]},
    }
    result = _result_row(benchmark, request, generation, local, online)
    assert result["status"] == "incomplete"
    assert result["provider_failure"] == "max_output_tokens"
