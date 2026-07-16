"""Phase D local cross-encoder bake-off on the retained lossless candidate pool.

Each model is loaded from a pinned local Hugging Face cache revision. Candidate
text comes from the immutable Phase B winner, and the two Phase C-approved
logic variants (model score alone and model-rank + RRF-rank) are evaluated
without using gold labels during scoring or sorting.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .candidate_complementarity import _scopes
from .candidate_compression import _model_cache_status
from .candidate_representation import metric_block
from .experiment_tracking import (
    checkpoint_run, create_run_directory, experiment_paths,
    initialize_experiment, read_jsonl as read_run_log, render_resume,
    sha256_file, utc_now, write_json,
)
from .fusion_reranking import (
    PHASE_B_RUN_ID, RRF_CONSTANT, _peak_memory_mb, _rank_map,
    load_phase_b_rows,
)
from .retrieval import read_jsonl


RANDOM_SEED = 0
LOGIC_VARIANTS = ("reranker_score", "reranker_rank_plus_rrf_rank")
MODEL_CONFIGS = {
    "minilm_l6": {
        "model_name": "cross-encoder/ms-marco-MiniLM-L6-v2",
        "revision": "c5ee24cb16019beea0893ab7796b1df96625c6b8",
        "run_id": "phase_d_d1_minilm_l6_full_pool",
    },
    "bge_v2_m3": {
        "model_name": "BAAI/bge-reranker-v2-m3",
        "revision": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
        "run_id": "phase_d_d3_bge_v2_m3_full_pool",
    },
    "mxbai_base_v1": {
        "model_name": "mixedbread-ai/mxbai-rerank-base-v1",
        "revision": "800f24c113213a187e65bde9db00c15a2bb12738",
        "run_id": "phase_d_d4_mxbai_base_v1_full_pool",
    },
}


@dataclass(frozen=True)
class LoadedModel:
    """A local CrossEncoder plus reproducibility and cold-start measurements."""

    model: Any
    metadata: dict[str, Any]
    cold_load_ms: float
    warmup_ms: float
    model_size_bytes: int
    parameter_count: int


def _answerable_ids(questions: list[dict[str, Any]]) -> set[str]:
    """Return reviewed rows eligible for Hit@K and MRR."""
    return {row["question_id"] for row in questions
            if row.get("gold_pdf_pages") and (row.get("gold_answer_span") or "").strip()}


def _evaluation_scopes(questions: list[dict[str, Any]],
                       answerable: set[str]) -> dict[str, list[str]]:
    """Build canonical, natural, book, dependency, style, and difficulty slices."""
    scopes = _scopes(questions, answerable)
    for difficulty in sorted({row.get("difficulty", "unknown") for row in questions
                              if row["question_id"] in answerable}):
        scopes[f"difficulty:{difficulty}"] = [
            row["question_id"] for row in questions
            if row["question_id"] in answerable
            and row.get("difficulty", "unknown") == difficulty
        ]
    return scopes


def _snapshot_path(cache_dir: Path, model_name: str, revision: str) -> Path:
    """Resolve the Hugging Face cache snapshot for an exact commit."""
    repo_dir = "models--" + model_name.replace("/", "--")
    path = cache_dir / repo_dir / "snapshots" / revision
    if not path.is_dir():
        raise FileNotFoundError(
            f"pinned model snapshot is not cached: {path}; download it before running"
        )
    return path


def _snapshot_size(path: Path) -> int:
    """Sum runtime snapshot files once, excluding cache blobs and lock files."""
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def load_local_cross_encoder(model_name: str, revision: str, cache_dir: Path,
                             device: str, batch_size: int,
                             maximum_length: int = 512) -> LoadedModel:
    """Load a pinned offline CrossEncoder and measure cold start and warmup."""
    snapshot = _snapshot_path(cache_dir, model_name, revision)
    started = time.perf_counter()
    import sentence_transformers
    import torch
    from sentence_transformers import CrossEncoder

    torch.manual_seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    model = CrossEncoder(
        model_name, revision=revision, local_files_only=True,
        cache_folder=str(cache_dir), device=device, max_length=maximum_length,
    )
    cold_load_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    model.predict([["warm up", "warm up"]], batch_size=1,
                  show_progress_bar=False, convert_to_numpy=True)
    warmup_ms = (time.perf_counter() - started) * 1000
    config = getattr(model, "config", None) or getattr(model.model, "config", None)
    resolved = getattr(config, "_commit_hash", None) or revision
    parameters = sum(int(parameter.numel()) for parameter in model.model.parameters())
    metadata = {
        "model_name": model_name,
        "requested_revision": revision,
        "resolved_model_revision": resolved,
        "library": "sentence-transformers",
        "library_version": sentence_transformers.__version__,
        "torch_version": torch.__version__,
        "device": device,
        "batch_size": batch_size,
        "model_cache": str(cache_dir),
        "local_files_only": True,
        "model_max_length_tokens": maximum_length,
        "truncation_policy": "tokenizer longest-first query/passage truncation to maximum length",
        "score_activation": type(model.default_activation_function).__name__,
        "snapshot_path": str(snapshot),
    }
    return LoadedModel(model, metadata, cold_load_ms, warmup_ms,
                       _snapshot_size(snapshot), parameters)


def rank_scored_candidates(candidates: list[dict[str, Any]],
                           scores: list[float], logic: str) -> list[dict[str, Any]]:
    """Order model scores alone or combine model and RRF ranks deterministically."""
    if logic not in LOGIC_VARIANTS:
        raise ValueError(f"unknown reranker logic: {logic}")
    if len(candidates) != len(scores):
        raise ValueError("model score count must equal candidate count")
    by_id = {str(item["candidate_id"]): item for item in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("candidate IDs must be unique")
    model_scores = {str(item["candidate_id"]): float(score)
                    for item, score in zip(candidates, scores)}
    model_ranks = _rank_map(model_scores)
    rrf_scores = {
        key: sum(1.0 / (RRF_CONSTANT + int(rank))
                 for rank in by_id[key].get("source_ranks", {}).values())
        for key in by_id
    }
    rrf_ranks = _rank_map(rrf_scores)
    if logic == "reranker_score":
        final = model_scores
    else:
        final = {key: 1.0 / (RRF_CONSTANT + model_ranks[key])
                 + 1.0 / (RRF_CONSTANT + rrf_ranks[key]) for key in by_id}
    ordered = sorted(by_id, key=lambda key: (-final[key], -model_scores[key], key))
    return [{**by_id[key], "model_score": model_scores[key],
             "phase_d_score": final[key]} for key in ordered]


def _quality_key(metrics: dict[str, Any], logic: str) -> tuple[Any, ...]:
    """Choose model logic by natural quality, overall rank quality, then name."""
    natural = metrics[logic]["slices"]["natural_student"]
    overall = metrics[logic]["overall"]
    return (natural["hit_at_1_count"], natural["hit_at_3_count"],
            natural["hit_at_5_count"], natural["mrr"],
            overall["hit_at_1_count"], overall["mrr"],
            overall["hit_at_3_count"], overall["hit_at_5_count"], logic)


def _metric_summary(rows: dict[str, dict[str, Any]],
                    scopes: dict[str, list[str]]) -> dict[str, Any]:
    """Summarize one logic variant over all required slices."""
    slices = {name: metric_block([rows[qid] for qid in ids])
              for name, ids in scopes.items()}
    return {"overall": slices["all_answerable"], "slices": slices,
            "top_five_miss_question_ids": [
                qid for qid in scopes["all_answerable"]
                if rows[qid]["first_gold_rank"] is None
                or rows[qid]["first_gold_rank"] > 5
            ]}


def stratified_screen_rows(phase_b_rows: list[dict[str, Any]],
                           per_group: int) -> list[dict[str, Any]]:
    """Select rows by book and benchmark slice without consulting gold labels."""
    if per_group < 1:
        raise ValueError("screen rows per group must be positive")
    groups = {
        (book, slice_name): []
        for book in ("biology", "physical_sciences")
        for slice_name in ("canonical", "natural_student")
    }
    for row in phase_b_rows:
        key = (row["book_id"], row.get("benchmark_slice", "canonical"))
        if key in groups and len(groups[key]) < per_group:
            groups[key].append(row)
    if any(len(rows) != per_group for rows in groups.values()):
        raise ValueError("benchmark lacks enough rows for the requested stratified screen")
    selected_ids = {row["question_id"] for rows in groups.values() for row in rows}
    return [row for row in phase_b_rows if row["question_id"] in selected_ids]


def evaluate_model(model: Any, phase_b_rows: list[dict[str, Any]],
                   questions: list[dict[str, Any]], batch_size: int,
                   run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Score every full-pool candidate once and evaluate both retained logics."""
    answerable = _answerable_ids(questions)
    scopes = _evaluation_scopes(questions, answerable)
    question_by_id = {row["question_id"]: row for row in questions}
    logic_rows: dict[str, dict[str, dict[str, Any]]] = {
        logic: {} for logic in LOGIC_VARIANTS
    }
    details = []
    total_candidates = 0
    for index, cached in enumerate(phase_b_rows, 1):
        qid = cached["question_id"]
        candidates = cached["ranked_candidates"]
        pairs = [[cached["question"], item["representation"]] for item in candidates]
        started = time.perf_counter()
        values = model.predict(pairs, batch_size=batch_size,
                               show_progress_bar=False, convert_to_numpy=True)
        scoring_ms = (time.perf_counter() - started) * 1000
        scores = [float(value) for value in np.asarray(values).reshape(-1)]
        rankings = {logic: rank_scored_candidates(candidates, scores, logic)
                    for logic in LOGIC_VARIANTS}
        first_ranks = {}
        for logic, ranking in rankings.items():
            first_gold = next((rank for rank, item in enumerate(ranking, 1)
                               if item.get("matches_accepted_evidence")), None)
            first_ranks[logic] = first_gold
            logic_rows[logic][qid] = {
                "answerable": qid in answerable,
                "first_gold_rank": first_gold,
                "latency_ms": scoring_ms,
                "candidate_count": len(ranking),
            }
        details.append({
            "question_id": qid, "question": cached["question"],
            "book_id": question_by_id[qid]["book_id"],
            "benchmark_slice": question_by_id[qid].get("benchmark_slice", "canonical"),
            "scoring_latency_ms": scoring_ms,
            "candidate_count": len(candidates),
            "first_accepted_evidence_rank": first_ranks,
            "rankings": {logic: [
                {key: item.get(key) for key in (
                    "candidate_id", "unit_type", "source_ranks", "model_score",
                    "phase_d_score", "matches_accepted_evidence", "representation")}
                | {"rank": rank}
                for rank, item in enumerate(ranking, 1)
            ] for logic, ranking in rankings.items()},
        })
        total_candidates += len(candidates)
        if index == 1 or index % 5 == 0 or index == len(phase_b_rows):
            print(f"{run_id}: scored {index}/{len(phase_b_rows)} questions", flush=True)
    metrics = {logic: _metric_summary(rows, scopes)
               for logic, rows in logic_rows.items()}
    elapsed_seconds = sum(row["scoring_latency_ms"] for row in details) / 1000
    metrics["candidate_throughput_per_second"] = (
        total_candidates / elapsed_seconds if elapsed_seconds else None
    )
    return metrics, details


