"""Run the approved bounded generation matrix with resumable checkpoints.

The script deliberately narrows after each phase instead of constructing a
Cartesian product.  It uses deterministic automatic metrics only for screening;
the resulting winner remains provisional pending the blinded human review.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from textbook_audit.generation_experiments import (
    CONTEXT_STRATEGIES,
    DEFAULT_CONFIG,
    DEFAULT_OUTPUT,
    ROOT,
    run_configuration,
    utc_now,
    write_json_atomic,
)
from textbook_audit.generation_experiment_report import build_report
from textbook_audit.generation_diagnostics import run_abstention_diagnostic


def screen_score(run: dict[str, Any]) -> tuple[float, float, float, float]:
    """Rank screens by grounding, coverage, structure, then lower p95 latency."""
    metrics = run["metrics"]
    return (
        metrics["citation_validity"] - metrics["unsupported_claim_rate"],
        metrics["required_point_coverage"],
        metrics["structured_output_rate"],
        -(metrics["p95_latency_seconds"] or 1e9),
    )


def decision_line(phase: str, run: dict[str, Any], decision: str, reason: str) -> str:
    """Render one concise, auditable retain/reject decision."""
    metrics = run["metrics"]
    return (
        f"- {utc_now()} | {phase} | `{run['run_id']}` | **{decision}** | "
        f"coverage={metrics['required_point_coverage']}, citation={metrics['citation_validity']}, "
        f"unsupported={metrics['unsupported_claim_rate']}, p95={metrics['p95_latency_seconds']}s | {reason}"
    )


def update_resume(output: Path, phase: str, completed: list[dict[str, Any]], next_action: str) -> None:
    """Keep the compact cross-session resumption guide current after each phase."""
    leaders = sorted(completed, key=screen_score, reverse=True)[:3]
    lines = [
        "# Resume generation experiments", "", "## Objective", "",
        "Select a provisional local textbook-answering pipeline without changing frozen retrieval or benchmark inputs.",
        "", "## Frozen invariants", "",
        "- Retrieval Baseline v1 and Generation Benchmark v1 checksums are verified before every run.",
        "- Development decisions use 16 fixed questions; the 24-question holdout is never used for tuning.",
        "- Local llama.cpp CPU inference only; no hosted answer or judge calls.",
        "", "## Current checkpoint", "", f"- Phase: {phase}",
        f"- Completed configurations in this matrix invocation: {len(completed)}",
        f"- Exact next action: {next_action}", "", "## Current leaders", "",
    ]
    for run in leaders:
        lines.append(
            f"- `{run['run_id']}`: coverage {run['metrics']['required_point_coverage']}, "
            f"citation {run['metrics']['citation_validity']}, p95 {run['metrics']['p95_latency_seconds']}s"
        )
    lines.extend(["", "## Resume command", "", "Re-run the same matrix command. Completed question and run files are reused.", ""])
    (output / "RESUME_GENERATION_EXPERIMENT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Execute prompt, context, model, parameter, holdout, and final phases."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llama-server", type=Path, required=True)
    parser.add_argument("--qwen8", type=Path, required=True)
    parser.add_argument("--qwen14", type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--port", type=int, default=18092)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    completed: list[dict[str, Any]] = []
    decisions = output / "decisions.md"
    if not decisions.exists():
        decisions.write_text("# Generation experiment decisions\n\n", encoding="utf-8")

    def run(model_key: str, model_path: Path, split: str, mode: str, prompt: str,
            context: str, max_tokens: int | None = None, thinking: bool | None = None) -> dict[str, Any]:
        """Run or resume one matrix cell and immediately refresh resume state."""
        result = run_configuration(
            root=ROOT, config_path=args.config.resolve(), output_dir=output,
            llama_server=args.llama_server.resolve(), model_path=model_path.resolve(),
            model_key=model_key, split_name=split, evaluation_mode=mode,
            prompt_strategy=prompt, context_strategy=context, port=args.port,
            max_output_tokens=max_tokens, thinking=thinking,
        )
        completed.append(result)
        update_resume(output, "running", completed, "Continue the bounded matrix command.")
        return result

    # Phase B: isolate prompt effects on identical gold evidence and model.
    phase_b = [run("qwen3_8b_q4_k_m", args.qwen8, "development", "gold", prompt,
                   "gold_separate_full") for prompt in ("P0", "P1", "P2", "P3")]
    prompt_winner = max(phase_b, key=screen_score)
    winning_prompt = prompt_winner["prompt_strategy"]
    with decisions.open("a", encoding="utf-8") as handle:
        for item in phase_b:
            keep = item is prompt_winner
            handle.write(decision_line("Phase B", item, "retain" if keep else "reject",
                                       "Best grounded development screen." if keep else "Dominated by retained prompt.") + "\n")

    # Phase C: compare approved frozen-ranking context representations.
    retrieved_contexts = [item for item in CONTEXT_STRATEGIES if item != "gold_separate_full"]
    phase_c = [run("qwen3_8b_q4_k_m", args.qwen8, "development", "retrieved",
                   winning_prompt, context) for context in retrieved_contexts]
    context_winner = max(phase_c, key=screen_score)
    winning_context = context_winner["context_strategy"]
    with decisions.open("a", encoding="utf-8") as handle:
        for item in phase_c:
            keep = item is context_winner
            handle.write(decision_line("Phase C", item, "retain" if keep else "reject",
                                       "Best retrieved-context development screen." if keep else "No superior quality/latency trade-off.") + "\n")

    # Phase G diagnostic: runtime signals activate formula/table guidance, while
    # explicit multi-part query phrasing activates subtopic organization.
    specialist = run_configuration(
        root=ROOT, config_path=args.config.resolve(), output_dir=output,
        llama_server=args.llama_server.resolve(), model_path=args.qwen8.resolve(),
        model_key="qwen3_8b_q4_k_m", split_name="development",
        evaluation_mode="retrieved", prompt_strategy=winning_prompt,
        context_strategy=winning_context, port=args.port,
        specialist_instruction="ACTIVATE_SPECIALISTS",
    )
    completed.append(specialist)
    with decisions.open("a", encoding="utf-8") as handle:
        handle.write(decision_line(
            "Phase G", specialist, "diagnostic",
            "Formula, table, and multi-part instructions activated only by runtime query/retrieval signals."
        ) + "\n")

    # Phase F: a smoke-only thinking diagnostic; hidden reasoning is discarded by
    # the streaming runtime and this result never changes the global default.
    thinking_diagnostic = run(
        "qwen3_8b_q4_k_m", args.qwen8, "smoke", "retrieved",
        winning_prompt, winning_context, thinking=True,
    )
    with decisions.open("a", encoding="utf-8") as handle:
        handle.write(decision_line(
            "Phase F", thinking_diagnostic, "diagnostic",
            "Thinking mode measured on the difficult smoke slice; non-thinking remains the global default."
        ) + "\n")

    # Phase D/E: runtime-gate 14B, then compare only 256 and 512 output caps.
    candidates: list[tuple[str, Path, dict[str, Any], int]] = []
    q8_default = context_winner
    q8_caps = [run("qwen3_8b_q4_k_m", args.qwen8, "development", "retrieved",
                   winning_prompt, winning_context, cap) for cap in (256, 512)]
    q8_best = max([q8_default, *q8_caps], key=screen_score)
    candidates.append(("qwen3_8b_q4_k_m", args.qwen8, q8_best,
                       q8_best["settings"]["max_output_tokens"]))

    if args.qwen14 and args.qwen14.is_file():
        smoke14 = run("qwen3_14b_q4_k_m", args.qwen14, "smoke", "retrieved",
                      winning_prompt, winning_context)
        if smoke14["metrics"]["completed"] >= 6 and smoke14["metrics"]["structured_output_rate"] >= 0.75:
            default14 = run("qwen3_14b_q4_k_m", args.qwen14, "development", "retrieved",
                            winning_prompt, winning_context)
            cap14 = [run("qwen3_14b_q4_k_m", args.qwen14, "development", "retrieved",
                         winning_prompt, winning_context, cap) for cap in (256, 512)]
            best14 = max([default14, *cap14], key=screen_score)
            candidates.append(("qwen3_14b_q4_k_m", args.qwen14, best14,
                               best14["settings"]["max_output_tokens"]))
            verdict, reason = "retain", "Passed smoke gate and entered development frontier."
        else:
            verdict, reason = "reject", "Failed the >=6/8 completion and 75% structure runtime gate."
        with decisions.open("a", encoding="utf-8") as handle:
            handle.write(decision_line("Phase D", smoke14, verdict, reason) + "\n")

    # Phase I: no more than two available finalists; no tuning after these runs.
    finalists = sorted(candidates, key=lambda item: screen_score(item[2]), reverse=True)[:2]
    holdout_runs: list[tuple[str, Path, int, dict[str, Any], dict[str, Any]]] = []
    for model_key, model_path, _, cap in finalists:
        gold = run(model_key, model_path, "holdout", "gold", winning_prompt,
                   "gold_separate_full", cap)
        retrieved = run(model_key, model_path, "holdout", "retrieved", winning_prompt,
                        winning_context, cap)
        holdout_runs.append((model_key, model_path, cap, gold, retrieved))
    winner = max(holdout_runs, key=lambda item: screen_score(item[4]))
    model_key, model_path, cap, _, winning_holdout = winner
    final_gold = run(model_key, model_path, "all", "gold", winning_prompt,
                     "gold_separate_full", cap)
    final_retrieved = run(model_key, model_path, "all", "retrieved", winning_prompt,
                          winning_context, cap)
    final = {
        "schema_version": 1, "completed_at": utc_now(), "status": "complete",
        "provisional_winner": {
            "model_key": model_key, "prompt_strategy": winning_prompt,
            "context_strategy": winning_context, "max_output_tokens": cap,
            "holdout_retrieved_run": winning_holdout["run_id"],
            "all_gold_run": final_gold["run_id"], "all_retrieved_run": final_retrieved["run_id"],
        },
        "warning": "Provisional until blinded human review; automatic matching is not scientific adjudication.",
    }
    write_json_atomic(output / "provisional_winner.json", final)
    # The five negative/weak retrieval rows are kept separate from answerable metrics.
    run_abstention_diagnostic(
        output_dir=output, llama_server=args.llama_server.resolve(),
        model_path=model_path.resolve(), runtime=final_retrieved["runtime"],
        settings=final_retrieved["settings"], prompt_strategy=winning_prompt,
        port=args.port,
    )
    # Reporting is deterministic and uses only the immutable ledger/checkpoints.
    build_report(output)
    update_resume(output, "complete", completed, "Complete blinded human review packet.")
    # The per-run helper records a generic controlled-run state. Replace it with
    # the terminal matrix checkpoint so a fresh session does not attempt more
    # inference after all final and abstention artifacts already exist.
    state_path = output / "experiment_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update({
        "updated_at": utc_now(),
        "current_phase": "complete",
        "last_completed_run": final_retrieved["run_id"],
        "last_valid_checkpoint": str((output / "provisional_winner.json").resolve()),
        "exact_next_action": "Complete blinded human review packet; do not retune on holdout.",
    })
    write_json_atomic(state_path, state)
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
