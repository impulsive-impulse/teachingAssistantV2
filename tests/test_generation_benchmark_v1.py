"""Contract tests for the approved Generation Benchmark v1."""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from pypdf import PdfReader

from textbook_audit.baseline_freeze import verify_manifest
from textbook_audit.generation_benchmark import (
    DEFAULT_BENCHMARK,
    DEFAULT_SCHEMA,
    SOURCE_FILES,
    near_duplicate_pairs,
    read_jsonl,
    schema_required_fields,
    validate_benchmark,
    validate_row,
)


ROOT = Path(__file__).resolve().parents[1]
RETRIEVAL_BENCHMARK = ROOT / "data/benchmarks/retrieval_benchmark_v1.jsonl"
BASELINE_CONFIG = ROOT / "config/retrieval_baseline_v1.yaml"
BASELINE_MANIFEST = ROOT / "reports/retrieval_baseline_v1/manifest.json"
FROZEN_RETRIEVAL_BENCHMARK_SHA256 = "d333768b9c645cf0048a38356bfea69aa4a9e7220010e2cdf6340b91af38c046"
FROZEN_BASELINE_CONFIG_SHA256 = "736fb9325794caead4439316b6ca546bd782cd7029b4f9f7788f545c5b43baa6"


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return read_jsonl(DEFAULT_BENCHMARK)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_schema_and_complete_benchmark_validate(rows: list[dict]) -> None:
    result = validate_benchmark(rows, DEFAULT_SCHEMA)
    assert result["rows"] == 40
    assert result["near_duplicates"] == []


def test_jsonl_is_canonical_and_deterministic(rows: list[dict]) -> None:
    lines = DEFAULT_BENCHMARK.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 40
    assert lines == [json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                     for row in rows]
    assert [row["question_id"] for row in rows] == sorted(
        row["question_id"] for row in rows)


def test_book_and_chapter_distribution(rows: list[dict]) -> None:
    assert Counter(row["book_id"] for row in rows) == {
        "biology": 20, "physical_sciences": 20}
    assert Counter(row["chapter_number"] for row in rows
                   if row["book_id"] == "biology") == {
        chapter: 2 for chapter in range(1, 11)}
    assert {row["chapter_number"] for row in rows
            if row["book_id"] == "physical_sciences"} == set(range(1, 13))


def test_unique_ids_and_duplicate_detection(rows: list[dict]) -> None:
    assert len({row["question_id"] for row in rows}) == 40
    assert near_duplicate_pairs(rows) == []
    duplicate = copy.deepcopy(rows[0])
    duplicate["question_id"] = "GEN-BIO-999"
    assert near_duplicate_pairs([rows[0], duplicate]) == [
        (rows[0]["question_id"], "GEN-BIO-999", 1.0)]


def test_source_provenance_is_complete(rows: list[dict]) -> None:
    for row in rows:
        assert row["source_name"] == "Manabadi"
        assert row["source_url"].startswith("https://www.manabadi.co.in/")
        assert row["source_question_number"]
        assert row["original_source_question"]
        assert row["normalized_question"]


def test_textbook_evidence_and_pages_are_valid(rows: list[dict]) -> None:
    readers = {book: PdfReader(ROOT / "books" / filename)
               for book, filename in SOURCE_FILES.items()}
    for row in rows:
        assert row["accepted_pdf_pages"]
        assert row["accepted_textbook_pages"]
        assert len(row["accepted_evidence_references"]) == len(row["accepted_pdf_pages"])
        for reference in row["accepted_evidence_references"]:
            assert reference["book_id"] == row["book_id"]
            assert reference["source_file"] == SOURCE_FILES[row["book_id"]]
            assert 1 <= reference["pdf_page"] <= len(readers[row["book_id"]].pages)
            assert reference["textbook_page"] >= 1


def test_answer_rubrics_are_complete(rows: list[dict]) -> None:
    for row in rows:
        assert all(point.strip() for point in row["required_answer_points"])
        assert row["prohibited_or_unsupported_claims"]
        assert row["expected_answer_depth"] in {"short", "medium", "detailed"}
        assert row["reviewer_status"] == "approved"
        assert row["benchmark_version"] == "generation_benchmark_v1"


def test_formula_fields_and_notation_validate(rows: list[dict]) -> None:
    formula_rows = [row for row in rows if row["requires_formula"]]
    assert len(formula_rows) == 10
    mirror = next(row for row in rows if row["question_id"] == "GEN-PSC-002")
    assert any("v = -20/3 cm" in point for point in mirror["required_answer_points"])
    lens = next(row for row in rows if row["question_id"] == "GEN-PSC-008")
    assert any("1/R₁ − 1/R₂" in point for point in lens["required_answer_points"])
    broken = copy.deepcopy(lens)
    broken["normalized_question"] = "Explain the concept."
    broken["required_answer_points"] = ["Give the explanation."]
    broken["optional_answer_points"] = []
    with pytest.raises(ValueError, match="formula dependency"):
        validate_row(broken, schema_required_fields())


def test_schema_rejects_missing_and_unknown_fields(rows: list[dict]) -> None:
    required = schema_required_fields()
    missing = copy.deepcopy(rows[0])
    del missing["source_url"]
    with pytest.raises(ValueError, match="missing"):
        validate_row(missing, required)
    unknown = copy.deepcopy(rows[0])
    unknown["website_answer"] = "not permitted in the final benchmark"
    with pytest.raises(ValueError, match="unknown"):
        validate_row(unknown, required)


def test_existing_retrieval_assets_remain_immutable() -> None:
    assert sha256(RETRIEVAL_BENCHMARK) == FROZEN_RETRIEVAL_BENCHMARK_SHA256
    assert sha256(BASELINE_CONFIG) == FROZEN_BASELINE_CONFIG_SHA256
    assert verify_manifest(ROOT, BASELINE_MANIFEST)["mismatches"] == []
