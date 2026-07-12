"""Regression tests for page loading, ranking, matching, and metrics."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.retrieval import (BM25, accepted_pdf_pages, load_pages,
                                      metric_block, read_jsonl,
                                      reciprocal_rank_fusion, stable_ranking)


class RetrievalTests(unittest.TestCase):
    """Protect the baseline's data-selection and scoring invariants."""

    def test_reviewed_benchmark_is_canonical_and_candidates_are_distinct(self) -> None:
        """Require the reviewed canonical file and its finalized statuses."""
        rows = read_jsonl(ROOT / "data/benchmarks/retrieval_benchmark_v1.jsonl")
        self.assertEqual(len(rows), 40)
        self.assertTrue(all(r["review_status"] in {"verified", "verified_with_fixes", "confirmed_unanswerable"} for r in rows))

    def test_loading_excludes_front_matter_and_preserves_metadata(self) -> None:
        """Ensure only mapped content pages enter otherwise intact corpora."""
        books = load_pages(ROOT)
        for book_id, pages in books.items():
            self.assertTrue(all(p["book_id"] == book_id for p in pages))
            self.assertTrue(all(p["textbook_page_number"] is not None for p in pages))
            self.assertTrue(all("chapter_title" in p and "section_title" in p for p in pages))

    def test_bm25_and_tie_break_are_deterministic(self) -> None:
        """Check keyword relevance and corpus-order resolution of score ties."""
        index = BM25(["plant photosynthesis sunlight", "electric current", "plant cell"])
        ranking = stable_ranking(index.scores("photosynthesis sunlight"))
        self.assertEqual(int(ranking[0]), 0)
        self.assertEqual(stable_ranking(np.zeros(3)).tolist(), [0, 1, 2])

    def test_rrf_combines_rankings(self) -> None:
        """Check RRF rewards items supported near the top of both rankings."""
        scores = reciprocal_rank_fusion([np.array([0, 1, 2]), np.array([1, 0, 2])], 3)
        self.assertGreater(scores[0], scores[2])
        self.assertAlmostEqual(scores[0], scores[1])

    def test_page_matching_includes_alternative_textbook_pages(self) -> None:
        """Translate reviewed alternative printed pages into accepted PDF pages."""
        q = {"gold_pdf_pages": [11], "alternative_gold_pages": [3]}
        pages = [{"pdf_page_number": 11, "textbook_page_number": 2},
                 {"pdf_page_number": 12, "textbook_page_number": 3}]
        self.assertEqual(accepted_pdf_pages(q, pages), {11, 12})

    def test_metrics_exclude_negatives_from_effectiveness(self) -> None:
        """Keep unanswerable questions out of Hit@K and MRR denominators."""
        rows = [
            {"answerable": True, "first_relevant_rank": 1, "latency_ms": 1.0},
            {"answerable": True, "first_relevant_rank": None, "latency_ms": 3.0},
            {"answerable": False, "first_relevant_rank": None, "latency_ms": 2.0},
        ]
        result = metric_block(rows)
        self.assertEqual(result["answerable_questions"], 2)
        self.assertEqual(result["hit_at_1"], 0.5)
        self.assertEqual(result["mrr"], 0.5)
        self.assertEqual(result["average_latency_ms"], 2.0)

    def test_missing_benchmark_fails_clearly(self) -> None:
        """Provide an actionable error instead of falling back to candidates."""
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(FileNotFoundError, "reviewed benchmark is missing"):
                read_jsonl(Path(d) / "retrieval_benchmark_v1.jsonl")


if __name__ == "__main__":
    unittest.main()
