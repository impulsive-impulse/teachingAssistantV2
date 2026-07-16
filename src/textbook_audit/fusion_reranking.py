"""Phase C fusion and reranking logic over cached, lossless Phase B pools.

The module deliberately separates two questions:

* Which retrieval/reranker score fusion orders the complete 61/61 candidate
  pool best?
* Can a gold-blind 8/10/15-candidate preselector preserve that evidence before
  a slower cross-encoder runs?

Gold flags are read only after each deterministic ordering has been produced.
The full-pool methods reuse the measured Phase B cross-encoder scores; they do
not call a model or overwrite any earlier experiment artifact.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .candidate_complementarity import _scopes
from .candidate_compression import _model_cache_status
from .candidate_representation import metric_block
from .experiment_tracking import (
    checkpoint_run, create_run_directory, experiment_paths,
    initialize_experiment, read_jsonl as read_run_log, render_resume,
    sha256_file, utc_now, write_json,
)
from .retrieval import BM25, read_jsonl, stable_ranking
from .reranker import RRF_CONSTANT, SOURCE_RETRIEVERS


RANDOM_SEED = 0
BUDGETS = (8, 10, 15)
SOFT_SOURCE = "soft_fusion_hybrid"
PHASE_B_RUN_ID = (
    "phase_b_b4_rerank_combination_dense_best_member_"
    "two_relevant_windows_neighbor_expansion"
)
WEIGHTS = {
    "page_dense_bge_small": 1.0,
    "fixed_400_80_bm25": 1.0,
    "fixed_400_80_dense_bge_small": 0.75,
    "soft_fusion_hybrid": 1.25,
}

FULL_POOL_METHODS = (
    "soft_fusion_no_reranker",
    "plain_rrf",
    "weighted_rrf",
    "bge_reranker_score",
    "bge_rank_plus_rrf_rank",
    "bge_score_plus_normalized_rrf",
    "bge_rank_plus_soft_fusion_rank",
)
PRESELECTORS = ("rrf_preselector", "bm25_fast_reranker")


@dataclass(frozen=True)
class Evaluation:
    """One fully computed run awaiting an immutable experiment checkpoint."""

    run_id: str
    configuration: dict[str, Any]
    rows: dict[str, dict[str, Any]]
    details: list[dict[str, Any]]
    metrics: dict[str, Any]
    candidate_recall: dict[str, Any]
    uses_cross_encoder: bool
    measured_logic_latencies: tuple[float, ...]


def _minmax(values: dict[str, float]) -> dict[str, float]:
    """Normalize one query's scores to [0, 1] without unstable division."""
    if not values:
        return {}
    low, high = min(values.values()), max(values.values())
    if math.isclose(low, high):
        return {key: 0.0 for key in values}
    return {key: (value - low) / (high - low) for key, value in values.items()}


def _peak_memory_mb() -> float:
    """Read the current process peak working set without loading a model."""
    try:
        import psutil
        memory = psutil.Process().memory_info()
        return float(getattr(memory, "peak_wset", memory.rss)) / (1024 * 1024)
    except (ImportError, OSError):
        return 0.0


def _rank_map(scores: dict[str, float]) -> dict[str, int]:
    """Convert scores into deterministic one-based ranks using ID tie-breaks."""
    ordered = sorted(scores, key=lambda key: (-scores[key], key))
    return {key: index for index, key in enumerate(ordered, 1)}


def _rrf_score(candidate: dict[str, Any], *, weighted: bool = False) -> float:
    """Fuse the four native source ranks, optionally using Phase A weights."""
    ranks = candidate.get("source_ranks", {})
    return sum(
        (WEIGHTS.get(source, 1.0) if weighted else 1.0)
        / (RRF_CONSTANT + int(rank))
        for source, rank in ranks.items()
    )