def _comparison_record(root: Path, run_id: str) -> dict[str, Any]:
    """Read one immutable experiment record by ID."""
    records = read_run_log(experiment_paths(root)["runs"])
    return next(record for record in records if record["run_id"] == run_id)


def _decision(metrics: dict[str, Any], selected_logic: str,
              root: Path) -> tuple[str, str]:
    """Retain a faster near-quality model; reject one dominated by cached BGE."""
    current = metrics[selected_logic]["slices"]["natural_student"]
    current_overall = metrics[selected_logic]["overall"]
    bge = _comparison_record(root, "phase_c_c1_bge_rank_plus_rrf_rank_full_pool")
    bge_natural = bge["metrics"]["natural_student"]
    bge_overall = bge["metrics"]["overall"]
    bge_p95 = float(bge["latency"]["p95_ms"])
    dominated_quality = (
        current["hit_at_1_count"] <= bge_natural["hit_at_1_count"]
        and current["hit_at_3_count"] <= bge_natural["hit_at_3_count"]
        and current["hit_at_5_count"] <= bge_natural["hit_at_5_count"]
        and current_overall["mrr"] <= bge_overall["mrr"]
    )
    faster = current_overall["p95_latency_ms"] < bge_p95
    if faster and (not dominated_quality or current["hit_at_5_count"] >= bge_natural["hit_at_5_count"] - 1):
        return "retain", "Speed-oriented Pareto candidate versus cached BGE-base quality control."
    if dominated_quality and not faster:
        return "reject", "Dominated by cached BGE-base in both quality and p95 latency."
    return "investigate", "Mixed quality/latency result requires the next successive bake-off comparison."


