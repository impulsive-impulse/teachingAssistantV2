"""Regression coverage for the resumable Phase A generation smoke gate."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from textbook_audit.generation_benchmark import read_jsonl
from textbook_audit.generation_phase_a import (
    DEFAULT_CONFIG,
    LlamaServerConfig,
    LocalLlamaServer,
    add_manual_review_metrics,
    build_benchmark_split,
    build_gold_context,
    evaluate_rubric,
    load_config,
    load_manual_reviews,
    load_or_initialize_state,
    render_generation_prompt,
    sha256_file,
    summarize_smoke,
    validate_structured_answer,
)


ROOT = Path(__file__).resolve().parents[1]
GENERATION_BENCHMARK = ROOT / "data/benchmarks/generation_benchmark_v1.jsonl"
RETRIEVAL_BENCHMARK = ROOT / "data/benchmarks/retrieval_benchmark_v1.jsonl"
GENERATION_SHA256 = "f756e6333909c72f0e0be82b7bc16c9756f158fb39e16d463442e2bed5266680"
RETRIEVAL_SHA256 = "d333768b9c645cf0048a38356bfea69aa4a9e7220010e2cdf6340b91af38c046"


@pytest.fixture(scope="module")
def config() -> dict:
    """Load the reviewed Phase A configuration once for focused tests."""
    return load_config(DEFAULT_CONFIG)


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    """Load canonical generation rows without modifying the benchmark."""
    return read_jsonl(GENERATION_BENCHMARK)


def test_frozen_benchmark_hashes_are_unchanged() -> None:
    """Protect both user-named immutable benchmark artifacts."""
    assert sha256_file(GENERATION_BENCHMARK) == GENERATION_SHA256
    assert sha256_file(RETRIEVAL_BENCHMARK) == RETRIEVAL_SHA256


def test_split_is_balanced_and_keeps_32_rows_held_out(rows: list[dict], config: dict) -> None:
    """Verify the fixed smoke gate and held-out separation contract."""
    split = build_benchmark_split(rows, config, GENERATION_BENCHMARK)
    assert split["counts"] == {"development": 8, "held_out": 32}
    assert split["smoke_question_ids"] == config["split"]["development_question_ids"]
    assert split["smoke_distribution"] == {
        "books": {"biology": 4, "physical_sciences": 4},
        "difficulty": {"easy": 2, "medium": 3, "hard": 3},
        "formula": 3,
        "visual": 1,
        "table": 1,
        "multiple_passages": 2,
    }
    assert not (set(split["smoke_question_ids"]) & set(split["held_out_question_ids"]))


def test_gold_context_uses_exact_accepted_pdf_pages(rows: list[dict]) -> None:
    """Ensure PDF extraction preserves benchmark page and citation metadata."""
    row = next(item for item in rows if item["question_id"] == "GEN-BIO-002")
    context = build_gold_context(row, ROOT / "books")
    assert [item["pdf_page"] for item in context["evidence"]] == row["accepted_pdf_pages"]
    assert [item["textbook_page"] for item in context["evidence"]] == row["accepted_textbook_pages"]
    assert [item["evidence_id"] for item in context["evidence"]] == ["E1", "E2"]
    assert all(item["text"] and len(item["text_sha256"]) == 64 for item in context["evidence"])


def test_prompt_contains_question_and_evidence_but_not_rubric(rows: list[dict]) -> None:
    """Prevent answer-rubric leakage into the generation prompt."""
    row = next(item for item in rows if item["question_id"] == "GEN-BIO-002")
    context = build_gold_context(row, ROOT / "books")
    prompt = render_generation_prompt(row, context)
    assert row["normalized_question"] in prompt
    assert context["evidence"][0]["text"] in prompt
    assert "required_answer_points" not in prompt
    assert "prohibited_or_unsupported_claims" not in prompt
    assert "Every claim must cite" in prompt


def test_structured_answer_and_citations_validate() -> None:
    """Accept claim-level citations and reject unknown evidence IDs."""
    raw = json.dumps({"claims": [
        {"text": "Bile emulsifies fat.", "citations": ["E1"]},
        {"text": "Lipase forms fatty acids and glycerol.", "citations": ["E1", "E2"]},
    ]})
    valid = validate_structured_answer(raw, {"E1", "E2"})
    assert valid["valid"] is True
    assert valid["structure_valid"] is True
    assert valid["cited_evidence_ids"] == ["E1", "E2"]

    unknown = validate_structured_answer(
        '{"claims":[{"text":"Unsupported source.","citations":["E9"]}]}', {"E1"}
    )
    assert unknown["valid"] is False
    assert "unknown citations" in unknown["errors"][0]

    supported = validate_structured_answer(
        raw, {"E1", "E2"},
        {"E1": "Bile emulsifies fat and lipase digests fats.",
         "E2": "Fat digestion produces fatty acids and glycerol."},
    )
    assert supported["valid"] is True
    assert all(item["supported"] for item in supported["citation_support"])

    unsupported = validate_structured_answer(
        '{"claims":[{"text":"Saturn has icy rings.","citations":["E1"]}]}',
        {"E1"}, {"E1": "Bile emulsifies fat in the small intestine."},
    )
    assert unsupported["valid"] is False
    assert unsupported["structure_valid"] is True
    assert unsupported["citation_support"][0]["supported"] is False


def test_rubric_evaluation_scores_explicit_answer(rows: list[dict], config: dict) -> None:
    """Confirm deterministic rubric scoring covers every required fat-digestion point."""
    row = next(item for item in rows if item["question_id"] == "GEN-BIO-002")
    structured = validate_structured_answer(json.dumps({"claims": [
        {"text": "Bile emulsifies fats into small globules in the small intestine.",
         "citations": ["E1"]},
        {"text": "Pancreatic lipase acts on fats, and digestion is completed in the small "
                 "intestine; the end products include fatty acids and glycerol.",
         "citations": ["E1", "E2"]},
    ]}), {"E1", "E2"})
    evaluation = evaluate_rubric(row, structured, config["evaluation"])
    assert evaluation["required_coverage"] == 1.0
    assert evaluation["asserted_unsupported_claims"] == []
    assert evaluation["automatic_pass"] is True


def test_state_resume_rejects_changed_model(tmp_path: Path, config: dict, rows: list[dict]) -> None:
    """Ensure resume cannot mix results from different model bytes."""
    split = build_benchmark_split(rows, config, GENERATION_BENCHMARK)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    model_path = tmp_path / "model.gguf"
    model_path.write_bytes(b"approved-model-placeholder")
    state_path = tmp_path / "state.json"
    command = ["llama-server.exe", "--model", str(model_path)]
    state = load_or_initialize_state(
        state_path, split, config, config_path, model_path, command
    )
    assert state["status"] == "initialized"
    model_path.write_bytes(b"changed-model-placeholder")
    with pytest.raises(ValueError, match="model_sha256"):
        load_or_initialize_state(state_path, split, config, config_path, model_path, command)


def test_llama_server_command_freezes_runtime_settings(tmp_path: Path, config: dict) -> None:
    """Check that the interface applies the approved CPU and batching parameters."""
    resolved = LlamaServerConfig(
        executable=tmp_path / "llama-server.exe",
        model=tmp_path / "model.gguf",
        port=18090,
        runtime=config["runtime"],
        generation=config["generation"],
        log_dir=tmp_path / "logs",
    )
    command = LocalLlamaServer(resolved).command()
    assert command[command.index("--ctx-size") + 1] == "8192"
    assert command[command.index("--threads") + 1] == "10"
    assert command[command.index("--n-gpu-layers") + 1] == "0"
    assert command[command.index("--seed") + 1] == "42"


def test_llama_server_context_uses_runtime_startup_timeout(
    tmp_path: Path, config: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = dict(config["runtime"])
    runtime["startup_timeout_seconds"] = 600
    resolved = LlamaServerConfig(
        executable=tmp_path / "llama-server.exe",
        model=tmp_path / "model.gguf",
        port=18090,
        runtime=runtime,
        generation=config["generation"],
        log_dir=tmp_path / "logs",
    )
    server = LocalLlamaServer(resolved)
    observed: list[float] = []
    monkeypatch.setattr(
        server, "start", lambda timeout_seconds: observed.append(timeout_seconds)
    )
    with server:
        pass
    assert observed == [600.0]


def test_smoke_summary_counts_completed_outputs() -> None:
    """Aggregate only completed rows and keep manual review as a hard gate."""
    template = {
        "status": "completed",
        "citation_validation": {
            "valid": True, "structure_valid": True, "citation_support_valid": True,
        },
        "rubric_evaluation": {"automatic_pass": True, "required_coverage": 1.0,
                              "rubric_score": 1.0},
        "generation": {"latency_seconds": 2.0},
    }
    metrics = summarize_smoke([copy.deepcopy(template) for _ in range(8)], 8)
    assert metrics["completed_questions"] == 8
    assert metrics["structured_output_valid"] == 8
    assert metrics["lexical_citation_support_valid"] == 8
    assert metrics["manual_review_required"] is True
    assert metrics["prompt_comparisons_started"] is False


def test_committed_manual_review_covers_the_exact_smoke_slice(rows: list[dict], config: dict) -> None:
    """Validate the reviewed answer/citation judgments and their aggregate counts."""
    split = build_benchmark_split(rows, config, GENERATION_BENCHMARK)
    reviews = load_manual_reviews(
        ROOT / "reports/generation_phase_a_v1", split["smoke_question_ids"], required=True
    )
    metrics = add_manual_review_metrics({}, reviews)["manual_review"]
    assert metrics == {
        "reviewed_questions": 8,
        "strict_gate_passes": 2,
        "mean_strict_required_coverage": 0.6937,
        "fully_supported_citations": 5,
        "partially_supported_citations": 3,
        "unsupported_citations": 0,
        "unsupported_claims_found": 0,
    }
