"""Regression tests for deterministic candidate fusion and reranking."""

from __future__ import annotations

import sys
import json
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.candidate_complementarity import Candidate
from textbook_audit.reranker import (
    SOURCE_RETRIEVERS, build_candidate_pool, first_gold_rank,
    format_query_passage, map_scores_to_candidates, normalize_passage_text,
    retrieval_metrics,
)


def item(source: str, rank: int, identifier: str, text: str, *,
         page: int = 10, gold: bool = False) -> Candidate:
    """Create one compact source candidate with realistic metadata."""
    return Candidate(source, rank, identifier, "fixed_chunk", "biology",
                     (page,), (str(page - 2),), text, gold,
                     (identifier,) if gold else (), "Life Processes", "Nutrition")


def source_lists() -> dict[str, list[Candidate]]:
    """Build all four required source lists for fusion tests."""
    return {source: [item(source, 1, f"{source}-1",
                          f"distinct evidence text for {source} with enough tokens", page=index + 10)]
            for index, source in enumerate(SOURCE_RETRIEVERS)}


class RerankerTests(unittest.TestCase):
    """Protect pool, formatting, score mapping, metrics, slices, and budgets."""

    def test_pool_requires_every_configured_source(self) -> None:
        """Fail clearly instead of silently constructing an incomplete union."""
        rankings = source_lists(); del rankings[SOURCE_RETRIEVERS[-1]]
        with self.assertRaisesRegex(ValueError, "missing required"):
            build_candidate_pool(rankings)

    def test_pool_deduplicates_cross_unit_evidence(self) -> None:
        """Cluster contained same-page evidence and retain source contributions."""
        rankings = source_lists()
        shared = "plants make food using sunlight water carbon dioxide and release oxygen"
        rankings[SOURCE_RETRIEVERS[0]][0] = item(SOURCE_RETRIEVERS[0], 1, "page", "intro " + shared + " ending", gold=True)
        rankings[SOURCE_RETRIEVERS[1]][0] = item(SOURCE_RETRIEVERS[1], 1, "chunk", shared, gold=True)
        pool = build_candidate_pool(rankings)
        merged = next(candidate for candidate in pool if len(candidate.source_ranks) == 2)
        self.assertTrue(merged.matches_gold)
        self.assertEqual(dict(merged.source_ranks), {SOURCE_RETRIEVERS[0]: 1, SOURCE_RETRIEVERS[1]: 1})

    def test_rrf_order_is_deterministic_and_gold_blind(self) -> None:
        """Rank multi-source agreement first regardless of its gold label."""
        rankings = source_lists()
        shared = "light changes direction when moving between two transparent materials"
        rankings[SOURCE_RETRIEVERS[0]][0] = item(SOURCE_RETRIEVERS[0], 1, "a", shared, gold=False)
        rankings[SOURCE_RETRIEVERS[1]][0] = item(SOURCE_RETRIEVERS[1], 1, "b", shared, gold=False)
        rankings[SOURCE_RETRIEVERS[2]][0] = item(SOURCE_RETRIEVERS[2], 1, "gold", "unrelated but accepted direct evidence tokens here", page=22, gold=True)
        pool = build_candidate_pool(rankings)
        self.assertEqual(len(pool[0].source_ranks), 2)
        self.assertFalse(pool[0].matches_gold)

    def test_query_passage_format_excludes_benchmark_labels(self) -> None:
        """Send only the query, neutral headings, and normalized content."""
        candidate = build_candidate_pool(source_lists())[0]
        formatted = format_query_passage("How do plants eat?", candidate)
        self.assertIn("Query: How do plants eat?", formatted)
        self.assertIn("Chapter: Life Processes", formatted)
        self.assertIn("Section: Nutrition", formatted)
        self.assertNotIn("difficulty", formatted.lower())
        self.assertNotIn("gold", formatted.lower())

    def test_passage_policy_truncates_at_word_boundary(self) -> None:
        """Avoid splitting the last word when limiting extracted passage text."""
        normalized = normalize_passage_text("alpha   beta gamma delta", 12)
        self.assertEqual(normalized, "alpha beta")

    def test_score_mapping_preserves_input_identity_and_ties(self) -> None:
        """Map batched outputs by position and use RRF as the deterministic tie."""
        pool = build_candidate_pool(source_lists())
        reranked = map_scores_to_candidates(pool, np.array([0.1, 0.9, 0.2, 0.3]))
        self.assertEqual(reranked[0][0].candidate_id, pool[1].candidate_id)
        tied = map_scores_to_candidates(pool, [1.0] * len(pool))
        expected = sorted(pool, key=lambda value: (-value.fusion_score, value.candidate_id))
        self.assertEqual([x[0].candidate_id for x in tied], [x.candidate_id for x in expected])

    def test_first_gold_rank_handles_control_and_scored_lists(self) -> None:
        """Use one matching rule for fused controls and reranker score tuples."""
        rankings = source_lists()
        rankings[SOURCE_RETRIEVERS[2]][0] = item(SOURCE_RETRIEVERS[2], 1, "gold", "accepted evidence content with enough unique words", page=30, gold=True)
        pool = build_candidate_pool(rankings)
        self.assertEqual(first_gold_rank(pool), first_gold_rank([(value, 0.0) for value in pool]))

    def test_metrics_exclude_negative_queries_and_calculate_mrr(self) -> None:
        """Keep negatives outside effectiveness denominators while timing all rows."""
        rows = [
            {"answerable": True, "first_gold_rank": 1, "latency_ms": 10, "candidate_count": 10},
            {"answerable": True, "first_gold_rank": 4, "latency_ms": 20, "candidate_count": 10},
            {"answerable": False, "first_gold_rank": None, "latency_ms": 30, "candidate_count": 10},
        ]
        metrics = retrieval_metrics(rows)
        self.assertEqual(metrics["answerable_questions"], 2)
        self.assertEqual(metrics["hit_at_1_count"], 1)
        self.assertEqual(metrics["hit_at_5_count"], 2)
        self.assertAlmostEqual(metrics["mrr"], 0.625)

    def test_candidate_budget_is_a_prefix_of_same_control_pool(self) -> None:
        """Compare 10 versus 20 without changing upstream candidate ordering."""
        rankings = {source: [item(source, rank, f"{source}-{rank}",
                    f"source {source} rank {rank} unique evidence words here", page=rank + index * 30)
                    for rank in range(1, 21)] for index, source in enumerate(SOURCE_RETRIEVERS)}
        pool20 = build_candidate_pool(rankings, maximum_candidates=20)
        self.assertEqual(build_candidate_pool(rankings, maximum_candidates=10), pool20[:10])

    def test_generated_artifacts_preserve_budgets_slices_and_negatives(self) -> None:
        """Lock output shape, reviewed denominator, budgets, and negative split."""
        results_path = ROOT / "data/retrieval/reranker_results.jsonl"
        metrics_path = ROOT / "reports/reranker_metrics.json"
        self.assertTrue(results_path.is_file()); self.assertTrue(metrics_path.is_file())
        rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 66 * 2 * 2 * 5)
        self.assertEqual({row["candidate_budget"] for row in rows}, {10, 20})
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        self.assertEqual(metrics["overall"]["20"]["bge_reranker_base"]["answerable_questions"], 61)
        self.assertEqual(len(metrics["negative_queries"]["20"]["excluded_question_ids"]), 5)
        self.assertEqual(metrics["slices"]["20"]["canonical"]["bge_reranker_base"]["answerable_questions"], 41)
        self.assertEqual(metrics["slices"]["20"]["natural_student"]["bge_reranker_base"]["answerable_questions"], 20)


if __name__ == "__main__":
    unittest.main()
