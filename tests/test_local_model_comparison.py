"""Controls for isolated, versioned local-model comparison experiments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from textbook_audit.generation_phase_a import LocalLlamaServer
from textbook_audit.local_model_human_review import build_packet
from textbook_audit.local_model_report import (
    build_benchmark_table,
    build_control_reference,
    build_final_decision,
    build_gate_leaderboard,
    build_quality_table,
)
from textbook_audit.verified_download import ranges
from textbook_audit.local_model_comparison import (
    corruption_reason,
    output_schema_valid,
    runtime_log_evidence,
    smoke_gate_unreachable,
    verify_model_artifact,
)


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "reports/local_model_comparison_v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_frozen_controls_remain_exact() -> None:
    config = json.loads((EXPERIMENT / "experiment_config.json").read_text(encoding="utf-8"))
    for key in (
        "retrieval_baseline",
        "generation_baseline",
        "historical_generation_experiment",
        "generation_benchmark",
        "development_evidence_source",
    ):
        item = config["frozen_inputs"][key]
        assert sha256_file(ROOT / item["path"]) == item["sha256"]


def test_development_snapshot_is_prompt_safe_and_exact() -> None:
    config = json.loads((EXPERIMENT / "experiment_config.json").read_text(encoding="utf-8"))
    snapshot = ROOT / config["frozen_inputs"]["development_evidence_snapshot"]["path"]
    assert sha256_file(snapshot) == config["frozen_inputs"]["development_evidence_snapshot"]["sha256"]
    rows = read_jsonl(snapshot)
    historical = json.loads(
        (ROOT / "config/generation_experiments_v1.json").read_text(encoding="utf-8")
    )
    assert [row["question_id"] for row in rows] == historical["split"]["development_question_ids"]
    assert all(len(row["evidence"]) == 5 for row in rows)
    forbidden = {"required_answer_points", "optional_answer_points", "unsupported_claims"}
    assert all(not (forbidden & set(row)) for row in rows)


def test_weights_and_runtimes_are_confined_to_ignored_storage() -> None:
    config = json.loads((EXPERIMENT / "experiment_config.json").read_text(encoding="utf-8"))
    registry = json.loads((EXPERIMENT / "artifact_registry.json").read_text(encoding="utf-8"))
    assert all(
        profile["binary_root"].startswith("app_data/models/")
        for profile in config["runtime_profiles"].values()
    )
    destination = registry["candidates"]["gemma_3_12b_it_qat_q4_0"]["download"]["destination"]
    assert destination.startswith("app_data/models/")


def test_opencl_log_gate_requires_device_kernels_and_real_offload() -> None:
    valid = """
    GPUOpenCL: Qualcomm(R) Adreno(TM) X1-85 GPU
    using device GPUOpenCL (Qualcomm(R) Adreno(TM) X1-85 GPU)
    using kernels optimized for Adreno (GGML_OPENCL_USE_ADRENO_KERNELS)
    offloaded 49/49 layers to GPU
    """
    evidence = runtime_log_evidence("adreno_opencl", valid)
    assert evidence["valid"]
    assert evidence["offloaded_layers"] == 49
    with pytest.raises(RuntimeError, match="silent fallback"):
        runtime_log_evidence("adreno_opencl", "CPU model loaded successfully")


def test_cpu_log_gate_rejects_unexpected_gpu_selection() -> None:
    assert runtime_log_evidence("cpu_arm64", "CPU buffer size = 100 MiB")["valid"]
    with pytest.raises(RuntimeError, match="unexpectedly"):
        runtime_log_evidence(
            "cpu_arm64",
            "using device GPUOpenCL\noffloaded 2/49 layers to GPU",
        )


def test_corruption_screen_catches_known_bad_streams() -> None:
    assert corruption_reason('{"status":"answered"}') is None
    assert corruption_reason("<unused14> " * 30) == "unused_token_stream"
    assert corruption_reason("same " * 25) == "repeated_token_stream"


def test_output_validity_gate_separates_schema_from_bad_citation_values() -> None:
    assert output_schema_valid({
        "status": "answered",
        "answer": "A",
        "errors": ["citation page metadata does not match supplied evidence"],
    })
    assert not output_schema_valid({
        "status": "answered",
        "answer": "A",
        "errors": ["output must contain exactly the five required keys"],
    })


def test_smoke_gate_stops_only_when_perfect_remainder_cannot_recover() -> None:
    def result(structured: bool, citation: float) -> dict:
        return {
            "status": "completed",
            "output_schema_valid": structured,
            "evaluation": {
                "structured_output_valid": structured,
                "citation_validity": citation,
            },
        }

    assert smoke_gate_unreachable([result(False, 0.0)], 8, 0.875, 0.875) is None
    assert smoke_gate_unreachable(
        [result(False, 0.0), result(False, 0.0)], 8, 0.875, 0.875
    ) == "smoke_structured_output_gate_unreachable"
    assert smoke_gate_unreachable(
        [result(True, 0.0), result(True, 0.0)], 8, 0.875, 0.875
    ) == "smoke_citation_gate_unreachable"


def test_llama_timing_parser_separates_prompt_and_generation(tmp_path: Path) -> None:
    log = tmp_path / "server.log"
    prefix = "older session\n"
    log.write_text(
        prefix
        + "slot print_timing: prompt eval time =  1200.00 ms / 120 tokens "
        "(10.00 ms per token, 100.00 tokens per second)\n"
        + "slot print_timing: eval time = 2000.00 ms / 40 tokens "
        "(50.00 ms per token, 20.00 tokens per second)\n",
        encoding="utf-8",
    )
    timings = LocalLlamaServer._request_timings(log, len(prefix.encode("utf-8")))
    assert timings == {
        "prompt_eval_seconds": 1.2,
        "prompt_tokens_per_second": 100.0,
        "generation_eval_seconds": 2.0,
        "generation_tokens_per_second": 20.0,
    }


def test_blind_packet_rotates_labels_and_requires_identical_context() -> None:
    benchmark = [{
        "question_id": "Q1",
        "normalized_question": "Why?",
        "requires_formula": False,
        "requires_visual": False,
        "requires_table": False,
        "requires_multiple_passages": False,
        "required_answer_points": ["because"],
        "optional_answer_points": [],
        "prohibited_or_unsupported_claims": [],
    }]

    def run(run_id: str, answer: str, context_hash: str = "same") -> tuple[dict, dict]:
        result = {
            "question_id": "Q1",
            "status": "completed",
            "context_sha256": context_hash,
            "supplied_evidence": [{"evidence_id": "E1", "text": "because"}],
            "parsed_output": {
                "answer": answer,
                "status": "answered",
                "selected_evidence_ids": ["E1"],
                "citations": [],
            },
        }
        return (
            {"run_id": run_id, "model_key": run_id, "backend": "cpu_arm64",
             "stage": "development"},
            {"Q1": result},
        )

    packet, key = build_packet(benchmark, [run("r1", "one"), run("r2", "two")])
    assert len(packet) == 1
    assert {answer["label"] for answer in packet[0]["answers"]} == {"Answer A", "Answer B"}
    assert set(key["questions"]["Q1"]) == {"Answer A", "Answer B"}
    with pytest.raises(ValueError, match="identical evidence"):
        build_packet(benchmark, [run("r1", "one"), run("r2", "two", "different")])


def test_generated_tables_label_partial_stages_and_backend_evidence() -> None:
    manifest = {
        "run_id": "model__smoke__adreno_opencl__id",
        "model": {"display_name": "Model", "evaluation_order": 1},
        "stage": "smoke",
        "backend": "adreno_opencl",
        "backend_log_evidence": {
            "offloaded_layers": 10,
            "available_layers": 10,
        },
        "metrics": {
            "questions": 3,
            "required_point_coverage": 0.5,
            "citation_validity": 1.0,
            "schema_valid_output_rate": 1.0,
            "structured_output_rate": 2 / 3,
            "p50_time_to_first_token_seconds": 1.25,
            "peak_rss_bytes": 2 * 1024 ** 3,
        },
        "decision": "reject",
    }
    benchmark = build_benchmark_table([manifest])
    quality = build_quality_table([manifest])
    assert "| smoke | adreno_opencl | 3 | 10/10 | 1.25 |" in benchmark
    assert "| smoke | adreno_opencl | 3 | 50.0% | 100.0% |" in quality
    assert "100.0% | 66.7% | reject |" in quality


def test_gate_leaderboard_and_final_decision_require_all_rejections() -> None:
    manifest = {
        "run_id": "control__development__adreno_opencl__id",
        "model_key": "qwen3_8b_q4_k_m_control",
        "model": {"display_name": "Control"},
        "stage": "development",
        "backend": "adreno_opencl",
        "metrics": {
            "questions": 16,
            "required_point_coverage": 0.5,
            "citation_validity": 1.0,
            "schema_valid_output_rate": 1.0,
            "p50_time_to_first_token_seconds": 2.0,
            "p50_latency_seconds": 3.0,
        },
    }
    registry = {
        "candidates": {
            "qwen3_8b_q4_k_m_control": {
                "control": True,
                "display_name": "Control",
            },
            "candidate": {
                "evaluation_order": 1,
                "display_name": "Candidate",
                "evaluation": {"decision": "reject", "reason": "invalid_output"},
            },
        }
    }
    leaderboard = build_gate_leaderboard([manifest], registry)
    assert "Only model to pass smoke and complete development" in leaderboard
    decision = build_final_decision(registry)
    assert "do not advance any tested candidate" in decision
    registry["candidates"]["candidate"]["evaluation"]["decision"] = "pending"
    assert "narrowing is incomplete" in build_final_decision(registry)


def test_versioned_report_support_preserves_v1_conclusions() -> None:
    registry = json.loads(
        (EXPERIMENT / "artifact_registry.json").read_text(encoding="utf-8")
    )
    decision = build_final_decision(registry)
    assert "Gemma failed the smoke citation gate" in decision
    assert "Phi-4 Mini and Mistral Small" in decision


def test_control_reference_is_explicitly_labelled_and_optional() -> None:
    registry = {
        "candidates": {
            "control": {
                "control": True,
                "display_name": "Frozen control",
            },
            "candidate": {
                "evaluation_order": 1,
                "evaluation": {
                    "control_opencl_validity_reference": {
                        "ttft_seconds": 10,
                        "latency_seconds": 20,
                        "prompt_tokens_per_second": 30,
                        "generation_tokens_per_second": 4,
                        "peak_rss_gib": 5,
                        "sampled_peak_gpu_local_memory_gib": 3,
                    }
                },
            },
        }
    }
    reference = build_control_reference(registry)
    assert "Frozen control validity reference" in reference
    assert "not rerun or modified" in reference
    assert "| Frozen control | adreno_opencl | 10.00 | 20.00 |" in reference
    del registry["candidates"]["candidate"]["evaluation"]
    assert build_control_reference(registry) == ""


def test_parallel_download_ranges_cover_boundary_exactly() -> None:
    intervals = ranges(7, 31, 4)
    assert intervals[0][0] == 7
    assert intervals[-1][1] == 30
    assert sum(end - start + 1 for start, end in intervals) == 24
    assert all(
        left_end + 1 == right_start
        for (_, left_end), (right_start, _) in zip(intervals, intervals[1:])
    )


def test_versioned_experiment_configuration_is_not_the_completed_v1() -> None:
    experiment = ROOT / "reports/local_model_comparison_v2_qwen36_27b"
    if not experiment.is_dir():
        pytest.skip("Qwen3.6 comparison metadata has not been created")
    config = json.loads((experiment / "experiment_config.json").read_text(encoding="utf-8"))
    assert config["experiment_id"] == "local_model_comparison_v2_qwen36_27b"
    assert config["production_baselines_mutable"] is False
    assert experiment != EXPERIMENT


def test_split_artifact_verifies_every_shard(tmp_path: Path) -> None:
    contents = [b"first shard", b"second shard"]
    shards = []
    for index, content in enumerate(contents, start=1):
        filename = f"model-{index:05d}-of-00002.gguf"
        (tmp_path / filename).write_bytes(content)
        shards.append(
            {
                "filename": filename,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    verified = verify_model_artifact(tmp_path / shards[0]["filename"], {"shards": shards})
    assert len(verified["files"]) == 2
    assert verified["files"][1]["sha256"] == shards[1]["sha256"]


def test_split_artifact_rejects_a_bad_secondary_shard(tmp_path: Path) -> None:
    first = tmp_path / "model-00001-of-00002.gguf"
    second = tmp_path / "model-00002-of-00002.gguf"
    first.write_bytes(b"good")
    second.write_bytes(b"bad")
    artifact = {
        "shards": [
            {
                "filename": first.name,
                "bytes": 4,
                "sha256": hashlib.sha256(b"good").hexdigest(),
            },
            {
                "filename": second.name,
                "bytes": 3,
                "sha256": hashlib.sha256(b"expected").hexdigest(),
            },
        ]
    }
    with pytest.raises(ValueError, match="model shard checksum differs"):
        verify_model_artifact(first, artifact)
