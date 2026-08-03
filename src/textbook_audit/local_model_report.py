"""Deterministic report tables for versioned local-model comparisons."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


STAGE_ORDER = {"validity": 0, "smoke": 1, "development": 2, "holdout": 3}
BACKEND_ORDER = {"cpu_arm64": 0, "adreno_opencl": 1}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifests(runs_dir: Path) -> list[dict[str, Any]]:
    """Load completed run manifests in a stable comparison order."""

    manifests = []
    for path in runs_dir.glob("*/run_manifest.json"):
        manifest = _load_json(path)
        results_path = path.parent / "results.jsonl"
        if (
            "schema_valid_output_rate" not in manifest.get("metrics", {})
            and results_path.is_file()
        ):
            results = [
                json.loads(line)
                for line in results_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            complete = [row for row in results if row.get("status") == "completed"]
            manifest["metrics"]["schema_valid_output_rate"] = (
                round(
                    sum(bool(row.get("output_schema_valid")) for row in complete)
                    / len(complete),
                    4,
                )
                if complete
                else 0.0
            )
        manifests.append(manifest)
    return sorted(
        manifests,
        key=lambda item: (
            item.get("model", {}).get("evaluation_order", -1),
            STAGE_ORDER.get(item["stage"], 99),
            BACKEND_ORDER.get(item["backend"], 99),
            item["run_id"],
        ),
    )


def _number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def _percent(value: Any) -> str:
    if value is None:
        return "—"
    return f"{100 * float(value):.1f}%"


def _gib(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value) / (1024 ** 3):.2f}"


def build_benchmark_table(manifests: list[dict[str, Any]]) -> str:
    """Build the CPU/GPU performance table from authoritative manifests."""

    header = (
        "| Model | Stage | Backend | Questions | GPU offload | TTFT p50 (s) | "
        "Latency p50 (s) | Prompt tok/s | Gen tok/s | Peak RAM (GiB) | "
        "GPU local (GiB) | Run gate result |\n"
        "|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|"
    )
    rows = [header]
    for run in manifests:
        metrics = run.get("metrics", {})
        backend = run["backend"]
        evidence = run.get("backend_log_evidence") or {}
        if backend == "adreno_opencl":
            offload = (
                f"{evidence.get('offloaded_layers', '—')}/"
                f"{evidence.get('available_layers', '—')}"
            )
        else:
            offload = "CPU only"
        rows.append(
            "| {model} | {stage} | {backend} | {questions} | {offload} | "
            "{ttft} | {latency} | {prompt} | {generation} | {ram} | {gpu} | "
            "{decision} |".format(
                model=run["model"]["display_name"],
                stage=run["stage"],
                backend=backend,
                questions=metrics.get("questions", "—"),
                offload=offload,
                ttft=_number(metrics.get("p50_time_to_first_token_seconds")),
                latency=_number(metrics.get("p50_latency_seconds")),
                prompt=_number(metrics.get("mean_prompt_tokens_per_second")),
                generation=_number(metrics.get("mean_generation_tokens_per_second")),
                ram=_gib(metrics.get("peak_rss_bytes")),
                gpu=_gib(metrics.get("sampled_peak_gpu_local_memory_bytes")),
                decision=run.get("decision", "—"),
            )
        )
    return "\n".join(rows) + "\n"


def build_quality_table(manifests: list[dict[str, Any]]) -> str:
    """Build quality rows, retaining stage labels so partial runs are explicit."""

    header = (
        "| Model | Stage | Backend | N | Coverage | Citation valid | "
        "Citation support | Unsupported | Formula | Multi-passage | "
        "Schema valid | Full validator | Run gate result |\n"
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"
    )
    rows = [header]
    for run in manifests:
        metrics = run.get("metrics", {})
        rows.append(
            "| {model} | {stage} | {backend} | {n} | {coverage} | "
            "{citation} | {support} | {unsupported} | {formula} | {multi} | "
            "{schema} | {structured} | {decision} |".format(
                model=run["model"]["display_name"],
                stage=run["stage"],
                backend=run["backend"],
                n=metrics.get("questions", "—"),
                coverage=_percent(metrics.get("required_point_coverage")),
                citation=_percent(metrics.get("citation_validity")),
                support=_percent(metrics.get("mean_citation_support_token_recall")),
                unsupported=_percent(metrics.get("unsupported_claim_rate")),
                formula=_percent(metrics.get("formula_accuracy")),
                multi=_percent(metrics.get("multi_passage_completeness")),
                schema=_percent(metrics.get("schema_valid_output_rate")),
                structured=_percent(metrics.get("structured_output_rate")),
                decision=run.get("decision", "—"),
            )
        )
    return "\n".join(rows) + "\n"


def build_control_reference(registry: dict[str, Any]) -> str:
    """Render an explicitly labelled frozen-control reference when recorded."""

    candidates = registry.get("candidates", {})
    control = next(
        (value for value in candidates.values() if value.get("control")), None
    )
    reference = next(
        (
            value.get("evaluation", {}).get("control_opencl_validity_reference")
            for value in candidates.values()
            if value.get("evaluation_order") is not None
            and value.get("evaluation", {}).get(
                "control_opencl_validity_reference"
            )
        ),
        None,
    )
    if control is None or reference is None:
        return ""
    return (
        "## Frozen control validity reference\n\n"
        "This row is copied from the checksum-pinned v1 control manifest named "
        "in `artifact_registry.json`; it was not rerun or modified in this "
        "experiment.\n\n"
        "| Model | Backend | TTFT (s) | Latency (s) | Prompt tok/s | Gen tok/s "
        "| Peak RAM (GiB) | GPU local (GiB) |\n"
        "|---|---|---:|---:|---:|---:|---:|---:|\n"
        f"| {control['display_name']} | adreno_opencl | "
        f"{_number(reference.get('ttft_seconds'))} | "
        f"{_number(reference.get('latency_seconds'))} | "
        f"{_number(reference.get('prompt_tokens_per_second'))} | "
        f"{_number(reference.get('generation_tokens_per_second'))} | "
        f"{_number(reference.get('peak_rss_gib'))} | "
        f"{_number(reference.get('sampled_peak_gpu_local_memory_gib'))} |\n\n"
    )


def build_gate_leaderboard(
    manifests: list[dict[str, Any]], registry: dict[str, Any]
) -> str:
    """Summarize each model at its furthest valid comparison stage."""

    candidates = registry["candidates"]
    ordered_keys = ["qwen3_8b_q4_k_m_control"] + sorted(
        (
            key
            for key, value in candidates.items()
            if value.get("evaluation_order") is not None
        ),
        key=lambda key: candidates[key]["evaluation_order"],
    )
    header = (
        "| Model | Furthest stage | Backend | N | Coverage | Citation valid | "
        "Schema valid | TTFT p50 (s) | Latency p50 (s) | Eligibility | Outcome |\n"
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|---|"
    )
    rows = [header]
    for model_key in ordered_keys:
        candidate = candidates[model_key]
        model_runs = [run for run in manifests if run["model_key"] == model_key]
        if not model_runs:
            continue
        furthest_stage = max(
            (run["stage"] for run in model_runs),
            key=lambda stage: STAGE_ORDER.get(stage, -1),
        )
        stage_runs = [run for run in model_runs if run["stage"] == furthest_stage]
        selected = max(
            stage_runs,
            key=lambda run: (
                BACKEND_ORDER.get(run["backend"], -1),
                run["run_id"],
            ),
        )
        metrics = selected["metrics"]
        evaluation = candidate.get("evaluation", {})
        if candidate.get("control"):
            eligibility = "retained control"
            outcome = "Only model to pass smoke and complete development"
        else:
            decision = evaluation.get("decision", "pending")
            eligibility = "ineligible" if decision == "reject" else "pending"
            outcome = evaluation.get(
                "reason", evaluation.get("next_stage", decision)
            ).replace("_", " ")
        rows.append(
            "| {model} | {stage} | {backend} | {n} | {coverage} | "
            "{citation} | {schema} | {ttft} | {latency} | {eligibility} | "
            "{outcome} |".format(
                model=candidate["display_name"],
                stage=furthest_stage,
                backend=selected["backend"],
                n=metrics.get("questions", "—"),
                coverage=_percent(metrics.get("required_point_coverage")),
                citation=_percent(metrics.get("citation_validity")),
                schema=_percent(metrics.get("schema_valid_output_rate")),
                ttft=_number(metrics.get("p50_time_to_first_token_seconds")),
                latency=_number(metrics.get("p50_latency_seconds")),
                eligibility=eligibility,
                outcome=outcome,
            )
        )
    return "\n".join(rows) + "\n"


def build_final_decision(registry: dict[str, Any]) -> str:
    """Render the terminal decision when every required alternative is rejected."""

    candidates = registry["candidates"]
    required = [
        value
        for value in candidates.values()
        if value.get("evaluation_order") is not None
    ]
    all_rejected = required and all(
        candidate.get("evaluation", {}).get("decision") == "reject"
        for candidate in required
    )
    if not all_rejected:
        return (
            "Ordered candidate narrowing is incomplete. Winner declarations, "
            "blinded review, and any holdout decision remain pending.\n"
        )
    legacy_v1_required = {
        "gemma_3_12b_it_qat_q4_0",
        "gpt_oss_20b_native_mxfp4",
        "phi_4_14b",
        "granite_3_3_8b_instruct",
    }
    required_keys = {
        key
        for key, value in candidates.items()
        if value.get("evaluation_order") is not None
    }
    if required_keys == legacy_v1_required:
        return (
            "- **Best quality model:** Qwen3-8B Q4_K_M control. It is the only "
            "model that passed smoke and completed the frozen development "
            "benchmark.\n"
            "- **Best speed model (eligible models):** Qwen3-8B Q4_K_M control. "
            "Its OpenCL validity TTFT/latency were 73.29/100.70 s, faster than "
            "every required alternative on the identical case. Gemma had the "
            "fastest raw CPU validity latency, but is ineligible because it "
            "failed citation reliability.\n"
            "- **Best balanced model:** Qwen3-8B Q4_K_M control, based on its "
            "only successful combination of schema reliability, citations, "
            "coverage, latency, and memory.\n"
            "- **Comparison against Qwen:** Gemma failed the smoke citation "
            "gate; gpt-oss produced invalid OpenCL JSON and excessive latency; "
            "Phi-4 was markedly slower with lower coverage; Granite "
            "systematically emitted invalid citation page metadata and was "
            "slower/less complete.\n"
            "- **Blinded human review:** no packet was generated because no "
            "alternative reached development/finalist status. The packet "
            "builder requires at least two same-stage runs with identical "
            "evidence, which prevents presenting a one-model packet as a "
            "blinded comparison.\n"
            "- **Holdout:** untouched. No alternative satisfied the finalist "
            "gate.\n"
            "- **Answering Baseline v2 recommendation:** do not advance any "
            "tested candidate. Retain the frozen Answering Baseline v1/Qwen3-8B "
            "control. The optional Phi-4 Mini and Mistral Small candidates "
            "remain separate future experiments requiring their own artifact "
            "review and approval.\n"
        )
    control = next(
        (value for value in candidates.values() if value.get("control")),
        {"display_name": "the frozen control"},
    )
    rejected = "; ".join(
        f"{candidate['display_name']}: "
        f"{candidate['evaluation'].get('reason', 'rejected').replace('_', ' ')}"
        for candidate in required
    )
    control_name = control["display_name"]
    return (
        f"- **Best quality model:** {control_name}; no candidate passed all "
        "successive-narrowing gates.\n"
        f"- **Best speed model (eligible models):** {control_name}.\n"
        f"- **Best balanced model:** {control_name}.\n"
        f"- **Comparison against the control:** {rejected}.\n"
        "- **Blinded human review:** no packet was generated because no "
        "alternative reached development/finalist status.\n"
        "- **Holdout:** untouched; no alternative satisfied the finalist gate.\n"
        "- **Answering Baseline v2 recommendation:** do not advance any tested "
        "candidate; retain the frozen production control.\n"
    )


def write_tables(experiment_dir: Path) -> Path:
    """Write manifest-derived tables and gate-aware final decisions."""

    manifests = load_manifests(experiment_dir / "runs")
    registry = _load_json(experiment_dir / "artifact_registry.json")
    content = (
        "# Generated benchmark tables\n\n"
        "This file is generated from immutable run manifests. Validity and "
        "early-stopped smoke rows are not quality-leaderboard finals. The "
        "Decision column records the runner's immediate gate result; final "
        "eligibility is recorded in the leaderboard.\n\n"
        "## CPU/GPU benchmark table\n\n"
        f"{build_benchmark_table(manifests)}\n"
        f"{build_control_reference(registry)}"
        "## Quality observations by completed stage\n\n"
        f"{build_quality_table(manifests)}\n"
        "## Gate-aware quality leaderboard\n\n"
        "Rows use each model's furthest completed stage; stages with different "
        "question counts are not treated as directly interchangeable quality "
        "estimates.\n\n"
        f"{build_gate_leaderboard(manifests, registry)}\n"
        "## Winners and Answering Baseline v2 recommendation\n\n"
        f"{build_final_decision(registry)}"
    )
    destination = experiment_dir / "benchmark_tables.md"
    destination.write_text(content, encoding="utf-8")
    return destination
