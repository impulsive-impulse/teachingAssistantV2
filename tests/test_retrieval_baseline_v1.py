"""Regression coverage for the immutable Retrieval Baseline v1 contract."""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from textbook_audit.baseline_freeze import (build_manifest, validate_golden,
                                            verify_manifest)
from textbook_audit.context_assembly import assemble_context
from textbook_audit.query_processing import (apply_synonym_rules,
                                             textbook_synonym_expansion)
from textbook_audit.retrieval import reciprocal_rank_fusion
from textbook_audit.retrieval_baseline import (RetrievalBaseline, load_config,
                                               sha256_file, validate_config)
from textbook_audit.specialist_retrieval import (lift_specialist_ranking,
                                                 specialist_activated)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/retrieval_baseline_v1.yaml"
# Changing any byte requires a new baseline version and an explicit test update.
FROZEN_CONFIG_SHA256 = "736fb9325794caead4439316b6ca546bd782cd7029b4f9f7788f545c5b43baa6"


@pytest.fixture(scope="module")
def config() -> dict:
    """Load the canonical v1 configuration once for schema-focused tests."""
    return load_config(CONFIG, ROOT)


@pytest.fixture(scope="module")
def runtime(config: dict) -> RetrievalBaseline:
    """Load the pinned local model and all validated indexes once per module."""
    return RetrievalBaseline(ROOT, config, "cpu")


def _public(config: dict) -> dict:
    """Remove loader-only provenance before direct schema validation."""
    return {key: copy.deepcopy(value) for key, value in config.items()
            if key != "_config_path"}


def test_configuration_loads_complete_frozen_values(config: dict) -> None:
    """Chunking, model revision, RRF, and top-K must remain exact."""
    assert config["chunking"]["target_tokens"] == 600
    assert config["chunking"]["overlap_tokens"] == 100
    assert config["embedding"]["revision"] == "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    assert config["fusion"]["rrf_k"] == 60
    assert config["output"]["final_top_k"] == 5


def test_configuration_rejects_missing_and_unknown_fields(config: dict) -> None:
    """No behavior-affecting value may silently fall back to a default."""
    missing = _public(config)
    del missing["bm25"]["k1"]
    with pytest.raises(ValueError, match="missing"):
        validate_config(missing)
    unknown = _public(config)
    unknown["fusion"]["new_weight"] = 0.5
    with pytest.raises(ValueError, match="unknown"):
        validate_config(unknown)


def test_configuration_checksum_is_immutable() -> None:
    """Protect the canonical v1 file from silent edits."""
    assert sha256_file(CONFIG) == FROZEN_CONFIG_SHA256


def test_synonym_expansion_is_config_driven_and_deterministic(config: dict) -> None:
    """The YAML rule table must reproduce the selected Phase G transformation."""
    query = "How do plants eat?"
    first = apply_synonym_rules(query, config["query_processing"]["rules"])
    second = apply_synonym_rules(query, config["query_processing"]["rules"])
    assert first == second == textbook_synonym_expansion(query)


@pytest.mark.parametrize(
    ("branch", "query", "expected"),
    [("formula", "How is focal length calculated?", True),
     ("table", "Compare mitosis and meiosis", True),
     ("visual", "Show the principal rays in the diagram", True),
     ("formula", "What is photosynthesis?", False)],
)
def test_configured_specialist_activation(config: dict, branch: str,
                                          query: str, expected: bool) -> None:
    """Each frozen regex must activate only from query text."""
    settings = config["specialists"][branch]
    assert specialist_activated(branch, query, settings["activation_version"],
                                settings["activation_pattern"]) is expected


def test_page_prior_lifts_to_every_child_with_stable_ties() -> None:
    """Specialist page order must become a deterministic child-chunk ranking."""
    chunks = [{"pdf_pages": [11]}, {"pdf_pages": [10, 11]}, {"pdf_pages": [10]}]
    documents = [{"pdf_pages": [10]}, {"pdf_pages": [11]}]
    lifted = lift_specialist_ranking(chunks, documents, np.asarray([1, 0]))
    assert lifted.tolist() == [0, 1, 2]


