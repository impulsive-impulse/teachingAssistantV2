"""Regression tests for candidate evidence normalization and complementarity."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.candidate_complementarity import (Candidate, _scopes,
                                                      accepted_page_ids,
                                                      deduplicate_candidates,
                                                      oracle_hit,
                                                      pairwise_overlap,
                                                      unique_wins)


def candidate(retriever: str, candidate_id: str, text: str, *,
              pages: tuple[int, ...] = (11,), correct: bool = False) -> Candidate:
    """Build a compact shared-schema candidate for deterministic unit tests."""
    return Candidate(retriever, 1, candidate_id, "test", "biology", pages,
                     ("2",), text, correct, (candidate_id,) if correct else ())


class CandidateComplementarityTests(unittest.TestCase):
    """Protect matching, deduplication, oracle, overlap, and slice invariants."""

    def test_page_evidence_requires_gold_span_not_only_gold_page(self) -> None:
        """Reject an accepted page whose text lacks the accepted answer span."""
        question = {"gold_pdf_pages": [11, 12], "alternative_gold_pages": [],
                    "gold_answer_span": "plants use sunlight to make food"}
        pages = [
            {"pdf_page_number": 11, "textbook_page_number": 2,
             "cleaned_text": "Plants use sunlight to make food during photosynthesis."},
            {"pdf_page_number": 12, "textbook_page_number": 3,
             "cleaned_text": "This page discusses an unrelated classroom activity."},
        ]
        self.assertEqual(accepted_page_ids(question, pages, 0.5), {11})

    def test_cross_unit_dedup_uses_page_and_text_containment(self) -> None:
        """Merge a paragraph contained in a page but retain unrelated same-page text."""
        paragraph = "plants use sunlight water and carbon dioxide to make food and release oxygen"
        page = candidate("page", "page-11", "intro words " + paragraph + " closing words")
        chunk = candidate("chunk", "chunk-1", paragraph)
        unrelated = candidate("chunk", "chunk-2", "digestive enzymes break food inside the stomach", pages=(11,))
        clusters = deduplicate_candidates([page, chunk, unrelated])
        self.assertEqual(len(clusters), 2)
        self.assertEqual({item.candidate_id for item in clusters[0]}, {"page-11", "chunk-1"})

    def test_pairwise_overlap_and_unique_useful_candidates(self) -> None:
        """Count shared evidence and correct evidence unique to one retriever."""
        shared_text = "light travels from one transparent medium into another medium"
        left = [candidate("left", "page-1", shared_text),
                candidate("left", "page-2", "unique correct plant evidence here with enough text tokens", pages=(12,), correct=True)]
        right = [candidate("right", "chunk-1", shared_text),
                 candidate("right", "chunk-2", "different incorrect evidence with enough text tokens", pages=(13,))]
        result = pairwise_overlap(left, right)
        self.assertEqual(result["shared_evidence_clusters"], 1)
        self.assertEqual(result["union_evidence_clusters"], 3)
        self.assertEqual(result["unique_useful_candidates_left"], 1)
        self.assertEqual(result["unique_useful_candidates_right"], 0)

    def test_oracle_and_unique_win_calculation(self) -> None:
        """Use a separate top-K budget for every method in a candidate union."""
        ranks = {"dense": 9, "bm25": None, "soft": 3}
        self.assertTrue(oracle_hit(ranks, ("dense", "bm25"), 10))
        self.assertFalse(oracle_hit(ranks, ("dense", "bm25"), 5))
        first = {"Q1": {"dense": 2, "bm25": None},
                 "Q2": {"dense": 4, "bm25": 3},
                 "Q3": {"dense": None, "bm25": 7}}
        wins = unique_wins(first, ("dense", "bm25"), 5)
        self.assertEqual(wins, {"dense": ["Q1"], "bm25": []})

    def test_required_slices_exclude_negative_questions(self) -> None:
        """Build canonical/natural, book, dependency, and query-style slices."""
        questions = [
            {"question_id": "C", "benchmark_slice": "canonical", "book_id": "biology",
             "formula_dependency": True},
            {"question_id": "N", "benchmark_slice": "natural_student", "book_id": "physical_sciences",
             "query_style": "colloquial", "visual_dependency": True},
            {"question_id": "NEG", "benchmark_slice": "canonical", "book_id": "biology"},
        ]
        scopes = _scopes(questions, {"C", "N"})
        self.assertEqual(scopes["all_answerable"], ["C", "N"])
        self.assertEqual(scopes["canonical"], ["C"])
        self.assertEqual(scopes["natural_student"], ["N"])
        self.assertEqual(scopes["formula_dependent"], ["C"])
        self.assertEqual(scopes["query_style:colloquial"], ["N"])

    def test_generated_audit_artifacts_preserve_depths_and_slice_counts(self) -> None:
        """Lock the reviewed-set denominator and required union headline counts."""
        results = ROOT / "data/retrieval/candidate_complementarity_results.jsonl"
        metrics_path = ROOT / "reports/candidate_complementarity_metrics.json"
        self.assertTrue(results.is_file())
        self.assertTrue(metrics_path.is_file())
        rows = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 66 * 15 * 3)
        self.assertEqual({row["candidate_depth"] for row in rows}, {5, 10, 20})
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        canonical = metrics["union_metrics"]["canonical"]["all_primary_retrievers"]
        natural = metrics["union_metrics"]["natural_student"]["all_primary_retrievers"]
        self.assertEqual((canonical["answerable_questions"], natural["answerable_questions"]), (41, 20))
        self.assertEqual((canonical["oracle_hit_at_20_count"], natural["oracle_hit_at_20_count"]), (40, 20))


if __name__ == "__main__":
    unittest.main()
