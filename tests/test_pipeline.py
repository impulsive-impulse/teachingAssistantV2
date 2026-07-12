"""Fast structural checks for configuration and committed artifacts."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.benchmark import FIELDS, build_rows, validate
from textbook_audit.config import SPECS
from textbook_audit.pipeline import chapter_for, textbook_page_for


EXPECTED_PAGE_COUNTS = {"biology": 257, "physical_sciences": 327}
REQUIRED_FIELDS = {
    "book_id", "source_file", "pdf_page_number", "textbook_page_number",
    "chapter_number", "chapter_title", "section_title", "raw_text",
    "cleaned_text", "text_length", "has_image", "has_table",
    "has_equation_like_text", "extraction_notes",
}


class PipelineTests(unittest.TestCase):
    def test_page_and_chapter_mapping_boundaries(self) -> None:
        for spec in SPECS:
            self.assertEqual(textbook_page_for(spec, spec.content_pdf_offset + 1), 1)
            for number, title, printed_start in spec.chapters:
                self.assertEqual(chapter_for(spec, printed_start), (number, title))

    def test_committed_page_artifacts(self) -> None:
        for spec in SPECS:
            path = ROOT / "data" / "processed" / f"{spec.book_id}_pages.jsonl"
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), EXPECTED_PAGE_COUNTS[spec.book_id])
            self.assertTrue(all(set(row) == REQUIRED_FIELDS for row in rows))
            self.assertTrue(all(row["pdf_page_number"] == index for index, row in enumerate(rows, 1)))
            self.assertTrue(all(row["text_length"] == len(row["cleaned_text"]) for row in rows))

    def test_committed_chapter_maps(self) -> None:
        for spec in SPECS:
            path = ROOT / "data" / "processed" / f"{spec.book_id}_chapter_map.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(value["book_id"], spec.book_id)
            self.assertEqual(len(value["chapters"]), len(spec.chapters))

    def test_retrieval_benchmark_candidates(self) -> None:
        rows = build_rows(ROOT)
        self.assertEqual(len(rows), 40)
        self.assertEqual(sum(r["book_id"] == "biology" for r in rows), 20)
        self.assertEqual(sum(r["book_id"] == "physical_sciences" for r in rows), 20)
        self.assertEqual(len({r["question_id"] for r in rows}), 40)
        self.assertTrue(all(list(r) == FIELDS for r in rows))
        self.assertEqual(validate(rows, ROOT), [])


if __name__ == "__main__":
    unittest.main()
