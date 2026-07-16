"""Promote the approved review proposal into Generation Benchmark v1."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from textbook_audit.generation_benchmark import SOURCE_FILES, validate_benchmark


PROPOSAL = ROOT / "reports/generation_benchmark_v1_review/proposed_40_questions.jsonl"
OUTPUT = ROOT / "data/benchmarks/generation_benchmark_v1.jsonl"

OUTPUT_FIELDS = [
    "question_id", "book_id", "chapter_id", "chapter_number", "chapter_title",
    "original_source_question", "normalized_question", "source_name", "source_url",
    "source_question_number", "question_type", "difficulty", "required_answer_points",
    "optional_answer_points", "prohibited_or_unsupported_claims", "accepted_pdf_pages",
    "accepted_textbook_pages", "accepted_evidence_references", "requires_formula",
    "requires_visual", "requires_table", "requires_multiple_passages",
    "expected_answer_depth", "website_answer_status", "website_answer_notes",
    "verification_notes", "reviewer_status", "benchmark_version",
]


def read_proposal() -> list[dict]:
    """Read and enforce the exact approved proposal shape."""
    rows = [json.loads(line) for line in PROPOSAL.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 40 or any(row.get("recommendation") == "reject" for row in rows):
        raise ValueError("proposal must contain exactly 40 non-rejected questions")
    return rows


def promote(row: dict) -> dict:
    """Remove review-only fields and add stable evidence/approval metadata."""
    book = row["book_id"]
    references = [
        {"book_id": book, "source_file": SOURCE_FILES[book],
         "pdf_page": pdf_page, "textbook_page": textbook_page}
        for pdf_page, textbook_page in zip(
            row["accepted_pdf_pages"], row["accepted_textbook_pages"])
    ]
    verification = (
        "Verified against the original textbook PDF text layer and the cited printed pages. "
        "Formula, table, experiment, and diagram-dependent evidence was also checked on rendered PDF pages."
    )
    if row["question_id"] in {"GEN-PSC-013", "GEN-PSC-014", "GEN-PSC-015",
                              "GEN-PSC-016", "GEN-PSC-017", "GEN-PSC-018",
                              "GEN-PSC-019", "GEN-PSC-020"}:
        verification += (
            " Printed textbook page labels are used because the processed Physical Sciences "
            "metadata has a five-page drift in the later chapters."
        )
    promoted = {
        key: row[key] for key in OUTPUT_FIELDS
        if key not in {"accepted_evidence_references", "verification_notes",
                       "reviewer_status", "benchmark_version"}
    }
    promoted.update({
        "accepted_evidence_references": references,
        "verification_notes": verification,
        "reviewer_status": "approved",
        "benchmark_version": "generation_benchmark_v1",
    })
    return {field: promoted[field] for field in OUTPUT_FIELDS}


def main() -> None:
    """Write deterministic JSONL only after complete in-memory validation."""
    rows = [promote(row) for row in read_proposal()]
    rows.sort(key=lambda row: row["question_id"])
    result = validate_benchmark(rows)
    serialized = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
                         for row in rows)
    OUTPUT.write_text(serialized, encoding="utf-8", newline="\n")
    parsed = [json.loads(line) for line in OUTPUT.read_text(encoding="utf-8").splitlines()]
    if parsed != rows:
        raise AssertionError("serialized benchmark does not round-trip deterministically")
    print(json.dumps({**result, "output": str(OUTPUT)}, indent=2))


if __name__ == "__main__":
    main()
