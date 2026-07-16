"""Validation helpers for the approved answer-generation benchmark v1."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCHMARK = ROOT / "data/benchmarks/generation_benchmark_v1.jsonl"
DEFAULT_SCHEMA = ROOT / "data/benchmarks/schemas/generation_benchmark_v1.schema.json"

BOOK_CHAPTERS = {"biology": set(range(1, 11)),
                 "physical_sciences": set(range(1, 13))}
BOOK_COUNTS = {"biology": 20, "physical_sciences": 20}
SOURCE_FILES = {"biology": "X Biology EM 2025-26.pdf",
                "physical_sciences": "X Physics EM 2025-26.pdf"}
WEBSITE_STATUSES = {"supported", "partially supported", "contradicted",
                    "formatting corrupted"}
QUESTION_TYPES = {
    "cause_effect", "comparison", "experiment_based", "formula_explanation",
    "formula_numerical", "multi_point_explanation", "process_explanation",
    "structure_function", "visual_explanation",
}
DIFFICULTIES = {"easy", "medium", "hard"}
DEPTHS = {"short", "medium", "detailed"}


def read_jsonl(path: Path = DEFAULT_BENCHMARK) -> list[dict[str, Any]]:
    """Read a UTF-8 JSONL file while reporting the failing line precisely."""
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"blank JSONL line at {number}")
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {number}: {exc}") from exc
    return rows


def schema_required_fields(schema_path: Path = DEFAULT_SCHEMA) -> set[str]:
    """Return the versioned schema's required row fields."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return set(schema["required"])


def _strings(row: dict[str, Any], field: str, *, nonempty: bool = False) -> list[str]:
    value = row.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip()
                                          for item in value):
        raise ValueError(f"{row.get('question_id')}: {field} must be an array of non-empty strings")
    if nonempty and not value:
        raise ValueError(f"{row.get('question_id')}: {field} must not be empty")
    return value


def _positive_pages(row: dict[str, Any], field: str) -> list[int]:
    value = row.get(field)
    if not isinstance(value, list) or not value or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in value):
        raise ValueError(f"{row.get('question_id')}: {field} must contain positive integers")
    return value


def validate_row(row: dict[str, Any], required: set[str]) -> None:
    """Validate one row against the stable v1 schema contract."""
    qid = row.get("question_id")
    missing = required - set(row)
    unknown = set(row) - required
    if missing or unknown:
        raise ValueError(f"{qid}: missing={sorted(missing)} unknown={sorted(unknown)}")
    if not isinstance(qid, str) or not re.fullmatch(r"GEN-(BIO|PSC)-\d{3}", qid):
        raise ValueError(f"invalid question_id: {qid!r}")
    book = row["book_id"]
    if book not in BOOK_CHAPTERS:
        raise ValueError(f"{qid}: invalid book_id")
    chapter = row["chapter_number"]
    if isinstance(chapter, bool) or not isinstance(chapter, int) or chapter not in BOOK_CHAPTERS[book]:
        raise ValueError(f"{qid}: invalid chapter_number")
    if row["chapter_id"] != f"{book}-ch{chapter:02d}":
        raise ValueError(f"{qid}: chapter_id does not match book/chapter")
    expected_prefix = "GEN-BIO-" if book == "biology" else "GEN-PSC-"
    if not qid.startswith(expected_prefix):
        raise ValueError(f"{qid}: ID prefix does not match book")
    for field in ("chapter_title", "original_source_question", "normalized_question",
                  "source_question_number", "verification_notes"):
        if not isinstance(row[field], str) or not row[field].strip():
            raise ValueError(f"{qid}: {field} must be a non-empty string")
    if row["source_name"] != "Manabadi" or not re.match(
            r"^https://www\.manabadi\.co\.in/", row["source_url"]):
        raise ValueError(f"{qid}: invalid source provenance")
    if row["question_type"] not in QUESTION_TYPES or row["difficulty"] not in DIFFICULTIES:
        raise ValueError(f"{qid}: invalid type or difficulty")
    _strings(row, "required_answer_points", nonempty=True)
    _strings(row, "optional_answer_points")
    _strings(row, "prohibited_or_unsupported_claims")
    pdf_pages = _positive_pages(row, "accepted_pdf_pages")
    textbook_pages = _positive_pages(row, "accepted_textbook_pages")
    if len(pdf_pages) != len(textbook_pages):
        raise ValueError(f"{qid}: PDF/textbook page lists must align")
    references = row["accepted_evidence_references"]
    if not isinstance(references, list) or len(references) != len(pdf_pages):
        raise ValueError(f"{qid}: evidence references must align with accepted pages")
    expected = [{"book_id": book, "source_file": SOURCE_FILES[book],
                 "pdf_page": pdf, "textbook_page": textbook}
                for pdf, textbook in zip(pdf_pages, textbook_pages)]
    if references != expected:
        raise ValueError(f"{qid}: evidence references differ from accepted pages")
    for field in ("requires_formula", "requires_visual", "requires_table",
                  "requires_multiple_passages"):
        if not isinstance(row[field], bool):
            raise ValueError(f"{qid}: {field} must be boolean")
    if row["expected_answer_depth"] not in DEPTHS:
        raise ValueError(f"{qid}: invalid answer depth")
    if row["website_answer_status"] not in WEBSITE_STATUSES:
        raise ValueError(f"{qid}: invalid website answer status")
    if not isinstance(row["website_answer_notes"], str):
        raise ValueError(f"{qid}: website_answer_notes must be a string")
    if row["reviewer_status"] != "approved" or row["benchmark_version"] != "generation_benchmark_v1":
        raise ValueError(f"{qid}: benchmark approval/version mismatch")
    if row["requires_formula"]:
        formula_context = " ".join([row["normalized_question"],
                                    *row["required_answer_points"],
                                    *row["optional_answer_points"]])
        if not re.search(r"[=∝→₁₂²⁺⁻]|\b(formula|equation|law|electron|hydrogen)\b",
                         formula_context, re.IGNORECASE):
            raise ValueError(f"{qid}: formula dependency lacks formula/law content")


