"""Regression tests for pinned, local Phase D reranker comparisons."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.reranker_bakeoff import (
    MODEL_CONFIGS, _snapshot_path, _snapshot_size, rank_scored_candidates,
    stratified_screen_rows,
)
from textbook_audit.experiment_tracking import experiment_paths, read_jsonl


def candidate(identifier: str, source_ranks: dict[str, int],
              *, gold: bool = False) -> dict:
    """Build one Phase B-shaped candidate for isolated model-rank tests."""
    return {
        "candidate_id": identifier,
        "source_ranks": source_ranks,
        "matches_accepted_evidence": gold,
        "representation": f"passage {identifier}",
    }


class RerankerBakeoffTests(unittest.TestCase):
    """Protect pinned-cache resolution, rank blending, and gold isolation."""

    def setUp(self) -> None:
        """Create model and retrieval ranks that intentionally disagree."""
        self.pool = [
            candidate("a", {"page_dense_bge_small": 1}),
            candidate("b", {"fixed_400_80_bm25": 1,
                              "soft_fusion_hybrid": 1}, gold=True),
            candidate("c", {"page_dense_bge_small": 9}),
        ]
        self.scores = [0.9, 0.7, 0.2]

    def test_raw_model_score_order(self) -> None:
        """Use descending model score and stable ID tie-breaks."""
        ranked = rank_scored_candidates(self.pool, self.scores, "reranker_score")
        self.assertEqual([item["candidate_id"] for item in ranked], ["a", "b", "c"])

    def test_rank_blend_is_deterministic_and_gold_blind(self) -> None:
        """Changing accepted-evidence flags must not alter blended ordering."""
        flipped = copy.deepcopy(self.pool)
        for item in flipped:
            item["matches_accepted_evidence"] = not item["matches_accepted_evidence"]
        first = rank_scored_candidates(
            self.pool, self.scores, "reranker_rank_plus_rrf_rank")
        second = rank_scored_candidates(
            flipped, self.scores, "reranker_rank_plus_rrf_rank")
        self.assertEqual([item["candidate_id"] for item in first],
                         [item["candidate_id"] for item in second])

    def test_score_count_must_match_pool(self) -> None:
        """Fail clearly instead of silently dropping an unscored candidate."""
        with self.assertRaisesRegex(ValueError, "score count"):
            rank_scored_candidates(self.pool, [0.1], "reranker_score")

    def test_snapshot_resolution_and_size(self) -> None:
        """Resolve only the requested revision and count its runtime files."""
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            model_name = "owner/model"
            revision = "abc123"
            snapshot = cache / "models--owner--model" / "snapshots" / revision
            snapshot.mkdir(parents=True)
            (snapshot / "config.json").write_bytes(b"123")
            (snapshot / "model.safetensors").write_bytes(b"12345")
            self.assertEqual(_snapshot_path(cache, model_name, revision), snapshot)
            self.assertEqual(_snapshot_size(snapshot), 8)

    def test_minilm_revision_is_pinned_and_cached(self) -> None:
        """Guard the exact approved commit and local snapshot needed to rerun."""
        config = MODEL_CONFIGS["minilm_l6"]
        self.assertEqual(config["revision"],
                         "c5ee24cb16019beea0893ab7796b1df96625c6b8")
        cache = ROOT / "data" / "retrieval" / "cache" / "models"
        self.assertTrue(_snapshot_path(cache, config["model_name"],
                                       config["revision"]).is_dir())

    def test_stratified_screen_uses_book_and_slice_only(self) -> None:
        """Select equal deterministic groups without reading evidence labels."""
        rows = []
        for book in ("biology", "physical_sciences"):
            for slice_name in ("canonical", "natural_student"):
                for index in range(3):
                    rows.append({"question_id": f"{book}-{slice_name}-{index}",
                                 "book_id": book, "benchmark_slice": slice_name,
                                 "matches_gold": bool(index % 2)})
        selected = stratified_screen_rows(rows, 2)
        self.assertEqual(len(selected), 8)
        self.assertTrue(all(not row["question_id"].endswith("-2") for row in selected))

    def test_bge_v2_revision_is_pinned_and_cached(self) -> None:
        """Guard the approved quality-model commit and verified local snapshot."""
        config = MODEL_CONFIGS["bge_v2_m3"]
        self.assertEqual(config["revision"],
                         "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e")
        cache = ROOT / "data" / "retrieval" / "cache" / "models"
        self.assertTrue(_snapshot_path(cache, config["model_name"],
                                       config["revision"]).is_dir())

    def test_mxbai_revision_is_pinned_and_cached(self) -> None:
        """Guard the final approved reranker commit and verified local snapshot."""
        config = MODEL_CONFIGS["mxbai_base_v1"]
        self.assertEqual(config["revision"],
                         "800f24c113213a187e65bde9db00c15a2bb12738")
        cache = ROOT / "data" / "retrieval" / "cache" / "models"
        self.assertTrue(_snapshot_path(cache, config["model_name"],
                                       config["revision"]).is_dir())

    def test_generated_phase_d_checkpoint_and_stopping_decisions(self) -> None:
        """Lock retained MiniLM, stopped large models, cache state, and E handoff."""
        paths = experiment_paths(ROOT)
        records = [record for record in read_jsonl(paths["runs"])
                   if record["phase"] == "D"]
        self.assertEqual(len(records), 3)
        by_id = {record["run_id"]: record for record in records}
        self.assertEqual(by_id["phase_d_d1_minilm_l6_full_pool"]["decision"], "retain")
        self.assertEqual(by_id["phase_d_d3_bge_v2_m3_full_pool_screen_8"]["decision"],
                         "investigate")
        stopped = by_id["phase_d_d4_mxbai_base_v1_full_pool_screen_8"]
        self.assertEqual(stopped["decision"], "reject")
        self.assertEqual(stopped["metrics"]["overall"]["answerable_questions"], 0)

        state = json.loads(paths["state"].read_text(encoding="utf-8"))
        current_phase = state["current_phase"]
        self.assertTrue(
            current_phase.startswith("Complete")
            or current_phase.split()[1] in {"E", "F", "G", "H", "I", "J"}
        )
        selection = state["current_best_configurations"]["phase_d"]["selection"]
        self.assertEqual(selection["speed_oriented_reranker"],
                         "phase_d_d1_minilm_l6_full_pool")
        self.assertEqual(state["model_cache_status"]["mxbai_base_v1"]["status"], "cached")


if __name__ == "__main__":
    unittest.main()
