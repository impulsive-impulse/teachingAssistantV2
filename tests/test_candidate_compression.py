"""Regression tests for Phase A selection and persistent experiment records."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.candidate_complementarity import Candidate
from textbook_audit.candidate_compression import (
    BUDGETS, CompressionConfig, QueryContext, broad_configs, first_gold_rank,
    metric_block, query_relevance_configs, select_candidates,
)
from textbook_audit.experiment_tracking import (
    checkpoint_run, create_run_directory, experiment_paths,
    initialize_experiment, read_jsonl, render_resume,
)
from textbook_audit.reranker import SOURCE_RETRIEVERS


def candidate(source: str, rank: int, *, gold: bool = False,
              shared: bool = False) -> Candidate:
    """Build one realistic source candidate with stable evidence metadata."""
    page = rank if shared else rank + SOURCE_RETRIEVERS.index(source) * 100
    text = ("shared direct evidence about plants making food using sunlight water carbon dioxide"
            if shared else
            f"distinct source {source} rank {rank} evidence terms for deterministic testing")
    return Candidate(source, rank, f"{source}-{rank}", "fixed_chunk", "biology",
                     (page,), (str(page),), text, gold,
                     (f"evidence-{rank}",) if gold else (), "Nutrition", "Photosynthesis")


def rankings(gold_source: str | None = None) -> dict[str, list[Candidate]]:
    """Create four complete source lists with one optional accepted candidate."""
    return {
        source: [candidate(source, rank,
                           gold=(source == gold_source and rank == 3),
                           shared=(rank == 1))
                 for rank in range(1, 21)]
        for source in SOURCE_RETRIEVERS
    }


class CandidateCompressionTests(unittest.TestCase):
    """Protect gold blindness, budgets, selector diversity, metrics, and history."""

    def test_every_selector_is_deterministic_and_respects_budgets(self) -> None:
        """Return exactly the configured number of candidates on repeated calls."""
        source_lists = rankings()
        for config in broad_configs():
            for budget in BUDGETS:
                first = select_candidates(source_lists, config, budget)
                second = select_candidates(source_lists, config, budget)
                self.assertEqual(len(first), budget)
                self.assertEqual([item.candidate_id for item in first],
                                 [item.candidate_id for item in second])

    def test_candidate_order_is_gold_blind(self) -> None:
        """Toggling accepted-evidence annotations cannot affect selection order."""
        for config in broad_configs():
            plain = select_candidates(rankings(), config, 10)
            labelled = select_candidates(rankings(SOURCE_RETRIEVERS[-1]), config, 10)
            self.assertEqual([item.candidate_id for item in plain],
                             [item.candidate_id for item in labelled])

    def test_query_aware_order_is_also_gold_blind(self) -> None:
        """Dense/BM25 candidate fusion cannot inspect accepted-evidence flags."""
        plain_rankings = rankings()
        labelled_rankings = rankings(SOURCE_RETRIEVERS[-1])
        vector = np.asarray([1.0, 0.0], dtype=np.float32)
        vectors = {item.candidate_id: vector
                   for items in plain_rankings.values() for item in items}
        context = QueryContext("plants make food", vector, 0.0, vectors)
        for config in query_relevance_configs():
            plain = select_candidates(plain_rankings, config, 10, context)
            labelled = select_candidates(labelled_rankings, config, 10, context)
            self.assertEqual([item.candidate_id for item in plain],
                             [item.candidate_id for item in labelled])

    def test_fixed_quotas_preserve_all_sources(self) -> None:
        """An eight-candidate quota pool includes evidence from every source."""
        selected = select_candidates(rankings(), CompressionConfig("fixed_source_quotas"), 8)
        represented = {source for item in selected for source, _ in item.source_ranks}
        self.assertEqual(represented, set(SOURCE_RETRIEVERS))

    def test_first_gold_rank_and_metrics_exclude_negatives(self) -> None:
        """Evaluate labels only after selection and exclude negative denominators."""
        selected = select_candidates(rankings(SOURCE_RETRIEVERS[0]),
                                     CompressionConfig("plain_rrf"), 20)
        rank = first_gold_rank(selected)
        rows = [
            {"answerable": True, "first_gold_rank": rank, "latency_ms": 1.0},
            {"answerable": True, "first_gold_rank": 1, "latency_ms": 2.0},
            {"answerable": False, "first_gold_rank": None, "latency_ms": 3.0},
        ]
        metrics = metric_block(rows)
        self.assertEqual(metrics["answerable_questions"], 2)
        self.assertEqual(metrics["hit_at_1_count"], 1)

    def test_append_only_tracking_and_leaderboard(self) -> None:
        """Checkpoint one run and refuse a duplicate run ID without truncation."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_experiment(root, [{"phase": "A"}], ["run-1"], {})
            run_dir = create_run_directory(root, "run-1")
            (run_dir / "metrics.json").write_text("{}\n", encoding="utf-8")
            block = {"answerable_questions": 2, "hit_at_1_count": 1, "hit_at_1": 0.5,
                     "hit_at_3_count": 2, "hit_at_3": 1.0,
                     "hit_at_5_count": 2, "hit_at_5": 1.0, "mrr": 0.75}
            record = {
                "run_id": "run-1", "timestamp": "2026-01-01T00:00:00+00:00",
                "phase": "A", "parent_run_id": None,
                "changed_variable": "selector",
                "configuration": {"pipeline_name": "test"}, "random_seed": 0,
                "input_artifact_versions": {}, "model_revisions": {},
                "metrics": {"overall": block, "canonical": block,
                            "natural_student": block},
                "latency": {"p50_ms": 1.0, "p95_ms": 2.0},
                "peak_memory": {"peak_rss_mb": 10.0},
                "disk_index_size": {"run_artifacts_bytes": 3},
                "candidate_recall": {"count": 2, "answerable_questions": 2,
                                     "recall": 1.0},
                "decision": "retain", "concise_reason": "lossless test",
                "output_artifact_paths": ["metrics.json"],
                "reproduce_command": "python test.py",
            }
            checkpoint_run(root, record, "next")
            paths = experiment_paths(root)
            self.assertEqual(len(read_jsonl(paths["runs"])), 1)
            self.assertIn("run-1", paths["leaderboard"].read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ValueError, "already exists"):
                checkpoint_run(root, record, "next")
            self.assertEqual(len(read_jsonl(paths["runs"])), 1)

    def test_resume_document_uses_current_unresolved_questions(self) -> None:
        """Recovery text must follow live state instead of stale Phase A copy."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = {
                "project_objective": "test objective",
                "current_phase": "Phase F",
                "completed_run_ids": [], "retained_configurations": [],
                "rejected_configurations": [], "current_best_configurations": {},
                "unresolved_questions": ["Does the current winner transfer?"],
                "exact_next_action": "Run the next isolated test.",
            }
            render_resume(root, state)
            text = experiment_paths(root)["resume"].read_text(encoding="utf-8")
            self.assertIn("Does the current winner transfer?", text)
            self.assertNotIn("smallest gold-blind compressed budget", text)

    def test_context_metrics_can_use_shared_decision_journal(self) -> None:
        """Context-only checkpoints must not invent retrieval Hit@K fields."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_experiment(root, [{"phase": "I"}], ["context-1"], {})
            create_run_directory(root, "context-1")
            block = {"questions": 2, "direct_evidence_hit_count": 2,
                     "answer_span_retained_count": 1,
                     "average_context_tokens": 900.0}
            record = {
                "run_id": "context-1", "timestamp": "2026-01-01T00:00:00+00:00",
                "phase": "I", "parent_run_id": "retrieval-1",
                "changed_variable": "assembler",
                "configuration": {"assembler": "test"}, "random_seed": 0,
                "input_artifact_versions": {}, "model_revisions": {},
                "metrics": {"overall": block, "canonical": block,
                            "natural_student": block},
                "latency": {"p95_ms": 1.0}, "peak_memory": {},
                "disk_index_size": {"new_index_bytes": 0},
                "candidate_recall": {"count": 2, "answerable_questions": 2,
                                     "recall": 1.0},
                "decision": "retain", "concise_reason": "context test",
                "output_artifact_paths": [], "reproduce_command": "python test.py",
            }
            checkpoint_run(root, record, "stop")
            journal = experiment_paths(root)["decisions"].read_text(encoding="utf-8")
            self.assertIn("direct evidence 2/2", journal)
            self.assertIn("exact span 1/2", journal)

    def test_generated_phase_a_checkpoint_is_lossless_and_resumable(self) -> None:
        """Lock the Phase A invariant, immutable history, and Phase B handoff."""
        paths = experiment_paths(ROOT)
        self.assertTrue(paths["state"].is_file())
        records = read_jsonl(paths["runs"])
        # Later phases append to the same immutable history.  Count only Phase A
        # here so this checkpoint test remains valid after the experiment moves on.
        phase_a_records = [record for record in records if record["phase"] == "A"]
        self.assertEqual(len(phase_a_records), 20)
        self.assertEqual(len({record["run_id"] for record in records}), len(records))
        winner = next(record for record in phase_a_records
                      if record["run_id"] == "phase_a_a4_uncompressed_union_t080")
        self.assertEqual(winner["candidate_recall"]["count"], 61)
        self.assertTrue(winner["candidate_recall"]["required_invariant_satisfied"])
        self.assertEqual(winner["configuration"]["pool_statistics"]["maximum"], 57)
        state = json.loads(paths["state"].read_text(encoding="utf-8"))
        self.assertIn(state["current_phase"].split()[1], {"B", "C", "D", "E", "F", "G", "H", "I", "J"})
        self.assertEqual(state["current_best_configurations"]["phase_a"]["pipeline_name"],
                         "uncompressed_union_t080")


if __name__ == "__main__":
    unittest.main()
