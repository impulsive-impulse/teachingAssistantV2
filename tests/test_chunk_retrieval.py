"""Regression tests for chunk construction, metadata, gold matching, and metrics."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.chunk_retrieval import (answer_span_coverage,
                                             derive_gold_chunks, fixed_chunks,
                                             structured_chunks)
from textbook_audit.retrieval import metric_block


def page(number: int, chapter: int, section: str, text: str) -> dict:
    """Create a minimal realistic page record for isolated chunk tests."""
    return {"book_id": "biology", "pdf_page_number": number,
            "textbook_page_number": number - 9, "chapter_number": chapter,
            "chapter_title": f"Chapter {chapter}", "section_title": section,
            "cleaned_text": text, "has_image": number % 2 == 0,
            "has_table": False, "has_equation_like_text": False}


class ChunkRetrievalTests(unittest.TestCase):
    """Protect chunk boundary, lineage, mapping, and evaluation invariants."""

    def test_fixed_chunks_never_cross_chapters_and_link_deterministically(self) -> None:
        """Ensure fixed overlap cannot mix chapters and navigation IDs are stable."""
        pages = [page(10, 1, "A", " ".join(f"alpha{i}." for i in range(30))),
                 page(11, 2, "B", " ".join(f"beta{i}." for i in range(30)))]
        chunks = fixed_chunks(pages, target=15, overlap=4)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(not ({10, 11} <= set(c["pdf_pages"])) for c in chunks))
        self.assertEqual(chunks[0]["chunk_id"], "biology:fixed:00000")
        self.assertIsNone(chunks[0]["previous_chunk_id"])
        self.assertEqual(chunks[0]["next_chunk_id"], chunks[1]["chunk_id"])

    def test_metadata_aggregates_every_contributing_page(self) -> None:
        """Preserve all source pages and OR page-level visual indicators."""
        pages = [page(10, 1, "A", "one two three four."),
                 page(11, 1, "A", "five six seven eight.")]
        chunks = structured_chunks(pages, minimum=2, maximum=20)
        self.assertEqual(chunks[0]["pdf_pages"], [10, 11])
        self.assertEqual(chunks[0]["textbook_pages"], [1, 2])
        self.assertTrue(chunks[0]["has_visual"])

    def test_structured_chunks_do_not_mix_sections(self) -> None:
        """Treat headings as semantic boundaries when sections are independently large."""
        pages = [page(10, 1, "A", " ".join("alpha" for _ in range(12))),
                 page(11, 1, "B", " ".join("beta" for _ in range(12)))]
        chunks = structured_chunks(pages, minimum=5, maximum=15)
        self.assertEqual([c["section_title"] for c in chunks], ["A", "B"])

    def test_answer_span_coverage_requires_contiguous_evidence(self) -> None:
        """Reject chunks containing scattered gold words but accept an exact span."""
        span = "cells release energy by breaking chemical bonds"
        self.assertEqual(answer_span_coverage(span, span), 1.0)
        self.assertLess(answer_span_coverage(span, "cells unrelated release unrelated energy"), 0.5)

    def test_gold_mapping_uses_page_and_answer_span(self) -> None:
        """A chunk from a gold page counts only when it includes answer-bearing text."""
        chunks = [{"chunk_id": "wrong", "pdf_pages": [10], "text": "unrelated introduction"},
                  {"chunk_id": "right", "pdf_pages": [10], "text": "cells release energy by breaking chemical bonds"},
                  {"chunk_id": "off-page", "pdf_pages": [11], "text": "cells release energy by breaking chemical bonds"}]
        q = {"gold_pdf_pages": [10], "gold_answer_span": "cells release energy by breaking chemical bonds"}
        mapping = derive_gold_chunks(q, chunks)
        self.assertEqual(mapping["status"], "mapped")
        self.assertEqual(mapping["primary"], ["right"])

    def test_uncertain_mapping_is_not_silently_scored(self) -> None:
        """Flag low-overlap answer spans for review rather than inventing a gold chunk."""
        q = {"gold_pdf_pages": [10], "gold_answer_span": "a complete verified answer phrase"}
        mapping = derive_gold_chunks(q, [{"chunk_id": "c", "pdf_pages": [10], "text": "a fragment"}])
        self.assertEqual(mapping["status"], "manual_review")
        self.assertEqual(mapping["primary"], [])

    def test_chunk_metrics_exclude_uncertain_and_negative_rows(self) -> None:
        """Only confidently mapped answerable questions affect retrieval effectiveness."""
        metrics = metric_block([{"answerable": True, "first_relevant_rank": 2, "latency_ms": 1.0},
                                {"answerable": False, "first_relevant_rank": None, "latency_ms": 2.0}])
        self.assertEqual(metrics["answerable_questions"], 1)
        self.assertEqual(metrics["hit_at_1"], 0.0)
        self.assertEqual(metrics["hit_at_3"], 1.0)


if __name__ == "__main__":
    unittest.main()
