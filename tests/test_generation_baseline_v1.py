"""Regression tests for the frozen Generation Baseline v1 decision."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from textbook_audit.generation_baseline import (
    DEFAULT_CONFIG,
    EXPECTED_LABELS,
    artifact_paths,
    build_manifest,
    load_config,
    validate_evidence,
    verify_manifest,
)
from textbook_audit.generation_experiments import ROOT
from textbook_audit.retrieval_baseline import sha256_file


# Filled with the reviewed config's final digest. A behavior change must create
# Generation Baseline v2 instead of updating this v1 constant.
FROZEN_CONFIG_SHA256 = "758c0a857b427ab73c790b6031a14762c6653f8714f0fef29830373439ab78ba"


@pytest.fixture(scope="module")
def config() -> dict:
    """Load the immutable baseline once for read-only validation tests."""
    return load_config(DEFAULT_CONFIG)


def test_generation_baseline_identity_and_profiles_are_frozen(config: dict) -> None:
    """Protect the primary online profile and explicit offline fallback roles."""
    assert config["baseline"]["frozen"] is True
    assert config["baseline"]["default_profile"] == "online_quality"
    assert config["profiles"]["online_quality"]["resolved_and_frozen_model"] == "gpt-4o-2024-08-06"
    assert config["profiles"]["local_offline"]["model_file"] == "Qwen3-8B-Q4_K_M.gguf"


def test_generation_baseline_config_checksum_is_immutable() -> None:
    """Require a semantic-version bump for any v1 configuration byte change."""
    assert sha256_file(DEFAULT_CONFIG) == FROZEN_CONFIG_SHA256


def test_generation_baseline_rejects_unknown_top_level_fields(tmp_path: Path) -> None:
    """Prevent silently ignored configuration fields from changing behavior."""
    changed = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    changed["unexpected"] = True
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="fields changed"):
        load_config(path)


def test_frozen_evidence_is_complete_and_matches_recorded_metrics(config: dict) -> None:
    """Validate 40 paired questions, explicit labels, source rows, and sign-off."""
    result = validate_evidence(ROOT, config)
    assert result["questions"] == 40
    assert result["online_completed"] == 80
    assert result["local_completed"] == {"gold": 40, "retrieved": 40}
    assert result["human_review"] == "accepted"
    assert len(EXPECTED_LABELS) == 4


def test_manifest_covers_every_declared_artifact(config: dict, tmp_path: Path) -> None:
    """Ensure the lock manifest is portable and every declared checksum verifies."""
    manifest = build_manifest(ROOT, config)
    assert [item["path"] for item in manifest["artifacts"]] == artifact_paths(config)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = verify_manifest(ROOT, path)
    assert result["valid"] is True
    assert result["artifacts_checked"] == len(artifact_paths(config))