def _render_report(root: Path, record: dict[str, Any], all_metrics: dict[str, Any],
                   selected_logic: str) -> str:
    """Render MiniLM/BGE/Soft-fusion comparison with full resource metadata."""
    soft = _comparison_record(root, "phase_c_c1_soft_fusion_no_reranker_full_pool")
    bge = _comparison_record(root, "phase_c_c1_bge_rank_plus_rrf_rank_full_pool")
    lines = ["# Phase D — Local reranker bake-off", "",
             "All methods use the lossless 61/61 candidate pool and retained Phase B candidate text. MiniLM was loaded from a pinned offline cache revision.", "",
             "| Method | Hit@1 | Hit@3 | Hit@5 | MRR | Natural Hit@1 | Natural Hit@3 | Natural Hit@5 | p95 latency | Decision |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for label, source in (("Soft-fusion-ranked control", soft),
                          ("BGE-base rank + RRF", bge)):
        overall, natural = source["metrics"]["overall"], source["metrics"]["natural_student"]
        lines.append(f'| {label} | {overall["hit_at_1_count"]}/61 | '
                     f'{overall["hit_at_3_count"]}/61 | {overall["hit_at_5_count"]}/61 | '
                     f'{overall["mrr"]:.3f} | {natural["hit_at_1_count"]}/20 | '
                     f'{natural["hit_at_3_count"]}/20 | {natural["hit_at_5_count"]}/20 | '
                     f'{source["latency"]["p95_ms"]:.1f} ms | {source["decision"]} |')
    selected = all_metrics[selected_logic]
    overall, natural = selected["overall"], selected["slices"]["natural_student"]
    lines.append(f'| MiniLM L6 ({selected_logic}) | {overall["hit_at_1_count"]}/61 | '
                 f'{overall["hit_at_3_count"]}/61 | {overall["hit_at_5_count"]}/61 | '
                 f'{overall["mrr"]:.3f} | {natural["hit_at_1_count"]}/20 | '
                 f'{natural["hit_at_3_count"]}/20 | {natural["hit_at_5_count"]}/20 | '
                 f'{record["latency"]["p95_ms"]:.1f} ms | {record["decision"]} |')
    lines += ["", "## MiniLM resources", "",
              f'- Revision: `{record["model_revisions"]["reranker"]["resolved_model_revision"]}`',
              f'- Parameters: {record["configuration"]["parameter_count"]:,}',
              f'- Runtime snapshot: {record["disk_index_size"]["model_size_bytes"] / (1024 ** 2):.1f} MiB',
              f'- Cold load: {record["latency"]["cold_start_ms"]:.1f} ms; warmup: {record["latency"]["warmup_ms"]:.1f} ms',
              f'- Peak process memory: {record["peak_memory"]["peak_rss_mb"]:.1f} MiB', "",
              "Raw model-score and rank+RRF results, all slices, query latencies, and every candidate score are stored in the immutable run directory.", ""]
    return "\n".join(lines)


