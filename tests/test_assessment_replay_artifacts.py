"""Replay the complete retained evaluation with network and inference forbidden."""

from pathlib import Path
import shutil
import socket

import pytest

from textbook_audit.assessment_protocol import fingerprint, read_json
from textbook_audit.assessment_runner import ARMS, read_raw, rebuild
import textbook_audit.assessment_runner as runner


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "reports" / "assessment_results_v1"


def raw_path(directory, question_id, arm):
    return directory / "raw" / (fingerprint({"question_id": question_id, "arm": arm}) + ".json")


def forbidden(*_args, **_kwargs):
    raise AssertionError("Cached artifact replay must not use network, retrieval or model inference.")


@pytest.mark.parametrize("name", ["final", "fresh_final"])
def test_all_real_question_arm_artifacts_replay_without_network_or_models(tmp_path, monkeypatch, name):
    source = RESULTS / name
    expected = read_json(source / "metrics.json")
    manifest = read_json(source / "run.json")
    assert manifest["complete"] and manifest["arms"] == list(ARMS)
    assert len(manifest["question_ids"]) == 45
    assert fingerprint(read_json(source / "pipeline.json")) == manifest["pipeline_sha256"]
    destination = tmp_path / name
    shutil.copytree(source, destination)
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "HF_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    for name in ("dispatch_paid", "load_assessment_model", "baseline_rankings", "ingest_benchmark"):
        monkeypatch.setattr(runner, name, forbidden)
    actual = rebuild(destination, ROOT)
    assert fingerprint(actual) == expected["checksum"]
    assert actual["cached_rebuild_model_calls"] == 0
    assert actual["identical_request_reuses"] == 46
    assert actual["metrics"]["proposed"]["complete_supporting_document_recall"] == 44 / 45
    for question_id in manifest["question_ids"]:
        hybrid = read_raw(raw_path(destination, question_id, "hybrid_rrf"))
        bypass = read_raw(raw_path(destination, question_id, "without_cross_document_selection"))
        assert hybrid["context"]["checksum"] == bypass["context"]["checksum"]
        assert hybrid["generation"]["raw_text"] == bypass["generation"]["raw_text"]
        assert hybrid["generation"]["validation"] == bypass["generation"]["validation"]
        assert all(document["kind"] == "hotpotqa" for document in hybrid["snapshot"]["source_documents"])


def test_fresh_run_uses_new_generation_with_identical_question_context_inputs():
    final, fresh = RESULTS / "final", RESULTS / "fresh_final"
    first, second = read_json(final / "run.json"), read_json(fresh / "run.json")
    assert first["run_id"] != second["run_id"]
    for key in ("question_ids", "pipeline_sha256", "protocol_sha256", "corpus_fingerprint"):
        assert first[key] == second[key]
    changed = 0
    for question_id in first["question_ids"]:
        for arm in ARMS:
            before, after = read_raw(raw_path(final, question_id, arm)), read_raw(raw_path(fresh, question_id, arm))
            assert before["runtime_input_sha256"] == after["runtime_input_sha256"]
            assert before["context"]["checksum"] == after["context"]["checksum"]
            changed += before["generation"]["raw_text"] != after["generation"]["raw_text"]
    assert changed > 0


def test_incomplete_real_cohort_cannot_produce_a_successful_cached_report(tmp_path, monkeypatch):
    directory = tmp_path / "incomplete"
    shutil.copytree(RESULTS / "final", directory)
    manifest = read_json(directory / "run.json")
    missing = raw_path(directory, manifest["question_ids"][0], ARMS[0]).with_suffix(".json.gz")
    missing.unlink()
    monkeypatch.setattr(runner, "dispatch_paid", forbidden)
    with pytest.raises(FileNotFoundError, match="selected question/arm"):
        rebuild(directory, ROOT)