def test_rrf_and_overlap_merge_use_frozen_parameters() -> None:
    """RRF k=60 and exact overlap joining must retain their measured behavior."""
    scores = reciprocal_rank_fusion([np.asarray([0, 1]), np.asarray([1, 0])], 2, 60)
    assert scores[0] == scores[1] == 1 / 61 + 1 / 62
    shared = " ".join(f"w{i}" for i in range(8))
    chunks = [
        {"chunk_id": "a", "text": f"left {shared}", "pdf_pages": [1],
         "textbook_pages": [1], "chapter_title": "C", "section_title": "S"},
        {"chunk_id": "b", "text": f"{shared} right", "pdf_pages": [2],
         "textbook_pages": [2], "chapter_title": "C", "section_title": "S"},
    ]
    merged = assemble_context("overlap_merge_metadata_preserving", [0, 1], chunks,
                              count=2, overlap_minimum=8, overlap_maximum=140)
    assert merged[0]["text"] == f"left {shared} right"
    assert merged[0]["source_chunk_ids"] == ["a", "b"]


def test_structured_entry_point_limits_to_five_and_preserves_metadata(config: dict,
                                                                      monkeypatch) -> None:
    """The public response contains five evidence units and no benchmark fields."""
    instance = RetrievalBaseline.__new__(RetrievalBaseline)
    instance.config = config
    instance.chunks = {"biology": [
        {"chunk_id": f"c{i}", "text": f"text {i}", "pdf_pages": [i + 1],
         "textbook_pages": [i], "chapter_title": "Chapter", "section_title": "Section"}
        for i in range(6)]}
    instance.loaded = type("Loaded", (), {"metadata": {"model_name": "test"}})()
    instance.chunk_index = {}
    instance.specialist_indexes = {}
    ranked = {
        "processed_query": "question", "activated_specialists": [],
        "ranking": np.arange(6), "scores": np.arange(6, 0, -1, dtype=float),
        "component_rankings": {"fixed_chunk_dense": {i: i + 1 for i in range(6)}},
        "component_raw_scores": {"fixed_chunk_dense": np.arange(6, 0, -1, dtype=float)},
        "latency_ms": 1.0,
    }
    monkeypatch.setattr(instance, "_rank", lambda question, book_id: ranked)
    result = instance.retrieve("question", "biology").to_dict()
    assert len(result["evidence"]) == 5
    assert result["evidence"][0]["evidence_id"] == "c0"
    assert result["evidence"][0]["chapter"] == "Chapter"
    assert "gold" not in json.dumps(result).lower()


def test_production_runtime_has_no_gold_label_dependency() -> None:
    """The public runtime source must not import or name benchmark gold fields."""
    source = inspect.getsource(__import__(
        "textbook_audit.retrieval_baseline", fromlist=["retrieval_baseline"]))
    assert "gold_pdf_pages" not in source
    assert "gold_answer_span" not in source


def test_resolved_revision_and_all_indexes_are_exact(runtime: RetrievalBaseline,
                                                     config: dict) -> None:
    """Local inference must resolve the pinned commit and hit every valid cache."""
    assert runtime.loaded.metadata["resolved_model_revision"] == config["embedding"]["revision"]
    assert all(item["cache_hit"] for item in runtime.chunk_index.values())
    assert all(item["cache_hit"] for method in runtime.specialist_indexes.values()
               for item in method.values())


def test_golden_fixture_and_repeat_ordering(runtime: RetrievalBaseline) -> None:
    """Representative canonical/natural/specialist queries remain stable twice."""
    result = validate_golden(ROOT, runtime, repeat=2)
    assert result["cases"] == 8
    assert result["deterministic"] is True


def test_manifest_generation_and_checksum_verification(runtime: RetrievalBaseline,
                                                       config: dict, tmp_path: Path) -> None:
    """Manifest paths and hashes must describe the exact frozen inputs/indexes."""
    manifest = build_manifest(ROOT, config, runtime)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = verify_manifest(ROOT, path)
    assert result["mismatches"] == []
    assert manifest["configuration"]["sha256"] == FROZEN_CONFIG_SHA256