def run(root: Path, benchmark_path: Path, model_key: str,
        batch_size: int = 32, device: str = "cpu",
        maximum_length: int = 512,
        screen_per_group: int = 0) -> dict[str, Any]:
    """Run one approved model, checkpoint it, and update the bake-off state."""
    if model_key not in MODEL_CONFIGS:
        raise ValueError(f"unknown approved model key: {model_key}")
    if not benchmark_path.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark_path}")
    if benchmark_path.name.endswith("_candidates.jsonl"):
        raise ValueError("use the reviewed benchmark, never the candidates file")
    config = MODEL_CONFIGS[model_key]
    run_id = (f'{config["run_id"]}_screen_{screen_per_group * 4}'
              if screen_per_group else config["run_id"])
    history = {record["run_id"]: record
               for record in read_run_log(experiment_paths(root)["runs"])}
    if run_id in history:
        record = history[run_id]
        return {"run_id": run_id, "decision": record["decision"],
                "selected_logic": record["configuration"]["selected_logic"],
                "metrics": record["metrics"]}
    initialize_experiment(root, [], [run_id], _model_cache_status(root))
    all_questions = read_jsonl(benchmark_path)
    phase_b_rows = load_phase_b_rows(root)
    if screen_per_group:
        phase_b_rows = stratified_screen_rows(phase_b_rows, screen_per_group)
        selected_ids = {row["question_id"] for row in phase_b_rows}
        questions = [row for row in all_questions if row["question_id"] in selected_ids]
    else:
        questions = all_questions
    cache_dir = root / "data" / "retrieval" / "cache" / "models"
    loaded = load_local_cross_encoder(
        config["model_name"], config["revision"], cache_dir,
        device, batch_size, maximum_length,
    )
    metrics, details = evaluate_model(loaded.model, phase_b_rows, questions,
                                      batch_size, run_id)
    selected_logic = max(LOGIC_VARIANTS,
                         key=lambda logic: _quality_key(metrics, logic))
    selected = metrics[selected_logic]
    if screen_per_group:
        decision = "investigate"
        reason = "Stratified latency/quality screen; full-set decision is intentionally deferred."
    else:
        decision, reason = _decision(metrics, selected_logic, root)
    run_dir = create_run_directory(root, run_id)
    details_path = run_dir / "ranked_candidates.jsonl"
    with details_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in details:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    metrics_payload = {
        "run_metadata": {"run_id": run_id, "phase": "D",
                         "candidate_pool_recall": "61/61",
                         "candidate_representation": PHASE_B_RUN_ID,
                         "selection_uses_gold": False,
                         "model": loaded.metadata,
                         "selected_logic": selected_logic},
        "logic_variants": metrics,
        "selected": selected,
    }
    metrics_path = run_dir / "metrics.json"
    config_path = run_dir / "configuration.json"
    write_json(metrics_path, metrics_payload)
    write_json(config_path, {**config, "batch_size": batch_size,
                             "device": device, "maximum_length": maximum_length,
                             "selected_logic": selected_logic})
    overall = selected["overall"]
    natural = selected["slices"]["natural_student"]
    phase_b_path = (root / "reports" / "experiments" / "runs" /
                    PHASE_B_RUN_ID / "ranked_candidates.jsonl")
    record = {
        "run_id": run_id, "timestamp": utc_now(), "phase": "D",
        "parent_run_id": "phase_c_c1_bge_rank_plus_rrf_rank_full_pool",
        "changed_variable": "local cross-encoder model",
        "configuration": {"pipeline_name": (f"{model_key}_{selected_logic}"
                                              + (f"_screen_{screen_per_group * 4}"
                                                 if screen_per_group else "")),
                          "model_key": model_key, "selected_logic": selected_logic,
                          "batch_size": batch_size, "maximum_length": maximum_length,
                          "candidate_pool": "full_lossless_union",
                          "candidate_representation": PHASE_B_RUN_ID,
                          "screen_per_book_slice_group": screen_per_group,
                          "parameter_count": loaded.parameter_count},
        "random_seed": RANDOM_SEED,
        "input_artifact_versions": {
            "benchmark_sha256": sha256_file(benchmark_path),
            "phase_b_rankings_sha256": sha256_file(phase_b_path),
        },
        "model_revisions": {"reranker": loaded.metadata},
        "metrics": {"overall": overall,
                    "canonical": selected["slices"]["canonical"],
                    "natural_student": natural},
        "latency": {"measurement": "warm full-pool local cross-encoder scoring; representation already cached",
                    "average_ms": overall["average_latency_ms"],
                    "p50_ms": overall["p50_latency_ms"],
                    "p95_ms": overall["p95_latency_ms"],
                    "maximum_ms": overall["maximum_latency_ms"],
                    "cold_start_ms": loaded.cold_load_ms,
                    "warmup_ms": loaded.warmup_ms},
        "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                        "measurement": "process peak working set after scoring"},
        "disk_index_size": {"run_artifacts_bytes": sum(
            item.stat().st_size for item in run_dir.rglob("*") if item.is_file()),
            "model_size_bytes": loaded.model_size_bytes,
            "new_index_bytes": 0},
        "candidate_recall": {"answerable_questions": overall["answerable_questions"],
                             "count": overall["answerable_questions"],
                             "recall": 1.0, "required_invariant_satisfied": True},
        "decision": decision, "concise_reason": reason,
        "output_artifact_paths": [str(details_path.relative_to(root)),
                                  str(metrics_path.relative_to(root)),
                                  str(config_path.relative_to(root))],
        "reproduce_command": ("temp\\python-x64\\python.exe scripts\\run_reranker_bakeoff.py "
                              f"--model {model_key} --device {device} --batch-size {batch_size}"
                              + (f" --screen-per-group {screen_per_group}"
                                 if screen_per_group else "")),
        "runtime_versions": {"python": platform.python_version(),
                             "numpy": np.__version__, "platform": platform.platform(),
                             "device": device},
    }
    next_action = ("Review the BGE-v2-m3 stratified screen and run the full set only if quality justifies its CPU cost."
                   if screen_per_group else
                   "Compare the completed reranker with the retained Phase D Pareto frontier.")
    checkpoint_run(root, record, next_action)
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["model_cache_status"][model_key] = {
        "status": "cached", "revision": config["revision"],
        "path": loaded.metadata["snapshot_path"],
    }
    state_key = model_key + (f"_screen_{screen_per_group * 4}" if screen_per_group else "")
    state["current_best_configurations"].setdefault("phase_d", {})[state_key] = {
        "run_id": run_id, "decision": decision, "selected_logic": selected_logic,
        "metrics": record["metrics"],
    }
    state["exact_next_action"] = next_action
    write_json(state_path, state)
    render_resume(root, state)
    report_path = root / "reports" / "experiments" / (
        f"phase_d_{model_key}_screen.md" if screen_per_group
        else "phase_d_reranker_bakeoff.md"
    )
    if screen_per_group:
        report_path.write_text(
            "# Phase D stratified reranker screen\n\n"
            f"Model: `{config['model_name']}` at `{config['revision']}`. "
            f"The screen uses {screen_per_group} query(ies) from each book × benchmark-slice group "
            "and does not select queries with gold labels.\n\n"
            f"Selected logic: `{selected_logic}`; answerable rows: {overall['answerable_questions']}; "
            f"Hit@1/3/5: {overall['hit_at_1_count']}/{overall['hit_at_3_count']}/{overall['hit_at_5_count']}; "
            f"MRR: {overall['mrr']:.3f}; p95 latency: {overall['p95_latency_ms']:.1f} ms; "
            f"peak memory: {record['peak_memory']['peak_rss_mb']:.1f} MiB.\n",
            encoding="utf-8",
        )
    else:
        report_path.write_text(_render_report(root, record, metrics, selected_logic), encoding="utf-8")
    return {"run_id": run_id, "decision": decision,
            "selected_logic": selected_logic, "metrics": record["metrics"],
            "report": str(report_path.relative_to(root))}


