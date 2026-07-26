"""Successive-narrowing runner for Local Model Comparison v1.

The runner consumes only the saved prompt-safe evidence snapshot. It never
invokes retrieval during a model comparison and never writes to production v1
baseline directories.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from pathlib import Path
from typing import Any

from textbook_audit.generation_benchmark import read_jsonl, validate_benchmark
from textbook_audit.generation_experiments import (
    evaluate_answer,
    parse_output,
    render_prompt,
    summarize,
)
from textbook_audit.generation_phase_a import (
    LlamaServerConfig,
    LocalLlamaServer,
    ROOT,
    sha256_file,
    sha256_text,
    token_recall,
    utc_now,
    write_json_atomic,
    write_jsonl_atomic,
)


EXPERIMENT_DIR = ROOT / "reports/local_model_comparison_v1"
DEFAULT_CONFIG = EXPERIMENT_DIR / "experiment_config.json"
DEFAULT_REGISTRY = EXPERIMENT_DIR / "artifact_registry.json"
STAGES = ("validity", "smoke", "development", "holdout")
BACKENDS = ("cpu_arm64", "adreno_opencl")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise ValueError(f"unsupported schema in {path}")
    return value


def verify_frozen_inputs(config: dict[str, Any]) -> dict[str, str]:
    """Verify every declared comparison control before model inference."""

    verified: dict[str, str] = {}
    for name, item in config["frozen_inputs"].items():
        expected = item.get("sha256")
        if not expected:
            raise ValueError(f"frozen input {name} has no checksum")
        path = ROOT / item["path"]
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"frozen input {name} checksum mismatch")
        verified[name] = actual
    return verified


def load_evidence_snapshot(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    path = ROOT / config["frozen_inputs"]["development_evidence_snapshot"]["path"]
    rows = read_jsonl(path)
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        question_id = row["question_id"]
        if question_id in result:
            raise ValueError(f"duplicate evidence snapshot row: {question_id}")
        evidence = row["evidence"]
        if len(evidence) != config["comparison_contract"]["evidence_count"]:
            raise ValueError(f"{question_id}: evidence count differs from contract")
        actual = sha256_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
        if actual != row["context_sha256"]:
            raise ValueError(f"{question_id}: evidence context checksum mismatch")
        result[question_id] = row
    return result


def stage_question_ids(
    stage: str, historical_config: dict[str, Any], snapshot: dict[str, dict[str, Any]]
) -> list[str]:
    if stage == "validity":
        ids = [historical_config["split"]["smoke_question_ids"][0]]
    elif stage == "smoke":
        ids = list(historical_config["split"]["smoke_question_ids"])
    elif stage == "development":
        ids = list(historical_config["split"]["development_question_ids"])
    else:
        raise ValueError(
            "holdout is unavailable until a finalist decision creates and pins "
            "a separate holdout evidence snapshot"
        )
    missing = sorted(set(ids) - set(snapshot))
    if missing:
        raise ValueError(f"saved evidence snapshot is missing IDs: {missing}")
    return ids


def runtime_log_evidence(backend: str, text: str) -> dict[str, Any]:
    """Reject silent backend fallback and return auditable offload evidence."""

    lowered = text.lower()
    matches = re.findall(r"offloaded\s+(\d+)/(\d+)\s+layers to gpu", lowered)
    offloaded, available = (map(int, matches[-1])) if matches else (0, 0)
    evidence = {
        "backend": backend,
        "adreno_device_named": "qualcomm(r) adreno(tm) x1-85 gpu" in lowered,
        "opencl_device_selected": "using device gpuopencl" in lowered,
        "adreno_kernels_selected": "using kernels optimized for adreno" in lowered,
        "offloaded_layers": offloaded,
        "available_layers": available,
        "valid": False,
    }
    if backend == "adreno_opencl":
        evidence["valid"] = bool(
            evidence["adreno_device_named"]
            and evidence["opencl_device_selected"]
            and evidence["adreno_kernels_selected"]
            and offloaded > 0
        )
        if not evidence["valid"]:
            raise RuntimeError("OpenCL log evidence is incomplete; rejecting silent fallback")
    else:
        evidence["valid"] = not (evidence["opencl_device_selected"] or offloaded > 0)
        if not evidence["valid"]:
            raise RuntimeError("CPU control unexpectedly selected/offloaded to a GPU")
    return evidence


def corruption_reason(raw_text: str) -> str | None:
    text = raw_text.strip()
    if not text:
        return "empty_output"
    if re.search(r"<unused\d+>", text, flags=re.IGNORECASE):
        return "unused_token_stream"
    if text.count("\ufffd") > max(1, len(text) // 100):
        return "replacement_character_corruption"
    tokens = re.findall(r"\S+", text)
    longest_run = 1
    current_run = 1
    for previous, current in zip(tokens, tokens[1:]):
        if current == previous:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 1
    if longest_run >= 20:
        return "repeated_token_stream"
    return None


def output_schema_valid(parsed: dict[str, Any]) -> bool:
    """Separate JSON/schema validity from evidence-value validation.

    Unknown evidence IDs and incorrect page metadata remain citation failures,
    but they do not mean the model emitted a corrupt or structurally unusable
    response.
    """

    citation_value_errors = {
        "selected evidence contains unknown IDs",
        "citation uses unknown evidence ID",
        "citation page metadata does not match supplied evidence",
    }
    errors = set(parsed.get("errors", []))
    return bool(
        parsed.get("status") in {"answered", "insufficient_evidence"}
        and isinstance(parsed.get("answer"), str)
        and not (errors - citation_value_errors)
    )


def enrich_evaluation(
    benchmark_row: dict[str, Any],
    parsed: dict[str, Any],
    evidence: list[dict[str, Any]],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    cited_ids = {
        citation.get("evidence_id")
        for citation in parsed.get("citations", [])
        if isinstance(citation, dict)
    }
    cited_text = " ".join(
        item["text"] for item in evidence if item["evidence_id"] in cited_ids
    )
    answer = parsed.get("answer", "")
    support_recall = token_recall(answer, cited_text) if answer and cited_text else 0.0
    selected_count = len(set(parsed.get("selected_evidence_ids", [])))
    evaluation = dict(evaluation)
    evaluation.update(
        {
            "citation_support_token_recall": round(support_recall, 4),
            "citation_support_screen_pass": support_recall >= 0.55,
            "multi_passage_complete": (
                evaluation["required_point_coverage"] == 1.0 and selected_count >= 2
                if benchmark_row["requires_multiple_passages"]
                else None
            ),
        }
    )
    return evaluation


def comparison_summary(results: list[dict[str, Any]], load_seconds: float | None) -> dict[str, Any]:
    metrics = summarize(results, load_seconds)
    complete = [row for row in results if row.get("status") == "completed"]
    support = [
        row["evaluation"]["citation_support_token_recall"] for row in complete
    ]
    multi = [
        float(row["evaluation"]["multi_passage_complete"])
        for row in complete
        if row["evaluation"]["multi_passage_complete"] is not None
    ]
    metrics.update(
        {
            "schema_valid_output_rate": round(
                statistics.mean(float(row["output_schema_valid"]) for row in complete),
                4,
            )
            if complete
            else 0.0,
            "mean_citation_support_token_recall": round(statistics.mean(support), 4)
            if support
            else None,
            "multi_passage_completeness": round(statistics.mean(multi), 4)
            if multi
            else None,
        }
    )
    return metrics


def smoke_gate_unreachable(
    results: list[dict[str, Any]],
    planned_questions: int,
    minimum_structured: float,
    minimum_citation: float,
) -> str | None:
    """Return an early-stop reason when remaining perfect rows cannot pass."""

    completed = [row for row in results if row.get("status") == "completed"]
    remaining = planned_questions - len(completed)
    if remaining < 0:
        raise ValueError("smoke results exceed the planned question count")
    maximum_structured = (
        sum(
            float(
                row.get(
                    "output_schema_valid",
                    row["evaluation"]["structured_output_valid"],
                )
            )
            for row in completed
        )
        + remaining
    ) / planned_questions
    maximum_citation = (
        sum(row["evaluation"]["citation_validity"] for row in completed) + remaining
    ) / planned_questions
    if maximum_structured < minimum_structured:
        return "smoke_structured_output_gate_unreachable"
    if maximum_citation < minimum_citation:
        return "smoke_citation_gate_unreachable"
    return None


def make_run_id(
    model_key: str,
    stage: str,
    backend: str,
    artifact: dict[str, Any],
    runtime: dict[str, Any],
    decoding: dict[str, Any],
) -> str:
    body = json.dumps(
        {
            "model": model_key,
            "stage": stage,
            "backend": backend,
            "artifact_sha256": artifact["sha256"],
            "runtime": runtime,
            "decoding": decoding,
        },
        sort_keys=True,
    )
    suffix = hashlib.sha256(body.encode("utf-8")).hexdigest()[:10]
    return f"{model_key}__{stage}__{backend}__{suffix}"


def run_comparison(
    *,
    config_path: Path,
    registry_path: Path,
    model_path: Path,
    model_key: str,
    stage: str,
    backend: str,
    port: int,
) -> dict[str, Any]:
    config = load_json(config_path)
    registry = load_json(registry_path)
    frozen_hashes = verify_frozen_inputs(config)
    candidate = registry["candidates"][model_key]
    artifact = candidate["artifact"]
    if not candidate["download"]["approved"]:
        raise ValueError("candidate download/evaluation is not approved")
    if model_path.name != artifact["filename"]:
        raise ValueError("model filename differs from the approved artifact")
    actual_model_hash = sha256_file(model_path)
    if actual_model_hash != artifact["sha256"]:
        raise ValueError("model checksum differs from the approved artifact")

    historical = load_json(
        ROOT / config["frozen_inputs"]["historical_generation_experiment"]["path"]
    )
    benchmark_rows = read_jsonl(
        ROOT / config["frozen_inputs"]["generation_benchmark"]["path"]
    )
    validate_benchmark(benchmark_rows)
    benchmark_by_id = {row["question_id"]: row for row in benchmark_rows}
    snapshot = load_evidence_snapshot(config)
    question_ids = stage_question_ids(stage, historical, snapshot)

    runtime = dict(config["runtime_profiles"][backend])
    binary_root = ROOT / runtime.pop("binary_root")
    executable = binary_root / "llama-server.exe"
    if not executable.is_file():
        raise FileNotFoundError(executable)
    decoding = dict(candidate["recommended_decoding"])
    decoding["chat_template_kwargs"] = dict(
        candidate["chat_template"].get("kwargs", {})
    )
    run_id = make_run_id(model_key, stage, backend, artifact, runtime, decoding)
    run_dir = EXPERIMENT_DIR / "runs" / run_id
    question_dir = run_dir / "questions"
    question_dir.mkdir(parents=True, exist_ok=True)
    extra = ["--metrics"]
    if backend == "adreno_opencl":
        # Device assignment and offload lines are debug-level in current
        # llama.cpp builds; the experiment must capture them to reject fallback.
        extra.extend(["-lv", "5"])
    if stage == "validity":
        extra.append("--check-tensors")
    extra_arguments = tuple(extra)
    server = LocalLlamaServer(
        LlamaServerConfig(
            executable=executable,
            model=model_path,
            port=port,
            runtime=runtime,
            generation=decoding,
            log_dir=run_dir / "runtime_logs",
            extra_arguments=extra_arguments,
        )
    )
    pending = [
        question_id
        for question_id in question_ids
        if not (question_dir / f"{question_id}.json").is_file()
    ]
    load_seconds: float | None = None
    backend_evidence: dict[str, Any] | None = None
    rejected_reason: str | None = None
    if pending:
        with server:
            load_seconds = server.load_seconds
            backend_evidence = runtime_log_evidence(
                backend, server.stderr_session_text()
            )
            for question_id in pending:
                row = benchmark_by_id[question_id]
                evidence = snapshot[question_id]["evidence"]
                prompt = render_prompt(
                    row,
                    evidence,
                    config["comparison_contract"]["prompt_strategy"],
                    config["comparison_contract"]["context_strategy"],
                )
                if not candidate["chat_template"]["qwen_no_think_prefix"]:
                    prompt = prompt.removeprefix("/no_think\n")
                generation = server.generate(prompt)
                corruption = corruption_reason(generation["raw_text"])
                parsed = parse_output(generation["raw_text"], evidence)
                schema_valid = output_schema_valid(parsed)
                evaluation = enrich_evaluation(
                    row,
                    parsed,
                    evidence,
                    evaluate_answer(row, parsed, historical),
                )
                status = "completed" if corruption is None else "invalid_output"
                write_json_atomic(
                    question_dir / f"{question_id}.json",
                    {
                        "schema_version": 1,
                        "run_id": run_id,
                        "question_id": question_id,
                        "question": row["normalized_question"],
                        "book_id": row["book_id"],
                        "difficulty": row["difficulty"],
                        "dependency_flags": {
                            "formula": row["requires_formula"],
                            "visual": row["requires_visual"],
                            "table": row["requires_table"],
                            "multiple_passages": row["requires_multiple_passages"],
                        },
                        "status": status,
                        "corruption_reason": corruption,
                        "prompt_sha256": sha256_text(prompt),
                        "context_sha256": snapshot[question_id]["context_sha256"],
                        "supplied_evidence": evidence,
                        "generation": generation,
                        "parsed_output": parsed,
                        "output_schema_valid": schema_valid,
                        "evaluation": evaluation,
                        "completed_at": utc_now(),
                    },
                )
                if corruption is not None or (stage == "validity" and not schema_valid):
                    rejected_reason = corruption or "invalid_output_schema"
                    break
                if stage == "smoke":
                    current_results = [
                        json.loads(path.read_text(encoding="utf-8"))
                        for planned_id in question_ids
                        if (path := question_dir / f"{planned_id}.json").is_file()
                    ]
                    gate = config["stage_gates"]["smoke"]
                    rejected_reason = smoke_gate_unreachable(
                        current_results,
                        len(question_ids),
                        gate["minimum_structured_output_rate"],
                        gate["minimum_citation_validity"],
                    )
                    if rejected_reason:
                        break

    results = [
        json.loads(path.read_text(encoding="utf-8"))
        for question_id in question_ids
        if (path := question_dir / f"{question_id}.json").is_file()
    ]
    metrics = comparison_summary(results, load_seconds)
    if stage == "validity":
        validity_rows = [
            row for row in results
            if row.get("status") == "completed"
            and row.get("output_schema_valid", output_schema_valid(row["parsed_output"]))
        ]
        if len(validity_rows) != 1:
            rejected_reason = rejected_reason or "output_validity_gate_failed"
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": utc_now(),
        "model_key": model_key,
        "model": candidate,
        "model_path": str(model_path),
        "model_sha256": actual_model_hash,
        "stage": stage,
        "backend": backend,
        "runtime": runtime,
        "server_command": server.command(),
        "backend_log_evidence": backend_evidence,
        "chat_template": candidate["chat_template"],
        "decoding": decoding,
        "question_ids": question_ids,
        "completed_question_ids": [row["question_id"] for row in results],
        "frozen_input_hashes": frozen_hashes,
        "metrics": metrics,
        "decision": "reject" if rejected_reason else "pending_review",
        "rejected_reason": rejected_reason,
    }
    write_json_atomic(run_dir / "run_manifest.json", manifest)
    write_jsonl_atomic(run_dir / "results.jsonl", results)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-key", default="gemma_3_12b_it_qat_q4_0")
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--backend", choices=BACKENDS, required=True)
    parser.add_argument("--port", type=int, default=18101)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    manifest = run_comparison(
        config_path=args.config.resolve(),
        registry_path=args.registry.resolve(),
        model_path=args.model.resolve(),
        model_key=args.model_key,
        stage=args.stage,
        backend=args.backend,
        port=args.port,
    )
    print(
        json.dumps(
            {
                "run_id": manifest["run_id"],
                "decision": manifest["decision"],
                "rejected_reason": manifest["rejected_reason"],
                "metrics": manifest["metrics"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
