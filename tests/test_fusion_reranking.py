"""Regression tests for Phase C cached fusion and candidate-budget gates."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.fusion_reranking import (
    FULL_POOL_METHODS, _minmax, load_phase_b_rows, preselect, rank_full_pool,
)
from textbook_audit.experiment_tracking import experiment_paths, read_jsonl


def candidate(identifier: str, score: float, source_ranks: dict[str, int],
              *, gold: bool = False, text: str = "neutral passage") -> dict:
    """Build one cached Phase B-shaped candidate for isolated ranking tests."""
    return {
        "rank": 1,
        "candidate_id": identifier,
        "unit_type": "fixed_chunk",
        "source_ranks": source_ranks,
        "score": score,
        "matches_accepted_evidence": gold,
        "representation": text,
    }


class FusionRerankingTests(unittest.TestCase):
    """Protect fusion determinism, gold isolation, budgets, and cached inputs."""

    def setUp(self) -> None:
        """Create candidates with deliberately conflicting source/model ranks."""
        self.pool = [
            candidate("a", 0.2, {"soft_fusion_hybrid": 1, "page_dense_bge_small": 3},
                      text="plants make food with light"),
            candidate("b", 0.9, {"fixed_400_80_bm25": 1},
                      gold=True, text="unrelated wire resistance"),
            candidate("c", 0.5, {"page_dense_bge_small": 1,
                                  "fixed_400_80_dense_bge_small": 2},
                      text="chlorophyll absorbs light"),
        ]

    def test_minmax_handles_constant_scores(self) -> None:
        """Avoid division by zero while keeping a neutral deterministic signal."""
        self.assertEqual(_minmax({"a": 4.0, "b": 4.0}), {"a": 0.0, "b": 0.0})

    def test_every_full_pool_method_is_deterministic(self) -> None:
        """Return the same unique IDs on repeated calls for every fusion rule."""
        for method in FULL_POOL_METHODS:
            first = [item["candidate_id"] for item in rank_full_pool(self.pool, method)]
            second = [item["candidate_id"] for item in rank_full_pool(self.pool, method)]
            self.assertEqual(first, second, method)
            self.assertEqual(set(first), {"a", "b", "c"})

    def test_ranking_does_not_consult_gold_flags(self) -> None:
        """Changing evaluation labels must never change a Phase C ordering."""
        flipped = copy.deepcopy(self.pool)
        for item in flipped:
            item["matches_accepted_evidence"] = not item["matches_accepted_evidence"]
        for method in FULL_POOL_METHODS:
            original = [item["candidate_id"] for item in rank_full_pool(self.pool, method)]
            relabelled = [item["candidate_id"] for item in rank_full_pool(flipped, method)]
            self.assertEqual(original, relabelled, method)

    def test_reranker_and_soft_controls_follow_their_intended_signal(self) -> None:
        """Confirm the two endpoint controls honor cross score and soft rank."""
        self.assertEqual(rank_full_pool(self.pool, "bge_reranker_score")[0]["candidate_id"], "b")
        self.assertEqual(rank_full_pool(self.pool, "soft_fusion_no_reranker")[0]["candidate_id"], "a")

    def test_bm25_preselector_is_capped_and_query_relevant(self) -> None:
        """Use candidate text—not gold or cross score—for the fast first stage."""
        selected = preselect(self.pool, "How do plants make food with light?",
                             "bm25_fast_reranker", 8)
        self.assertEqual(len(selected), 3)
        self.assertEqual(selected[0]["candidate_id"], "a")

    def test_generated_phase_b_cache_has_complete_lossless_pools(self) -> None:
        """Guard the exact cached artifact Phase C depends on after restarts."""
        rows = load_phase_b_rows(ROOT)
        self.assertEqual(len(rows), 66)
        self.assertEqual(len({row["question_id"] for row in rows}), 66)
        answerable = [row for row in rows if row["evaluation_status"] == "answerable"]
        self.assertEqual(len(answerable), 61)
        self.assertTrue(all(any(item["matches_accepted_evidence"]
                                for item in row["ranked_candidates"])
                            for row in answerable))

    def test_generated_phase_c_checkpoint_is_resumable(self) -> None:
        """Lock full-pool recall, rejected caps, retained logic, and Phase D handoff."""
        paths = experiment_paths(ROOT)
        records = [record for record in read_jsonl(paths["runs"])
                   if record["phase"] == "C"]
        self.assertEqual(len(records), 13)
        full = [record for record in records if record["run_id"].startswith("phase_c_c1_")]
        capped = [record for record in records if record["run_id"].startswith("phase_c_c2_")]
        self.assertEqual(len(full), 7)
        self.assertEqual(len(capped), 6)
        self.assertTrue(all(record["candidate_recall"]["count"] == 61 for record in full))
        self.assertTrue(all(record["decision"] == "reject" for record in capped))
        self.assertTrue(all(not record["candidate_recall"]["required_invariant_satisfied"]
                            for record in capped))

        state = json.loads(paths["state"].read_text(encoding="utf-8"))
        current_phase = state["current_phase"]
        self.assertTrue(
            current_phase.startswith("Complete")
            or current_phase.split()[1] in {"D", "E", "F", "G", "H", "I", "J"}
        )
        retained = set(state["current_best_configurations"]["phase_c"]["retained_run_ids"])
        self.assertEqual(retained, {
            "phase_c_c1_soft_fusion_no_reranker_full_pool",
            "phase_c_c1_bge_rank_plus_rrf_rank_full_pool",
        })
        self.assertEqual(state["model_cache_status"]["bge_reranker_base"]["status"], "cached")


if __name__ == "__main__":
    unittest.main()
