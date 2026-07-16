"""Regression tests for deterministic Phase B candidate presentations."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.candidate_complementarity import Candidate
from textbook_audit.candidate_representation import (
    RepresentationCatalog, RepresentationPolicy, _two_non_overlapping_windows,
    represent_candidate,
)
from textbook_audit.reranker import MergedCandidate
from textbook_audit.experiment_tracking import experiment_paths, read_jsonl


def merged(unit_type: str, text: str, *, identifier: str = "item-1") -> MergedCandidate:
    """Create one merged candidate without exposing gold to representation logic."""
    item = Candidate("source", 1, identifier, unit_type, "biology", (11,), ("2",),
                     text, False, (), "Nutrition", "Photosynthesis")
    return MergedCandidate(identifier, item, (item,), (("source", 1),), 1.0,
                           False, ())


class CandidateRepresentationTests(unittest.TestCase):
    """Protect lexical spans, headings, neighbours, and neutral formatting."""

    def test_relevant_paragraph_uses_query_not_leading_text(self) -> None:
        """Select the paragraph containing the student's query vocabulary."""
        candidate = merged("page", "unrelated leading material followed by plant food details")
        catalog = RepresentationCatalog(
            {("biology", 11): ("The stomach digests food.",
                               "Green plants make food using sunlight and chlorophyll.")}, {})
        policy = RepresentationPolicy("page", page_policy="relevant_paragraph")
        text = represent_candidate("How do green plants make food?", candidate, policy, catalog)
        self.assertIn("Green plants make food", text)
        self.assertNotIn("stomach", text.lower())

    def test_two_windows_are_deterministic_and_nonduplicated(self) -> None:
        """Return two disjoint spans in textbook order with an explicit separator."""
        text = " ".join(["alpha"] * 140 + ["middle"] * 140 + ["target"] * 140)
        first = _two_non_overlapping_windows("target alpha", text)
        second = _two_non_overlapping_windows("target alpha", text)
        self.assertEqual(first, second)
        self.assertIn("[... ]".replace(" ", ""), first.replace(" ", ""))

    def test_chunk_heading_policies_change_only_neutral_context(self) -> None:
        """Add chapter/section labels without benchmark or evidence annotations."""
        candidate = merged("fixed_chunk", "Plants use chlorophyll to make food.")
        catalog = RepresentationCatalog({}, {})
        raw = represent_candidate("How do plants eat?", candidate,
                                  RepresentationPolicy("chunk", chunk_policy="raw_chunk"), catalog)
        headed = represent_candidate("How do plants eat?", candidate,
                                     RepresentationPolicy("chunk", chunk_policy="chapter_section_chunk"), catalog)
        self.assertNotIn("Chapter:", raw)
        self.assertIn("Chapter: Nutrition", headed)
        self.assertIn("Section: Photosynthesis", headed)
        self.assertNotIn("gold", headed.lower())
        self.assertNotIn("difficulty", headed.lower())

    def test_neighbor_expansion_uses_registered_same_section_neighbor(self) -> None:
        """Append an adjacent paragraph selected with query terms."""
        candidate = merged("fixed_chunk", "Light reaches a leaf.", identifier="fixed-1")
        neighbor = Candidate("neighbor", 1, "fixed-2", "fixed_chunk", "biology",
                             (11,), ("2",), "Chlorophyll absorbs light energy.", False,
                             (), "Nutrition", "Photosynthesis")
        catalog = RepresentationCatalog({}, {"fixed-1": (neighbor,)})
        represented = represent_candidate(
            "What does chlorophyll do?", candidate,
            RepresentationPolicy("chunk", chunk_policy="neighbor_expansion"), catalog)
        self.assertIn("Neighbouring context", represented)
        self.assertIn("Chlorophyll absorbs", represented)

    def test_generated_phase_b_checkpoint_is_lossless_and_resumable(self) -> None:
        """Lock the full reranker comparison, retained winner, and Phase C handoff."""
        paths = experiment_paths(ROOT)
        records = read_jsonl(paths["runs"])
        rerank_records = [
            record for record in records
            if record["run_id"].startswith("phase_b_b4_rerank_")
        ]
        self.assertEqual(len(rerank_records), 4)
        self.assertTrue(all(record["candidate_recall"]["count"] == 61
                            for record in rerank_records))
        self.assertTrue(all(record["candidate_recall"]["required_invariant_satisfied"]
                            for record in rerank_records))

        state = json.loads(paths["state"].read_text(encoding="utf-8"))
        self.assertIn(state["current_phase"].split()[1],
                      {"C", "D", "E", "F", "G", "H", "I", "J"})
        winner = state["current_best_configurations"]["phase_b"]
        self.assertEqual(
            winner["run_id"],
            "phase_b_b4_rerank_combination_dense_best_member_"
            "two_relevant_windows_neighbor_expansion",
        )
        self.assertEqual(winner["candidate_recall"], "61/61")
        self.assertEqual(winner["metrics"]["overall"]["hit_at_5_count"], 40)
        self.assertTrue((ROOT / "reports" / "experiments" /
                         "phase_b_candidate_representation.md").is_file())


if __name__ == "__main__":
    unittest.main()