def _canonical_question(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def near_duplicate_pairs(rows: Iterable[dict[str, Any]],
                         threshold: float = 0.86) -> list[tuple[str, str, float]]:
    """Detect exact and high-Jaccard question duplicates deterministically."""
    prepared = [(row["question_id"], _canonical_question(row["normalized_question"]))
                for row in rows]
    duplicates = []
    for index, (left_id, left) in enumerate(prepared):
        for right_id, right in prepared[index + 1:]:
            union = left | right
            score = len(left & right) / len(union) if union else 1.0
            if score >= threshold:
                duplicates.append((left_id, right_id, round(score, 4)))
    return duplicates


def validate_benchmark(rows: list[dict[str, Any]],
                       schema_path: Path = DEFAULT_SCHEMA) -> dict[str, Any]:
    """Validate schema, distributions, provenance, rubrics, and duplicates."""
    required = schema_required_fields(schema_path)
    if len(rows) != 40:
        raise ValueError(f"expected exactly 40 rows, found {len(rows)}")
    for row in rows:
        validate_row(row, required)
    ids = [row["question_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("question IDs are not unique")
    counts = Counter(row["book_id"] for row in rows)
    if counts != Counter(BOOK_COUNTS):
        raise ValueError(f"invalid book distribution: {counts}")
    chapters = {book: {row["chapter_number"] for row in rows if row["book_id"] == book}
                for book in BOOK_CHAPTERS}
    if chapters != BOOK_CHAPTERS:
        raise ValueError(f"invalid chapter coverage: {chapters}")
    biology_counts = Counter(row["chapter_number"] for row in rows
                             if row["book_id"] == "biology")
    if biology_counts != Counter({chapter: 2 for chapter in range(1, 11)}):
        raise ValueError(f"Biology must have exactly two rows per chapter: {biology_counts}")
    duplicates = near_duplicate_pairs(rows)
    if duplicates:
        raise ValueError(f"duplicate or near-duplicate questions: {duplicates}")
    return {"rows": len(rows), "book_counts": dict(counts),
            "chapter_coverage": {book: sorted(values) for book, values in chapters.items()},
            "near_duplicates": duplicates}


def main() -> None:
    """Validate the canonical benchmark from the repository root."""
    print(json.dumps(validate_benchmark(read_jsonl()), indent=2))


if __name__ == "__main__":
    main()
