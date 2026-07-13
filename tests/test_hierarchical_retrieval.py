"""Regression tests for hierarchy detection, aggregation, retrieval, and scoring."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.hierarchical_retrieval import (aggregate_normalized,
    build_nodes, derive_gold, detect_heading, load_chapter_content,
    reconstruct_page_blocks, soft_fusion, strict_cascade)
from textbook_audit.retrieval import metric_block


class HierarchicalRetrievalTests(unittest.TestCase):
    """Protect structural and ranking invariants of hierarchical retrieval."""

    def test_chapter_assignment_uses_verified_ranges(self) -> None:
        """Exclude front matter and assign first content page from the chapter map."""
        chapters, pages = load_chapter_content(ROOT, "biology")
        self.assertEqual(chapters[0]["detected_pdf_page_start"], 10)
        self.assertEqual(pages[0]["pdf_page_number"], 10)
        self.assertEqual(pages[0]["chapter_title"], "Nutrition")

    def test_heading_detection_is_conservative(self) -> None:
        """Accept numbered headings and matched titles but reject questions and labels."""
        self.assertEqual(detect_heading("3.4.1 Structure of nephron")[1], "high")
        self.assertEqual(detect_heading("Cellular Respiration", "Cellular Respiration")[1], "medium")
        self.assertIsNone(detect_heading("What happens to glucose?"))
        self.assertIsNone(detect_heading("P C"))

    def test_paragraph_reconstruction_rejoins_wrapped_lines(self) -> None:
        """Join PDF line wraps while retaining explicit heading boundaries."""
        page = {"cleaned_text": "1.2 Photosynthesis\nPlants prepare food using\nsunlight and chlorophyll.",
                "section_title": "1.2 Photosynthesis", "has_table": False,
                "has_equation_like_text": False}
        blocks = reconstruct_page_blocks(page)
        self.assertEqual(blocks[0]["block_type"], "heading")
        self.assertIn("using sunlight", blocks[1]["text"])

    def test_parent_child_links_are_complete(self) -> None:
        """Build section and chapter nodes containing every supplied leaf ID."""
        leaves = [{"chunk_id": "p1", "section_id": "s1", "chapter_id": "c1", "chapter_title": "C",
                   "section_title": "S", "heading_confidence": "high", "text": "one"},
                  {"chunk_id": "p2", "section_id": "s1", "chapter_id": "c1", "chapter_title": "C",
                   "section_title": "S", "heading_confidence": "high", "text": "two"}]
        sections, chapters = build_nodes(leaves)
        self.assertEqual(sections[0]["child_ids"], ["p1", "p2"])
        self.assertEqual(chapters[0]["section_ids"], ["s1"])

    def test_aggregation_returns_normalized_mean(self) -> None:
        """Parent aggregation must average children and restore unit length."""
        result = aggregate_normalized(np.asarray([[1., 0.], [0., 1.]]))
        self.assertAlmostEqual(float(np.linalg.norm(result)), 1.0, places=6)
        self.assertAlmostEqual(float(result[0]), float(result[1]))

    def test_strict_cascade_filters_by_selected_parents(self) -> None:
        """Only leaves under selected chapter and section survive the cascade."""
        levels = {"chapters": [{"id": "c1"}, {"id": "c2"}],
                  "sections": [{"id": "s1", "chapter_id": "c1"}, {"id": "s2", "chapter_id": "c2"}],
                  "paragraphs": [{"section_id": "s1"}, {"section_id": "s2"}]}
        rank, stage = strict_cascade(levels, {"chapters": np.array([2., 1.]),
                                              "sections": np.array([2., 3.]),
                                              "paragraphs": np.array([1., 9.])}, 1, 1)
        self.assertEqual(rank.tolist(), [0])
        self.assertEqual(stage["selected_section_ids"], ["s1"])

    def test_soft_fusion_keeps_all_paragraphs_eligible(self) -> None:
        """Parent rank signals change scores without removing any leaf."""
        levels = {"chapters": [{"id": "c1"}], "sections": [{"id": "s1", "chapter_id": "c1"}],
                  "paragraphs": [{"section_id": "s1"}, {"section_id": "s1"}]}
        rank, scores = soft_fusion(levels, {"chapters": np.array([1.]), "sections": np.array([1.]),
                                             "paragraphs": np.array([1., 2.])})
        self.assertEqual(set(rank.tolist()), {0, 1})
        self.assertGreater(scores[1], scores[0])

    def test_gold_matching_requires_page_and_span(self) -> None:
        """Derive leaf and parent gold only from answer-bearing text on a gold page."""
        leaves = [{"chunk_id": "p1", "section_id": "s1", "chapter_id": "c1", "pdf_pages": [10], "text": "unrelated"},
                  {"chunk_id": "p2", "section_id": "s2", "chapter_id": "c1", "pdf_pages": [10], "text": "cells release stored chemical energy"}]
        gold = derive_gold({"gold_pdf_pages": [10], "gold_answer_span": "cells release stored chemical energy"}, leaves)
        self.assertEqual(gold["paragraphs"], ["p2"])
        self.assertEqual(gold["sections"], ["s2"])

    def test_metrics_exclude_unmapped_questions(self) -> None:
        """Reuse effectiveness metrics without counting negatives or uncertain mappings."""
        m = metric_block([{"answerable": True, "first_relevant_rank": 1, "latency_ms": 1.},
                          {"answerable": False, "first_relevant_rank": None, "latency_ms": 2.}])
        self.assertEqual(m["answerable_questions"], 1)
        self.assertEqual(m["mrr"], 1.0)


if __name__ == "__main__":
    unittest.main()
