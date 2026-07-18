"""Regression tests for the resumable local generation experiment harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from textbook_audit.generation_benchmark import read_jsonl
from textbook_audit.generation_experiments import (
    ROOT,
    build_context,
    build_split,
    load_experiment_config,
    parse_output,
    render_prompt,
    resolve_specialist_instruction,
    verify_frozen_inputs,
)
from textbook_audit.generation_experiment_report import classify_failure, pareto_frontier


CONFIG_PATH = ROOT / "config/generation_experiments_v1.json"


@pytest.fixture(scope="module")
def configured_rows() -> tuple[dict, list[dict]]:
    """Load the frozen experiment settings and reviewed benchmark once per module."""
    config = load_experiment_config(CONFIG_PATH)
    rows = read_jsonl(ROOT / config["frozen_inputs"]["generation_benchmark"])
    return config, rows


def test_frozen_hashes_and_split_are_stable(configured_rows: tuple[dict, list[dict]]) -> None:
    """Protect the immutable inputs and exact 8/16/24 question assignment."""
    config, rows = configured_rows
    hashes = verify_frozen_inputs(ROOT, config)
    split = build_split(rows, config)
    assert hashes["generation_benchmark"] == config["frozen_inputs"]["generation_benchmark_sha256"]
    assert split["counts"] == {"smoke": 8, "development": 16, "holdout": 24, "all": 40}
    assert set(split["smoke_question_ids"]) <= set(split["development_question_ids"])


def test_gold_prompt_does_not_leak_rubrics(configured_rows: tuple[dict, list[dict]]) -> None:
    """Ensure prompt construction never exposes answer keys or benchmark labels."""
    _, rows = configured_rows
    row = rows[0]
    items = build_context(row, "gold_separate_full", ROOT)
    prompt = render_prompt(row, items, "P0", "gold_separate_full")
    assert row["normalized_question"] in prompt
    assert row["required_answer_points"][0] not in prompt
    assert "required_answer_points" not in prompt
    assert "difficulty" not in prompt


def test_standard_output_parser_validates_pages() -> None:
    """Accept supplied page citations and reject fabricated page metadata."""
    items = [{"evidence_id": "E1", "pdf_page": 12, "textbook_page": 3,
              "pdf_pages": [12], "textbook_pages": [3], "text": "Evidence."}]
    valid = {
        "status": "answered", "answer": "Supported answer.",
        "selected_evidence_ids": ["E1"],
        "citations": [{"evidence_id": "E1", "pdf_page": 12, "textbook_page": 3}],
        "missing_information": [],
    }
    assert parse_output(json.dumps(valid), items)["valid"]
    valid["citations"][0]["pdf_page"] = 99
    parsed = parse_output(json.dumps(valid), items)
    assert not parsed["valid"]
    assert any("page metadata" in error for error in parsed["errors"])


def test_parser_rejects_extra_fields() -> None:
    """Keep the machine-readable answer contract deterministic across models."""
    raw = json.dumps({
        "status": "answered", "answer": "A", "selected_evidence_ids": [],
        "citations": [], "missing_information": [], "reasoning": "hidden",
    })
    parsed = parse_output(raw, [])
    assert not parsed["valid"]
    assert "exactly the five required keys" in parsed["errors"][0]


def test_failure_attribution_distinguishes_missing_retrieval() -> None:
    """Attribute a miss to retrieval when no accepted page reached generation."""
    result = {
        "supplied_evidence": [{"pdf_pages": [99]}],
        "evaluation": {
            "false_insufficient_evidence": False, "citation_validity": 1.0,
            "unsupported_claims": [], "required_point_coverage": 0.0,
        },
    }
    benchmark = {
        "accepted_pdf_pages": [12], "requires_visual": False,
        "requires_formula": False, "requires_multiple_passages": False,
    }
    assert classify_failure(result, benchmark) == "evidence absent from retrieved context"


def test_pareto_frontier_removes_strictly_dominated_run() -> None:
    """Keep quality/latency trade-offs while removing a worse run on every axis."""
    good = {"run_id": "good", "metrics": {"required_point_coverage": 0.8,
            "citation_validity": 1.0, "unsupported_claim_rate": 0.0,
            "p95_latency_seconds": 10.0}}
    weak = {"run_id": "weak", "metrics": {"required_point_coverage": 0.7,
            "citation_validity": 0.9, "unsupported_claim_rate": 0.1,
            "p95_latency_seconds": 12.0}}
    assert [row["run_id"] for row in pareto_frontier([good, weak])] == ["good"]


def test_multi_part_specialist_activation_uses_query_not_gold() -> None:
    """Activate subtopic organization from wording without dependency labels."""
    row = {"normalized_question": "What is double circulation and why is it important?",
           "book_id": "biology"}
    instruction = resolve_specialist_instruction(
        row, "gold_separate_full", "ACTIVATE_SPECIALISTS", ROOT
    )
    assert "explicit subtopic" in instruction