def record_stopped_screen(root: Path, benchmark_path: Path, model_key: str,
                          screen_per_group: int, minimum_elapsed_ms: float,
                          observed_peak_mb: float) -> dict[str, Any]:
    """Checkpoint a runtime-infeasible screen that produced no completed query."""
    if model_key not in MODEL_CONFIGS or screen_per_group < 1:
        raise ValueError("a known model and positive screen size are required")
    config = MODEL_CONFIGS[model_key]
    run_id = f'{config["run_id"]}_screen_{screen_per_group * 4}'
    history = {record["run_id"]: record
               for record in read_run_log(experiment_paths(root)["runs"])}
    if run_id in history:
        return history[run_id]
    run_dir = create_run_directory(root, run_id)
    empty_metrics = {
        "answerable_questions": 0, "hit_at_1_count": 0, "hit_at_1": 0.0,
        "hit_at_3_count": 0, "hit_at_3": 0.0,
        "hit_at_5_count": 0, "hit_at_5": 0.0, "mrr": 0.0,
        "average_latency_ms": None, "p50_latency_ms": None,
        "p95_latency_ms": None, "maximum_latency_ms": None,
    }
    payload = {
        "run_metadata": {"run_id": run_id, "phase": "D", "status": "stopped",
                         "stop_reason": "runtime infeasible before first full-pool query completed",
                         "selection_uses_gold": False},
        "model": {"model_name": config["model_name"],
                  "requested_revision": config["revision"],
                  "resolved_model_revision": config["revision"],
                  "device": "cpu", "local_files_only": True,
                  "model_max_length_tokens": 512, "batch_size": 32},
        "screen": {"queries_planned": screen_per_group * 4,
                   "queries_completed": 0,
                   "minimum_elapsed_before_stop_ms": minimum_elapsed_ms,
                   "quality_metrics_available": False},
        "overall": empty_metrics,
    }
    metrics_path = run_dir / "metrics.json"
    config_path = run_dir / "configuration.json"
    write_json(metrics_path, payload)
    write_json(config_path, {**config, "screen_per_book_slice_group": screen_per_group,
                             "batch_size": 32, "maximum_length": 512,
                             "status": "stopped_runtime_infeasible"})
    record = {
        "run_id": run_id, "timestamp": utc_now(), "phase": "D",
        "parent_run_id": "phase_d_d1_minilm_l6_full_pool",
        "changed_variable": "local cross-encoder model runtime feasibility",
        "configuration": {"pipeline_name": f"{model_key}_screen_{screen_per_group * 4}_stopped",
                          "model_key": model_key, "candidate_pool": "full_lossless_union",
                          "screen_per_book_slice_group": screen_per_group,
                          "status": "stopped_runtime_infeasible"},
        "random_seed": RANDOM_SEED,
        "input_artifact_versions": {"benchmark_sha256": sha256_file(benchmark_path)},
        "model_revisions": {"reranker": payload["model"]},
        "metrics": {"overall": empty_metrics, "canonical": empty_metrics,
                    "natural_student": empty_metrics},
        "latency": {"measurement": "minimum observed wall time before forced stop; no query completed",
                    "average_ms": None, "p50_ms": None, "p95_ms": None,
                    "maximum_ms": None,
                    "minimum_elapsed_before_stop_ms": minimum_elapsed_ms},
        "peak_memory": {"peak_rss_mb": observed_peak_mb,
                        "measurement": "observed live working set before forced stop"},
        "disk_index_size": {"run_artifacts_bytes": sum(
            item.stat().st_size for item in run_dir.rglob("*") if item.is_file()),
            "model_size_bytes": _snapshot_size(_snapshot_path(
                root / "data" / "retrieval" / "cache" / "models",
                config["model_name"], config["revision"])),
            "new_index_bytes": 0},
        "candidate_recall": {"answerable_questions": 0, "count": 0,
                             "recall": None, "required_invariant_satisfied": True,
                             "note": "full pools were configured but no query completed"},
        "decision": "reject",
        "concise_reason": "Runtime infeasible: no full-pool query completed after more than five minutes.",
        "output_artifact_paths": [str(metrics_path.relative_to(root)),
                                  str(config_path.relative_to(root))],
        "reproduce_command": ("temp\\python-x64\\python.exe scripts\\run_reranker_bakeoff.py "
                              f"--model {model_key} --device cpu --batch-size 32 "
                              f"--maximum-length 512 --screen-per-group {screen_per_group}"),
        "runtime_versions": {"python": platform.python_version(),
                             "numpy": np.__version__, "platform": platform.platform(),
                             "device": "cpu"},
    }
    next_action = "Finalize Phase D with MiniLM as the retained speed reranker and no larger full run."
    checkpoint_run(root, record, next_action)
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if run_id not in state["failed_or_blocked_runs"]:
        state["failed_or_blocked_runs"].append(run_id)
    state["model_cache_status"][model_key] = {
        "status": "cached", "revision": config["revision"],
        "path": str(_snapshot_path(root / "data" / "retrieval" / "cache" / "models",
                                   config["model_name"], config["revision"])),
    }
    state["current_best_configurations"].setdefault("phase_d", {})[
        f"{model_key}_screen_{screen_per_group * 4}"
    ] = {"run_id": run_id, "decision": "reject",
         "status": "stopped_runtime_infeasible",
         "minimum_elapsed_before_stop_ms": minimum_elapsed_ms}
    state["exact_next_action"] = next_action
    write_json(state_path, state)
    render_resume(root, state)
    return record


