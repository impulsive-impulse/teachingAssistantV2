"""Regression tests for final selection, frontier, and failure reporting."""

import json
from pathlib import Path

from textbook_audit.finalize_experiments import (
    BALANCED_RUN,
    LIGHTWEIGHT_RUN,
    QUALITY_RUN,
    pareto_frontier,
    run,
)
from textbook_audit.experiment_tracking import RUN_REQUIRED_FIELDS


ROOT = Path(__file__).resolve().parents[1]


def record(run_id: str, natural_h5: int, natural_mrr: float,
           hit1: int, mrr: float, latency: float, memory: float) -> dict:
    """Create the minimum comparable record needed for Pareto tests."""
    return {"run_id": run_id,
            "metrics": {"overall": {"hit_at_1_count": hit1, "mrr": mrr},
                        "natural_student": {"hit_at_5_count": natural_h5,
                                            "mrr": natural_mrr}},
            "latency": {"p95_ms": latency},
            "peak_memory": {"peak_rss_mb": memory}}


def test_pareto_frontier_rejects_only_strictly_dominated_runs() -> None:
    """A speed/quality tradeoff survives while an inferior clone does not."""
    quality = record("quality", 16, 0.60, 26, 0.60, 70, 700)
    speed = record("speed", 14, 0.52, 20, 0.51, 29, 750)
    dominated = record("dominated", 13, 0.50, 19, 0.50, 80, 800)
    assert {item["run_id"] for item in pareto_frontier(
        [quality, speed, dominated])} == {"quality", "speed"}


def test_generated_final_handoff_is_complete_and_consistent() -> None:
    """Final artifacts must name measured winners and every top-five miss."""
    result = run(ROOT)
    assert result["top5_failures"] == 11
    assert result["comparable_runs"] > result["pareto_runs"] > 0
    base = ROOT / "reports" / "experiments"
    selection = json.loads((base / "final_pipeline_selection.json").read_text(
        encoding="utf-8"))
    selected = {item["role"]: item["run_id"]
                for item in selection["selected_pipelines"]}
    assert selected == {"best_quality": QUALITY_RUN,
                        "best_lightweight_cpu": LIGHTWEIGHT_RUN,
                        "preferred_balanced": BALANCED_RUN}
    assert len(selection["remaining_top5_failures"]) == 11
    report = (base / "final_experiment_report.md").read_text(encoding="utf-8")
    assert "Exact balanced architecture" in report
    assert "query_final_pipeline.py" in report
    assert "generation benchmark" in report


def test_every_historical_run_is_unique_complete_and_reproducible() -> None:
    """Audit the persistent loop, not merely the final selected configurations."""
    run_log = ROOT / "reports" / "experiments" / "experiment_runs.jsonl"
    records = [json.loads(line) for line in run_log.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    assert len(records) == 121
    assert len({record["run_id"] for record in records}) == len(records)
    manifest_path = ROOT / "reports" / "experiments" / "experiment_artifact_manifest.jsonl"
    manifest = [json.loads(line) for line in manifest_path.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    by_path = {row["path"]: row for row in manifest}
    for record in records:
        assert not (set(RUN_REQUIRED_FIELDS) - set(record)), record["run_id"]
        assert record["reproduce_command"].strip()
        for output in record["output_artifact_paths"]:
            # Fresh clones omit large detail JSONL files, but their hash,
            # byte size, run owner, and reproduction command remain tracked.
            assert output in by_path, (record["run_id"], output)
            assert by_path[output]["run_id"] == record["run_id"]
            assert len(by_path[output]["sha256"]) == 64
    state = json.loads((ROOT / "reports" / "experiments" /
                        "experiment_state.json").read_text(encoding="utf-8"))
    assert set(state["completed_run_ids"]) == {record["run_id"] for record in records}
    assert state["pending_run_ids"] == []