def rank_full_pool(candidates: list[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    """Order a complete candidate pool with one preregistered gold-blind rule."""
    if method not in FULL_POOL_METHODS:
        raise ValueError(f"unknown full-pool fusion method: {method}")
    by_id = {str(item["candidate_id"]): item for item in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("candidate IDs must be unique inside one query pool")
    ids = list(by_id)
    cross_scores = {key: float(by_id[key]["score"]) for key in ids}
    cross_ranks = _rank_map(cross_scores)
    rrf_scores = {key: _rrf_score(by_id[key]) for key in ids}
    weighted_scores = {key: _rrf_score(by_id[key], weighted=True) for key in ids}
    rrf_ranks = _rank_map(rrf_scores)
    soft_ranks = {
        key: int(by_id[key].get("source_ranks", {}).get(SOFT_SOURCE, 10_000))
        for key in ids
    }

    if method == "soft_fusion_no_reranker":
        scores = {
            key: ((1.0 / (RRF_CONSTANT + soft_ranks[key]))
                  if soft_ranks[key] < 10_000 else 0.0)
            for key in ids
        }
    elif method == "plain_rrf":
        scores = rrf_scores
    elif method == "weighted_rrf":
        scores = weighted_scores
    elif method == "bge_reranker_score":
        scores = cross_scores
    elif method == "bge_rank_plus_rrf_rank":
        scores = {key: 1.0 / (RRF_CONSTANT + cross_ranks[key])
                  + 1.0 / (RRF_CONSTANT + rrf_ranks[key]) for key in ids}
    elif method == "bge_score_plus_normalized_rrf":
        normalized_cross = _minmax(cross_scores)
        normalized_rrf = _minmax(rrf_scores)
        scores = {key: 0.5 * normalized_cross[key] + 0.5 * normalized_rrf[key]
                  for key in ids}
    else:
        scores = {
            key: 1.0 / (RRF_CONSTANT + cross_ranks[key])
            + ((1.0 / (RRF_CONSTANT + soft_ranks[key]))
               if soft_ranks[key] < 10_000 else 0.0)
            for key in ids
        }

    # Retrieval-only controls use RRF as a secondary key for candidates absent
    # from the controlling source; reranker methods retain cross score next.
    reranker_method = method.startswith("bge_")
    ordered_ids = sorted(
        ids,
        key=lambda key: (
            -scores[key],
            -(cross_scores[key] if reranker_method else rrf_scores[key]),
            key,
        ),
    )
    return [{**by_id[key], "phase_c_score": scores[key]}
            for key in ordered_ids]


def preselect(candidates: list[dict[str, Any]], question: str,
              selector: str, budget: int) -> list[dict[str, Any]]:
    """Select a capped pool with RRF or a local BM25 fast-reranker signal."""
    if budget not in BUDGETS:
        raise ValueError(f"candidate budget must be one of {BUDGETS}")
    if selector == "rrf_preselector":
        ordered = rank_full_pool(candidates, "plain_rrf")
    elif selector == "bm25_fast_reranker":
        scores = BM25(item["representation"] for item in candidates).scores(question)
        order = stable_ranking(scores)
        ordered = [{**candidates[int(index)], "phase_c_score": float(scores[int(index)])}
                   for index in order]
    else:
        raise ValueError(f"unknown preselector: {selector}")
    return ordered[:budget]


def _answerable_ids(questions: list[dict[str, Any]]) -> set[str]:
    """Identify rows eligible for retrieval metrics using reviewed fields."""
    return {
        row["question_id"] for row in questions
        if row.get("gold_pdf_pages") and (row.get("gold_answer_span") or "").strip()
    }


def _evaluation_scopes(questions: list[dict[str, Any]],
                       answerable_ids: set[str]) -> dict[str, list[str]]:
    """Reuse required slices and add benchmark-defined difficulty groups."""
    scopes = _scopes(questions, answerable_ids)
    for difficulty in sorted({row.get("difficulty", "unknown") for row in questions
                              if row["question_id"] in answerable_ids}):
        scopes[f"difficulty:{difficulty}"] = [
            row["question_id"] for row in questions
            if row["question_id"] in answerable_ids
            and row.get("difficulty", "unknown") == difficulty
        ]
    return scopes


def load_phase_b_rows(root: Path, run_id: str = PHASE_B_RUN_ID) -> list[dict[str, Any]]:
    """Load and validate the cached 66-query full-pool cross-encoder ranking."""
    path = root / "reports" / "experiments" / "runs" / run_id / "ranked_candidates.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"required Phase B cached ranking is missing: {path}")
    rows = read_jsonl(path)
    ids = [row["question_id"] for row in rows]
    if len(rows) != 66 or len(set(ids)) != len(ids):
        raise ValueError("Phase B cached ranking must contain 66 unique question rows")
    if any(not row.get("ranked_candidates") for row in rows):
        raise ValueError("Phase B cached ranking contains an empty candidate pool")
    return rows


def _summarize(rows: dict[str, dict[str, Any]], scopes: dict[str, list[str]]) -> dict[str, Any]:
    """Compute overall and every required slice from first accepted ranks."""
    slices = {name: metric_block([rows[qid] for qid in ids])
              for name, ids in scopes.items()}
    return {"overall": slices["all_answerable"], "slices": slices}


def evaluate_full_method(method: str, phase_b_rows: list[dict[str, Any]],
                         questions: list[dict[str, Any]]) -> Evaluation:
    """Evaluate one full-pool fusion method with honest inherited latency."""
    answerable = _answerable_ids(questions)
    scopes = _evaluation_scopes(questions, answerable)
    by_question = {row["question_id"]: row for row in questions}
    rows: dict[str, dict[str, Any]] = {}
    details = []
    logic_latencies = []
    uses_cross_encoder = method.startswith("bge_")
    for cached in phase_b_rows:
        qid = cached["question_id"]
        started = time.perf_counter()
        ranked = rank_full_pool(cached["ranked_candidates"], method)
        logic_ms = (time.perf_counter() - started) * 1000
        logic_latencies.append(logic_ms)
        first_gold = next((rank for rank, item in enumerate(ranked, 1)
                           if item.get("matches_accepted_evidence")), None)
        deployment_ms = logic_ms + (float(cached["latency_ms"])
                                    if uses_cross_encoder else 0.0)
        rows[qid] = {"answerable": qid in answerable,
                     "first_gold_rank": first_gold,
                     "latency_ms": deployment_ms,
                     "candidate_count": len(ranked)}
        details.append({
            "question_id": qid,
            "question": by_question[qid]["question"],
            "book_id": by_question[qid]["book_id"],
            "benchmark_slice": by_question[qid].get("benchmark_slice", "canonical"),
            "method": method,
            "candidate_pool_recall_preserved": True,
            "first_accepted_evidence_rank": first_gold,
            "logic_latency_ms": logic_ms,
            "inherited_cross_encoder_latency_ms": (
                float(cached["latency_ms"]) if uses_cross_encoder else 0.0),
            "ranked_candidates": [
                {key: item.get(key) for key in (
                    "rank", "candidate_id", "unit_type", "source_ranks", "score",
                    "phase_c_score", "matches_accepted_evidence", "representation")}
                | {"rank": rank}
                for rank, item in enumerate(ranked, 1)
            ],
        })
    summary = _summarize(rows, scopes)
    metrics = {
        "run_metadata": {"phase": "C", "method": method,
                         "candidate_pool": PHASE_B_RUN_ID,
                         "candidate_pool_recall": "61/61",
                         "selection_uses_gold": False,
                         "cached_cross_encoder_scores": uses_cross_encoder},
        **summary,
        "top_five_miss_question_ids": [
            qid for qid in scopes["all_answerable"]
            if rows[qid]["first_gold_rank"] is None or rows[qid]["first_gold_rank"] > 5
        ],
    }
    return Evaluation(
        run_id=f"phase_c_c1_{method}_full_pool",
        configuration={"pipeline_name": method, "fusion_method": method,
                       "candidate_budget": "full", "rrf_constant": RRF_CONSTANT,
                       "source_weights": WEIGHTS if method == "weighted_rrf" else {},
                       "score_blend_alpha": 0.5 if method == "bge_score_plus_normalized_rrf" else None},
        rows=rows, details=details, metrics=metrics,
        candidate_recall={"answerable_questions": 61, "count": 61, "recall": 1.0,
                          "required_invariant_satisfied": True},
        uses_cross_encoder=uses_cross_encoder,
        measured_logic_latencies=tuple(logic_latencies),
    )


def evaluate_preselector(selector: str, budget: int,
                         phase_b_rows: list[dict[str, Any]],
                         questions: list[dict[str, Any]]) -> Evaluation:
    """Audit evidence preservation before allowing a capped/two-stage reranker."""
    answerable = _answerable_ids(questions)
    scopes = _evaluation_scopes(questions, answerable)
    by_question = {row["question_id"]: row for row in questions}
    rows: dict[str, dict[str, Any]] = {}
    details = []
    latencies = []
    retained_ids = []
    for cached in phase_b_rows:
        qid = cached["question_id"]
        started = time.perf_counter()
        selected = preselect(cached["ranked_candidates"], cached["question"], selector, budget)
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        first_gold = next((rank for rank, item in enumerate(selected, 1)
                           if item.get("matches_accepted_evidence")), None)
        if qid in answerable and first_gold is not None:
            retained_ids.append(qid)
        rows[qid] = {"answerable": qid in answerable,
                     "first_gold_rank": first_gold,
                     "latency_ms": latency_ms,
                     "candidate_count": len(selected)}
        details.append({
            "question_id": qid, "question": by_question[qid]["question"],
            "book_id": by_question[qid]["book_id"],
            "benchmark_slice": by_question[qid].get("benchmark_slice", "canonical"),
            "preselector": selector, "candidate_budget": budget,
            "accepted_evidence_retained_before_reranking": first_gold is not None,
            "first_accepted_evidence_rank": first_gold,
            "preselection_latency_ms": latency_ms,
            "stronger_reranker_executed": False,
            "selected_candidates": [
                {key: item.get(key) for key in (
                    "candidate_id", "unit_type", "source_ranks", "score",
                    "phase_c_score", "matches_accepted_evidence", "representation")}
                | {"rank": rank}
                for rank, item in enumerate(selected, 1)
            ],
        })
    count = len(retained_ids)
    recall = {"answerable_questions": 61, "count": count, "recall": count / 61,
              "required_invariant_satisfied": count == 61,
              "missing_question_ids": [qid for qid in scopes["all_answerable"]
                                       if qid not in retained_ids]}
    summary = _summarize(rows, scopes)
    metrics = {
        "run_metadata": {"phase": "C", "preselector": selector,
                         "candidate_budget": budget, "selection_uses_gold": False,
                         "stronger_reranker_executed": False,
                         "stop_reason": "pre-rerank evidence loss" if count < 61 else None},
        **summary, "candidate_recall_before_reranking": recall,
    }
    label = f"{selector}_budget_{budget}"
    return Evaluation(
        run_id=f"phase_c_c2_{label}",
        configuration={"pipeline_name": label, "preselector": selector,
                       "candidate_budget": budget,
                       "stronger_reranker": "BAAI/bge-reranker-base",
                       "stop_before_stronger_reranker_on_recall_loss": True},
        rows=rows, details=details, metrics=metrics, candidate_recall=recall,
        uses_cross_encoder=False, measured_logic_latencies=tuple(latencies),
    )


def _quality_key(evaluation: Evaluation) -> tuple[Any, ...]:
    """Prioritize natural-student ranks, then overall ranks and CPU latency."""
    natural = evaluation.metrics["slices"]["natural_student"]
    overall = evaluation.metrics["overall"]
    return (natural["hit_at_1_count"], natural["hit_at_3_count"],
            natural["hit_at_5_count"], natural["mrr"],
            overall["hit_at_1_count"], overall["mrr"],
            overall["hit_at_3_count"], overall["hit_at_5_count"],
            -overall["p95_latency_ms"])


def _pareto_retained(evaluations: list[Evaluation]) -> set[str]:
    """Retain best quality, best natural Hit@5/MRR, and fastest useful control."""
    quality = max(evaluations, key=_quality_key)
    natural = max(evaluations, key=lambda item: (
        item.metrics["slices"]["natural_student"]["hit_at_5_count"],
        item.metrics["slices"]["natural_student"]["mrr"],
        item.metrics["overall"]["mrr"],
    ))
    retrieval_only = [item for item in evaluations if not item.uses_cross_encoder]
    lightweight = max(retrieval_only, key=_quality_key)
    return {quality.run_id, natural.run_id, lightweight.run_id}


def _write_evaluation(root: Path, benchmark_path: Path, phase_b_path: Path,
                      evaluation: Evaluation, decision: str, reason: str,
                      next_action: str, parent_metadata: dict[str, Any],
                      parent_peak_mb: float) -> dict[str, Any]:
    """Persist one computed evaluation and checkpoint its immutable run record."""
    run_dir = create_run_directory(root, evaluation.run_id)
    details_name = "ranked_candidates.jsonl" if "c1" in evaluation.run_id else "preselected_candidates.jsonl"
    details_path = run_dir / details_name
    with details_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in evaluation.details:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    metrics_path = run_dir / "metrics.json"
    config_path = run_dir / "configuration.json"
    write_json(metrics_path, evaluation.metrics)
    write_json(config_path, evaluation.configuration)
    overall = evaluation.metrics["overall"]
    slices = evaluation.metrics["slices"]
    logic = evaluation.measured_logic_latencies
    deployment_peak = parent_peak_mb if evaluation.uses_cross_encoder else _peak_memory_mb()
    record = {
        "run_id": evaluation.run_id, "timestamp": utc_now(), "phase": "C",
        "parent_run_id": PHASE_B_RUN_ID,
        "changed_variable": ("fusion/reranking logic" if "c1" in evaluation.run_id
                             else "candidate budget and pre-rerank selection logic"),
        "configuration": evaluation.configuration,
        "random_seed": RANDOM_SEED,
        "input_artifact_versions": {
            "benchmark_sha256": sha256_file(benchmark_path),
            "phase_b_rankings_sha256": sha256_file(phase_b_path),
            "phase_b_run_id": PHASE_B_RUN_ID,
        },
        "model_revisions": parent_metadata,
        "metrics": {"overall": overall, "canonical": slices["canonical"],
                    "natural_student": slices["natural_student"]},
        "latency": {
            "measurement": ("measured fusion overhead plus inherited measured Phase B cross-encoder latency"
                            if evaluation.uses_cross_encoder else "measured local ranking/preselection only"),
            "average_ms": overall["average_latency_ms"],
            "p50_ms": overall["p50_latency_ms"],
            "p95_ms": overall["p95_latency_ms"],
            "maximum_ms": overall["maximum_latency_ms"],
            "average_logic_overhead_ms": statistics.fmean(logic) if logic else 0.0,
        },
        "peak_memory": {"peak_rss_mb": deployment_peak,
                        "measurement": ("inherited measured Phase B process peak"
                                        if evaluation.uses_cross_encoder
                                        else "no model loaded; not separately sampled")},
        "disk_index_size": {"run_artifacts_bytes": sum(
            item.stat().st_size for item in run_dir.rglob("*") if item.is_file()),
            "new_index_bytes": 0},
        "candidate_recall": evaluation.candidate_recall,
        "decision": decision, "concise_reason": reason,
        "output_artifact_paths": [str(details_path.relative_to(root)),
                                  str(metrics_path.relative_to(root)),
                                  str(config_path.relative_to(root))],
        "reproduce_command": "temp\\python-x64\\python.exe scripts\\run_fusion_reranking.py --stage all",
        "runtime_versions": {"python": platform.python_version(),
                             "numpy": np.__version__, "platform": platform.platform(),
                             "device": "cpu"},
    }
    checkpoint_run(root, record, next_action)
    return record


def _report(full_records: list[dict[str, Any]], budget_records: list[dict[str, Any]]) -> str:
    """Render the Phase C full-pool comparison and invalid budget gate."""
    lines = [
        "# Phase C — Fusion and reranking logic", "",
        "All full-pool methods preserve 61/61 accepted-evidence candidates. Reranker methods reuse the exact cached Phase B BGE scores; no model inference or gold-dependent ranking occurs in this phase.", "",
        "| Method | Decision | Hit@1 | Hit@3 | Hit@5 | MRR | Natural Hit@1 | Natural Hit@3 | Natural Hit@5 | p95 latency |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for record in full_records:
        overall = record["metrics"]["overall"]
        natural = record["metrics"]["natural_student"]
        lines.append(
            f'| `{record["configuration"]["pipeline_name"]}` | {record["decision"]} | '
            f'{overall["hit_at_1_count"]}/61 | {overall["hit_at_3_count"]}/61 | '
            f'{overall["hit_at_5_count"]}/61 | {overall["mrr"]:.3f} | '
            f'{natural["hit_at_1_count"]}/20 | {natural["hit_at_3_count"]}/20 | '
            f'{natural["hit_at_5_count"]}/20 | {record["latency"]["p95_ms"]:.1f} ms |'
        )
    lines += ["", "## Candidate-budget gate", "",
              "The stronger reranker is not executed when a gold-blind preselector has already dropped accepted evidence.", "",
              "| Preselector | Budget | Candidate recall before reranking | Decision |",
              "|---|---:|---:|---|"]
    for record in budget_records:
        recall = record["candidate_recall"]
        lines.append(f'| `{record["configuration"]["preselector"]}` | '
                     f'{record["configuration"]["candidate_budget"]} | '
                     f'{recall["count"]}/61 ({100 * recall["recall"]:.1f}%) | '
                     f'{record["decision"]} |')
    lines += ["", "## Decision", "",
              "Retain the full-pool quality and lightweight Pareto configurations shown above. Reject every capped path that violates the 61/61 pre-rerank invariant; do not spend cross-encoder time on an invalid pool.", ""]
    return "\n".join(lines)


def run(root: Path, benchmark_path: Path, stage: str = "all") -> dict[str, Any]:
    """Run cached full-pool fusion, capped recall gates, or both in sequence."""
    if stage not in {"logic", "budgets", "all"}:
        raise ValueError("stage must be logic, budgets, or all")
    if not benchmark_path.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark_path}")
    if benchmark_path.name.endswith("_candidates.jsonl"):
        raise ValueError("use the reviewed benchmark, never the candidates file")
    questions = read_jsonl(benchmark_path)
    phase_b_rows = load_phase_b_rows(root)
    phase_b_path = (root / "reports" / "experiments" / "runs" / PHASE_B_RUN_ID /
                    "ranked_candidates.jsonl")
    parent_metrics_path = phase_b_path.with_name("metrics.json")
    parent_metrics = json.loads(parent_metrics_path.read_text(encoding="utf-8"))
    parent_metadata = parent_metrics["run_metadata"].get("reranker", {})
    history = {record["run_id"]: record
               for record in read_run_log(experiment_paths(root)["runs"])}
    if PHASE_B_RUN_ID not in history:
        raise ValueError(f"immutable parent run is absent from experiment history: {PHASE_B_RUN_ID}")
    parent_peak_mb = float(history[PHASE_B_RUN_ID]["peak_memory"]["peak_rss_mb"])
    full_ids = [f"phase_c_c1_{method}_full_pool" for method in FULL_POOL_METHODS]
    budget_ids = [f"phase_c_c2_{selector}_budget_{budget}"
                  for selector in PRESELECTORS for budget in BUDGETS]
    pending = ((full_ids if stage in {"logic", "all"} else [])
               + (budget_ids if stage in {"budgets", "all"} else []))
    # Preserve the known local-cache inventory in the recovery state. Passing
    # an empty mapping here would make a resumed session think approved models
    # need to be downloaded again even though this phase loads no new model.
    initialize_experiment(root, [], pending, _model_cache_status(root))

    full_evaluations = [evaluate_full_method(method, phase_b_rows, questions)
                        for method in FULL_POOL_METHODS]
    retained_ids = _pareto_retained(full_evaluations)
    full_records = []
    for index, evaluation in enumerate(full_evaluations, 1):
        if evaluation.run_id in history:
            full_records.append(history[evaluation.run_id])
            continue
        decision = "retain" if evaluation.run_id in retained_ids else "reject"
        reason = ("Full-pool quality/latency Pareto configuration."
                  if decision == "retain" else
                  "Dominated or not selected under natural-first quality and CPU latency priorities.")
        record = _write_evaluation(
            root, benchmark_path, phase_b_path, evaluation, decision, reason,
            "Run remaining Phase C fusion and candidate-budget gates.", parent_metadata,
            parent_peak_mb,
        )
        full_records.append(record)
        print(f"{evaluation.run_id}: {index}/{len(full_evaluations)} checkpointed", flush=True)

    budget_records = []
    if stage in {"budgets", "all"}:
        for selector in PRESELECTORS:
            for budget in BUDGETS:
                evaluation = evaluate_preselector(selector, budget, phase_b_rows, questions)
                if evaluation.run_id in history:
                    budget_records.append(history[evaluation.run_id])
                    continue
                valid = evaluation.candidate_recall["required_invariant_satisfied"]
                decision = "investigate" if valid else "reject"
                reason = ("Candidate recall preserved; stronger reranker may run."
                          if valid else
                          "Invalid before reranking: capped gold-blind pool loses accepted evidence.")
                record = _write_evaluation(
                    root, benchmark_path, phase_b_path, evaluation, decision, reason,
                    "Finish Phase C budget gates; do not rerank any pool that loses evidence.",
                    parent_metadata, parent_peak_mb,
                )
                budget_records.append(record)
                print(f"{evaluation.run_id}: recall {evaluation.candidate_recall['count']}/61", flush=True)

    if stage == "logic":
        return {"stage": stage, "runs": [record["run_id"] for record in full_records]}

    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    retained_records = [record for record in full_records if record["decision"] == "retain"]
    state["current_phase"] = "Phase D — Local reranker bake-off"
    state["current_best_configurations"]["phase_c"] = {
        "retained_run_ids": [record["run_id"] for record in retained_records],
        "candidate_pool": "61/61 full Phase A union",
        "representation": PHASE_B_RUN_ID,
    }
    state["exact_next_action"] = (
        "Run the approved Phase D MiniLM speed-oriented reranker first using retained Phase C logic."
    )
    state["unresolved_questions"] = [
        "Can a faster local reranker improve the quality-latency frontier?",
        "Can any later fast reranker preserve 61/61 evidence at a practical capped budget?",
    ]
    write_json(state_path, state)
    render_resume(root, state)
    report_path = root / "reports" / "experiments" / "phase_c_fusion_reranking.md"
    report_path.write_text(_report(full_records, budget_records), encoding="utf-8")
    return {"stage": stage,
            "retained": [record["run_id"] for record in retained_records],
            "invalid_budget_runs": [record["run_id"] for record in budget_records
                                    if not record["candidate_recall"]["required_invariant_satisfied"]],
            "report": str(report_path.relative_to(root))}


def build_parser() -> argparse.ArgumentParser:
    """Expose Phase C stages through a stable, resumable command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--stage", choices=("logic", "budgets", "all"), default="all")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Resolve paths, execute Phase C, and print its compact machine summary."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    benchmark = (args.benchmark or root / "data" / "benchmarks" /
                 "retrieval_benchmark_v1.jsonl").resolve()
    print(json.dumps(run(root, benchmark, args.stage), indent=2))


if __name__ == "__main__":
    main()