def finalize_phase_d(root: Path) -> dict[str, Any]:
    """Select the Phase D Pareto model, record stopping decisions, and enter E."""
    paths = experiment_paths(root)
    state = json.loads(paths["state"].read_text(encoding="utf-8"))
    phase_d = state["current_best_configurations"].setdefault("phase_d", {})
    phase_d["selection"] = {
        "speed_oriented_reranker": "phase_d_d1_minilm_l6_full_pool",
        "quality_oriented_reranker": "phase_d_d1_minilm_l6_full_pool",
        "selected_logic": "reranker_rank_plus_rrf_rank",
        "reason": "MiniLM improves natural/top-5 quality over BGE-base at about one-sixth the p95 latency; larger models failed successive screens.",
    }
    for name in ("bge_v2_m3_full_run", "mxbai_base_v1_full_run"):
        if name not in state["rejected_configurations"]:
            state["rejected_configurations"].append(name)
    state["current_phase"] = "Phase E — Embedding model bake-off"
    state["exact_next_action"] = (
        "Inspect and acquire the approved BGE-M3 embedding revision, then run dense retrieval first."
    )
    state["unresolved_questions"] = [
        "Can BGE-M3 or another approved embedding improve natural-student first-stage retrieval?",
        "Can a stronger embedding reduce dependence on expensive full-pool reranking?",
    ]
    write_json(paths["state"], state)
    render_resume(root, state)
    heading = "## Phase D final selection — MiniLM L6"
    decisions = paths["decisions"].read_text(encoding="utf-8")
    if heading not in decisions:
        with paths["decisions"].open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                f"{heading}\n\n"
                "- Decision: **retain MiniLM L6** as both speed- and practical quality-oriented reranker; keep Soft-fusion-ranked retrieval as the balanced no-reranker path.\n"
                "- Evidence: MiniLM natural Hit@1/3/5 is 6/13/16 of 20 at 8.1 s p95; BGE-base is 5/12/15 at 47.0 s p95. BGE-v2 natural Hit@5 was 1/4 at 154.4 s screen p95; mxbai completed no query after >300 s.\n"
                "- Next: Begin Phase E with BGE-M3 dense retrieval, then narrow before sparse/multi-vector variants.\n\n"
            )
    report_path = root / "reports" / "experiments" / "phase_d_reranker_bakeoff.md"
    report = report_path.read_text(encoding="utf-8")
    if "## Successive-stopping screens" not in report:
        report += (
            "\n## Successive-stopping screens\n\n"
            "| Model | Screen | Natural Hit@5 | Avg latency | p95 latency | Peak memory | Decision |\n"
            "|---|---:|---:|---:|---:|---:|---|\n"
            "| BGE-reranker-v2-m3 | 8 balanced queries | 1/4 | 115.1 s | 154.4 s | 2,816.9 MiB | Reject full run |\n"
            "| mxbai-rerank-base-v1 | planned 8 | unavailable | >300 s before first query | unavailable | 1,121.1 MiB observed | Stop and reject |\n\n"
            "## Final Phase D decision\n\n"
            "Retain MiniLM L6 with rank+RRF as the only cross-encoder on the Phase D Pareto frontier. It is both faster and stronger on natural/top-5 retrieval than cached BGE-base. Larger models are infeasible or unpromising on this CPU. The Soft-fusion-ranked deduplicated union remains the preferred balanced path when 5–8 seconds of reranking latency is unacceptable.\n"
        )
        report_path.write_text(report, encoding="utf-8")
    return {"current_phase": state["current_phase"],
            "selected_reranker": "phase_d_d1_minilm_l6_full_pool",
            "next_action": state["exact_next_action"]}


def build_parser() -> argparse.ArgumentParser:
    """Expose pinned local model, device, batch, and sequence-length controls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--model", choices=tuple(MODEL_CONFIGS), default="minilm_l6")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--maximum-length", type=int, default=512)
    parser.add_argument("--screen-per-group", type=int, default=0,
                        help="run a gold-blind book × slice screen instead of all 66 rows")
    parser.add_argument("--record-stopped", action="store_true",
                        help="checkpoint a runtime-infeasible screen that completed no query")
    parser.add_argument("--finalize", action="store_true",
                        help="apply Phase D stopping decisions and advance to Phase E")
    parser.add_argument("--minimum-elapsed-ms", type=float, default=300000.0)
    parser.add_argument("--observed-peak-mb", type=float, default=0.0)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Resolve defaults, run one Phase D model, and print compact results."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    benchmark = (args.benchmark or root / "data" / "benchmarks" /
                 "retrieval_benchmark_v1.jsonl").resolve()
    if args.finalize:
        result = finalize_phase_d(root)
    elif args.record_stopped:
        result = record_stopped_screen(
            root, benchmark, args.model, args.screen_per_group,
            args.minimum_elapsed_ms, args.observed_peak_mb,
        )
    else:
        result = run(root, benchmark, args.model, args.batch_size,
                     args.device, args.maximum_length,
                     args.screen_per_group)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
