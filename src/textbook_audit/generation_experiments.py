"""Resumable local answer-generation experiments over frozen RAG inputs.

This module extends the small Phase A smoke harness without rewriting its
historical outputs.  Each configuration gets an immutable run directory and
each question is checkpointed independently, making multi-hour local CPU runs
safe to interrupt and resume.  Benchmark rubric fields are used only after
generation, never while prompts or contexts are constructed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from textbook_audit.generation_benchmark import read_jsonl, validate_benchmark
from textbook_audit.generation_phase_a import (
    LlamaServerConfig,
    LocalLlamaServer,
    ROOT,
    build_gold_context,
    content_tokens,
    sha256_file,
    sha256_text,
    token_recall,
    utc_now,
    write_json_atomic,
    write_jsonl_atomic,
)
from textbook_audit.retrieval_baseline import retrieve


DEFAULT_CONFIG = ROOT / "config/generation_experiments_v1.json"
DEFAULT_OUTPUT = ROOT / "reports/generation_experiments"
PROMPT_STRATEGIES = ("P0", "P1", "P2", "P3")
CONTEXT_STRATEGIES = (
    "gold_separate_full",
    "retrieved_top3_separate_compact",
    "retrieved_top5_separate_compact",
    "retrieved_top5_page_order_compact",
    "retrieved_top5_merged_compact",
    "retrieved_top5_separate_full",
)


def load_experiment_config(path: Path) -> dict[str, Any]:
    """Load the versioned experiment configuration and reject unknown schemas."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise ValueError("unsupported generation experiment config schema")
    return value


def verify_frozen_inputs(root: Path, config: dict[str, Any]) -> dict[str, str]:
    """Fail before inference if either frozen benchmark/config checksum changed."""
    frozen = config["frozen_inputs"]
    paths = {
        "generation_benchmark": root / frozen["generation_benchmark"],
        "retrieval_config": root / frozen["retrieval_config"],
    }
    hashes = {name: sha256_file(path) for name, path in paths.items()}
    for name, digest in hashes.items():
        if digest != frozen[f"{name}_sha256"]:
            raise ValueError(f"frozen {name} checksum mismatch")
    return hashes


def build_split(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    """Validate and materialize the approved 8/16/24 smoke/dev/holdout split."""
    all_ids = [row["question_id"] for row in rows]
    known = set(all_ids)
    smoke = list(config["split"]["smoke_question_ids"])
    development = list(config["split"]["development_question_ids"])
    if len(smoke) != 8 or len(set(smoke)) != 8:
        raise ValueError("smoke split must contain eight unique questions")
    if len(development) != 16 or len(set(development)) != 16:
        raise ValueError("development split must contain 16 unique questions")
    if not set(smoke) <= set(development):
        raise ValueError("smoke questions must be a subset of development")
    if not set(development) <= known:
        raise ValueError("split contains unknown benchmark IDs")
    holdout = [question_id for question_id in all_ids if question_id not in set(development)]
    if len(holdout) != 24:
        raise ValueError("holdout split must contain 24 questions")
    by_id = {row["question_id"]: row for row in rows}
    for name, ids in (("development", development), ("holdout", holdout)):
        books = {by_id[item]["book_id"] for item in ids}
        if books != {"biology", "physical_sciences"}:
            raise ValueError(f"{name} split must cover both books")
    return {
        "schema_version": 1,
        "seed": config["split"]["seed"],
        "policy": "Fixed stratified IDs; holdout is the stable benchmark complement.",
        "smoke_question_ids": smoke,
        "development_question_ids": development,
        "holdout_question_ids": holdout,
        "counts": {"smoke": 8, "development": 16, "holdout": 24, "all": 40},
    }


def _gold_items(row: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    """Create prompt-safe gold evidence units containing no rubric annotations."""
    return build_gold_context(row, root / "books")["evidence"]


def _retrieved_items(row: dict[str, Any], strategy: str, root: Path) -> list[dict[str, Any]]:
    """Convert exact frozen retrieval output into labelled generation evidence."""
    result = retrieve(row["normalized_question"], row["book_id"], include_text=True, root=root)
    top_n = 3 if "top3" in strategy else 5
    evidence = list(result.evidence[:top_n])
    if "page_order" in strategy:
        evidence.sort(key=lambda item: (min(item.pdf_pages), item.rank))
    if "merged" in strategy:
        items = []
        for index, segment in enumerate(result.assembled_context, 1):
            items.append({
                "evidence_id": f"E{index}",
                "pdf_page": min(segment.get("pdf_pages") or [0]),
                "textbook_page": min(segment.get("textbook_pages") or [0]),
                "source_file": row["accepted_evidence_references"][0]["source_file"],
                "text": segment["text"],
                "retrieval_rank": index,
                "source_chunk_ids": segment.get("source_chunk_ids", []),
            })
        return items[:top_n]
    return [{
        "evidence_id": f"E{index}",
        "pdf_page": item.pdf_pages[0] if item.pdf_pages else 0,
        "textbook_page": item.textbook_pages[0] if item.textbook_pages else 0,
        "pdf_pages": item.pdf_pages,
        "textbook_pages": item.textbook_pages,
        "source_file": row["accepted_evidence_references"][0]["source_file"],
        "text": item.evidence_text or "",
        "retrieval_rank": item.rank,
        "source_chunk_id": item.evidence_id,
    } for index, item in enumerate(evidence, 1)]


def build_context(row: dict[str, Any], strategy: str, root: Path) -> list[dict[str, Any]]:
    """Build gold or frozen-retrieved context without exposing benchmark labels."""
    if strategy == "gold_separate_full":
        return _gold_items(row, root)
    if strategy not in CONTEXT_STRATEGIES:
        raise ValueError(f"unknown context strategy: {strategy}")
    return _retrieved_items(row, strategy, root)


def _format_evidence(items: list[dict[str, Any]], compact: bool) -> str:
    """Render stable evidence blocks with either compact or full provenance."""
    blocks = []
    for item in items:
        if compact:
            heading = f"[{item['evidence_id']}] PDF {item['pdf_page']}; textbook {item['textbook_page']}"
        else:
            heading = (
                f"[{item['evidence_id']}] {item.get('source_file', '')} | "
                f"PDF page {item['pdf_page']} | textbook page {item['textbook_page']}"
            )
        blocks.append(f"{heading}\n{item['text']}")
    return "\n\n".join(blocks)


def render_prompt(
    row: dict[str, Any], items: list[dict[str, Any]], prompt_strategy: str,
    context_strategy: str, specialist_instruction: str | None = None,
) -> str:
    """Render one of the four approved prompts using runtime-safe row fields only."""
    if prompt_strategy not in PROMPT_STRATEGIES:
        raise ValueError(f"unknown prompt strategy: {prompt_strategy}")
    strategy_text = {
        "P0": "Answer directly and concisely from the evidence.",
        "P1": "First select the relevant evidence IDs internally, then write the answer.",
        "P2": "Write concise, separately supportable claims and cite the evidence used.",
        "P3": "Internally extract only brief supporting phrases, then write a student-friendly answer.",
    }[prompt_strategy]
    depth = {"short": "brief", "medium": "moderately detailed", "detailed": "detailed"}[
        row["expected_answer_depth"]
    ]
    schema = (
        '{"status":"answered|insufficient_evidence","answer":"...",'
        '"selected_evidence_ids":["E1"],"citations":'
        '[{"evidence_id":"E1","pdf_page":1,"textbook_page":1}],'
        '"missing_information":[]}'
    )
    specialist = f"\nAdditional instruction: {specialist_instruction}" if specialist_instruction else ""
    return (
        "/no_think\nUse only the supplied textbook evidence. Do not use outside knowledge. "
        "If it cannot support the question, return insufficient_evidence. Never invent page numbers. "
        f"{strategy_text} Make the answer {depth} and suitable for a Class 10 student.{specialist}\n"
        f"Return only valid JSON with exactly this shape: {schema}\n\n"
        f"QUESTION:\n{row['normalized_question']}\n\nTEXTBOOK EVIDENCE:\n"
        + _format_evidence(items, compact="compact" in context_strategy)
    )


def resolve_specialist_instruction(
    row: dict[str, Any], context_strategy: str, instruction: str | None, root: Path,
) -> str | None:
    """Activate specialist guidance from query/retrieval signals, never gold labels.

    The combined diagnostic prefix is intentionally interpreted at runtime. It
    checks the frozen retriever's activated branches and simple multi-part query
    phrasing; dependency labels remain unavailable to generation.
    """
    if not instruction or not instruction.startswith("ACTIVATE_SPECIALISTS"):
        return instruction
    activated: list[str] = []
    signals: set[str] = set()
    if context_strategy != "gold_separate_full":
        result = retrieve(row["normalized_question"], row["book_id"], include_text=False, root=root)
        signals = set(result.activated_specialist_signals)
    if "formula_equation_context" in signals:
        activated.append("State the exact formula, define symbols and units, include applicable conditions and sign conventions, and do not invent a derivation.")
    if "table_rows_with_headers" in signals:
        activated.append("Preserve table headings, row relationships, and units when explaining tabular evidence.")
    # This query-only detector activates organization for explicit compound questions.
    query = row["normalized_question"].lower()
    if re.search(r"\b(and|compare|differentiate|differences|what.+why|explain.+and)\b", query):
        activated.append("Organize the final answer by each explicit subtopic and select evidence for every subtopic.")
    return " ".join(activated) or None


def parse_output(raw_text: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Strictly validate the standard output schema and supplied citation metadata."""
    errors: list[str] = []
    try:
        parsed = json.loads(raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
    except json.JSONDecodeError as exc:
        return {"valid": False, "errors": [f"invalid JSON: {exc}"], "answer": ""}
    expected = {"status", "answer", "selected_evidence_ids", "citations", "missing_information"}
    if not isinstance(parsed, dict) or set(parsed) != expected:
        errors.append("output must contain exactly the five required keys")
    status = parsed.get("status")
    if status not in {"answered", "insufficient_evidence"}:
        errors.append("invalid status")
    if not isinstance(parsed.get("answer"), str):
        errors.append("answer must be a string")
    selected = parsed.get("selected_evidence_ids")
    citations = parsed.get("citations")
    missing = parsed.get("missing_information")
    if not isinstance(selected, list) or any(not isinstance(x, str) for x in selected):
        errors.append("selected_evidence_ids must be a string array")
        selected = []
    if not isinstance(missing, list) or any(not isinstance(x, str) for x in missing):
        errors.append("missing_information must be a string array")
    item_by_id = {item["evidence_id"]: item for item in items}
    if set(selected) - set(item_by_id):
        errors.append("selected evidence contains unknown IDs")
    if not isinstance(citations, list):
        errors.append("citations must be an array")
        citations = []
    valid_citations = 0
    for citation in citations:
        if not isinstance(citation, dict) or set(citation) != {"evidence_id", "pdf_page", "textbook_page"}:
            errors.append("citation has invalid shape")
            continue
        item = item_by_id.get(citation["evidence_id"])
        if item is None:
            errors.append("citation uses unknown evidence ID")
            continue
        pdf_pages = item.get("pdf_pages", [item["pdf_page"]])
        textbook_pages = item.get("textbook_pages", [item["textbook_page"]])
        if citation["pdf_page"] not in pdf_pages or citation["textbook_page"] not in textbook_pages:
            errors.append("citation page metadata does not match supplied evidence")
            continue
        valid_citations += 1
    return {
        "valid": not errors,
        "errors": errors,
        "status": status,
        "answer": parsed.get("answer", "") if isinstance(parsed, dict) else "",
        "selected_evidence_ids": selected,
        "citations": citations,
        "missing_information": missing if isinstance(missing, list) else [],
        "valid_citation_count": valid_citations,
        "citation_count": len(citations),
    }


def evaluate_answer(row: dict[str, Any], parsed: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Apply deterministic screening metrics after generation, never during ranking."""
    answer = parsed.get("answer", "")
    threshold = config["evaluation"]["required_point_match_threshold"]
    details = [{
        "point": point,
        "token_recall": round(token_recall(point, answer), 4),
        "matched": token_recall(point, answer) >= threshold,
    } for point in row["required_answer_points"]]
    coverage = sum(item["matched"] for item in details) / len(details)
    unsupported = []
    for claim in row["prohibited_or_unsupported_claims"]:
        if token_recall(claim, answer) >= config["evaluation"]["unsupported_claim_match_threshold"]:
            unsupported.append(claim)
    citation_validity = (
        parsed.get("valid_citation_count", 0) / parsed.get("citation_count", 1)
        if parsed.get("citation_count", 0) else 0.0
    )
    return {
        "required_point_details": details,
        "required_point_coverage": round(coverage, 4),
        "citation_validity": round(citation_validity, 4),
        "unsupported_claims": unsupported,
        "unsupported_claim_rate": float(bool(unsupported)),
        "structured_output_valid": bool(parsed.get("valid")),
        "false_insufficient_evidence": parsed.get("status") == "insufficient_evidence",
        "answer_word_count": len(answer.split()),
    }


def percentile(values: list[float], fraction: float) -> float | None:
    """Return a deterministic nearest-rank percentile for compact runtime reports."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.5)))
    return round(ordered[index], 4)


def summarize(results: list[dict[str, Any]], load_seconds: float | None) -> dict[str, Any]:
    """Aggregate comparable quality, grounding, and runtime metrics for one run."""
    complete = [row for row in results if row.get("status") == "completed"]
    latencies = [row["generation"]["latency_seconds"] for row in complete]
    generated = [row["generation"].get("usage", {}).get("completion_tokens", 0) for row in complete]
    first_tokens = [row["generation"]["time_to_first_token_seconds"] for row in complete
                    if row["generation"].get("time_to_first_token_seconds") is not None]
    peak_rss = [row["generation"]["peak_rss_bytes"] for row in complete
                if row["generation"].get("peak_rss_bytes") is not None]
    gpu_local = [row["generation"]["gpu_local_memory_bytes"] for row in complete
                 if row["generation"].get("gpu_local_memory_bytes") is not None]
    gpu_nonlocal = [row["generation"]["gpu_nonlocal_memory_bytes"] for row in complete
                    if row["generation"].get("gpu_nonlocal_memory_bytes") is not None]
    prompt_rates = [row["generation"]["prompt_tokens_per_second"] for row in complete
                    if row["generation"].get("prompt_tokens_per_second") is not None]
    generation_rates = [row["generation"]["generation_tokens_per_second"] for row in complete
                        if row["generation"].get("generation_tokens_per_second") is not None]
    formula_rows = [row for row in complete if row["dependency_flags"]["formula"]]
    return {
        "questions": len(results),
        "completed": len(complete),
        "required_point_coverage": round(statistics.mean(
            row["evaluation"]["required_point_coverage"] for row in complete
        ), 4) if complete else 0.0,
        "citation_validity": round(statistics.mean(
            row["evaluation"]["citation_validity"] for row in complete
        ), 4) if complete else 0.0,
        "unsupported_claim_rate": round(statistics.mean(
            row["evaluation"]["unsupported_claim_rate"] for row in complete
        ), 4) if complete else 0.0,
        "structured_output_rate": round(statistics.mean(
            float(row["evaluation"]["structured_output_valid"]) for row in complete
        ), 4) if complete else 0.0,
        "false_insufficient_count": sum(
            row["evaluation"]["false_insufficient_evidence"] for row in complete
        ),
        # This deterministic screen requires every rubric point on a formula-
        # dependent row; it is conservative and still needs scientific review.
        "formula_accuracy": round(statistics.mean(
            float(row["evaluation"]["required_point_coverage"] == 1.0
                  and not row["evaluation"]["unsupported_claims"])
            for row in formula_rows
        ), 4) if formula_rows else None,
        "model_load_seconds": round(load_seconds, 4) if load_seconds is not None else None,
        "p50_latency_seconds": percentile(latencies, 0.5),
        "p95_latency_seconds": percentile(latencies, 0.95),
        "p50_time_to_first_token_seconds": percentile(first_tokens, 0.5),
        "p95_time_to_first_token_seconds": percentile(first_tokens, 0.95),
        "mean_tokens_per_second": round(sum(generated) / sum(latencies), 4) if sum(latencies) else None,
        "mean_prompt_tokens_per_second": round(statistics.mean(prompt_rates), 4)
        if prompt_rates else None,
        "mean_generation_tokens_per_second": round(statistics.mean(generation_rates), 4)
        if generation_rates else None,
        "peak_rss_bytes": max(peak_rss) if peak_rss else None,
        "sampled_peak_gpu_local_memory_bytes": max(gpu_local) if gpu_local else None,
        "sampled_peak_gpu_nonlocal_memory_bytes": max(gpu_nonlocal) if gpu_nonlocal else None,
    }


def _run_id(model_key: str, split_name: str, mode: str, prompt: str, context: str,
            settings: dict[str, Any], specialist: str | None) -> str:
    """Build a readable ID plus hash so configuration collisions are impossible."""
    body = json.dumps([model_key, split_name, mode, prompt, context, settings, specialist], sort_keys=True)
    return f"{model_key}__{split_name}__{mode}__{prompt}__{context}__{sha256_text(body)[:10]}"


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    """Append one immutable run-ledger record using UTF-8 JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def rebuild_leaderboard(output_dir: Path) -> None:
    """Rebuild the concise CSV view from the immutable experiment run ledger."""
    ledger = output_dir / "experiment_runs.jsonl"
    rows = read_jsonl(ledger) if ledger.is_file() else []
    columns = [
        "run_id", "model", "split", "evaluation_mode", "prompt", "context",
        "required_point_coverage", "citation_validity", "unsupported_claim_rate",
        "formula_accuracy", "structured_output_rate", "p50_latency_seconds", "p95_latency_seconds",
        "mean_tokens_per_second", "decision",
    ]
    with (output_dir / "leaderboard.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            metrics = row["metrics"]
            writer.writerow({
                "run_id": row["run_id"], "model": row["model_key"], "split": row["split"],
                "evaluation_mode": row["evaluation_mode"], "prompt": row["prompt_strategy"],
                "context": row["context_strategy"],
                **{key: metrics.get(key) for key in columns if key in metrics},
                "decision": row.get("decision", "pending_review"),
            })


def run_configuration(
    *, root: Path, config_path: Path, output_dir: Path, llama_server: Path,
    model_path: Path, model_key: str, split_name: str, evaluation_mode: str,
    prompt_strategy: str, context_strategy: str, port: int,
    max_output_tokens: int | None = None, temperature: float | None = None,
    thinking: bool | None = None, specialist_instruction: str | None = None,
) -> dict[str, Any]:
    """Run or resume one fully specified configuration and record its summary once."""
    config = load_experiment_config(config_path)
    hashes = verify_frozen_inputs(root, config)
    rows = read_jsonl(root / config["frozen_inputs"]["generation_benchmark"])
    validate_benchmark(rows)
    split = build_split(rows, config)
    write_json_atomic(output_dir / "benchmark_split.json", split)
    if model_key not in config["models"]:
        raise ValueError(f"model is not approved: {model_key}")
    model = config["models"][model_key]
    actual_model_hash = sha256_file(model_path)
    if model.get("sha256") and actual_model_hash != model["sha256"]:
        raise ValueError("model checksum differs from approved configuration")
    if model_path.name != model["filename"]:
        raise ValueError("model filename differs from approved configuration")
    ids = split[f"{split_name}_question_ids"] if split_name != "all" else [r["question_id"] for r in rows]
    if evaluation_mode == "gold" and context_strategy != "gold_separate_full":
        raise ValueError("gold mode requires gold_separate_full context")
    if evaluation_mode == "retrieved" and context_strategy == "gold_separate_full":
        raise ValueError("retrieved mode cannot use gold context")
    settings = dict(config["generation_defaults"])
    if max_output_tokens is not None:
        settings["max_output_tokens"] = max_output_tokens
    if temperature is not None:
        settings["temperature"] = temperature
    if thinking is not None:
        settings["thinking"] = thinking
    run_id = _run_id(model_key, split_name, evaluation_mode, prompt_strategy,
                     context_strategy, settings, specialist_instruction)
    run_dir = output_dir / "runs" / run_id
    question_dir = run_dir / "questions"
    question_dir.mkdir(parents=True, exist_ok=True)
    by_id = {row["question_id"]: row for row in rows}
    runtime = dict(config["runtime"])
    server = LocalLlamaServer(LlamaServerConfig(
        executable=llama_server, model=model_path, port=port, runtime=runtime,
        generation=settings, log_dir=run_dir / "runtime_logs",
    ))
    pending = [item for item in ids if not (question_dir / f"{item}.json").is_file()]
    load_seconds = None
    if pending:
        with server:
            load_seconds = server.load_seconds
            for question_id in pending:
                row = by_id[question_id]
                items = build_context(row, context_strategy, root)
                active_specialist = resolve_specialist_instruction(
                    row, context_strategy, specialist_instruction, root
                )
                prompt = render_prompt(row, items, prompt_strategy, context_strategy,
                                       active_specialist)
                if settings.get("thinking"):
                    # Qwen enables thinking through the chat template; remove the
                    # explicit non-thinking control token for this diagnostic only.
                    prompt = prompt.removeprefix("/no_think\n")
                generation = server.generate(prompt)
                parsed = parse_output(generation["raw_text"], items)
                evaluation = evaluate_answer(row, parsed, config)
                write_json_atomic(question_dir / f"{question_id}.json", {
                    "schema_version": 1, "run_id": run_id, "question_id": question_id,
                    "question": row["normalized_question"], "book_id": row["book_id"],
                    "difficulty": row["difficulty"], "dependency_flags": {
                        "formula": row["requires_formula"], "visual": row["requires_visual"],
                        "table": row["requires_table"],
                        "multiple_passages": row["requires_multiple_passages"],
                    },
                    "status": "completed", "prompt_sha256": sha256_text(prompt),
                    "context_sha256": sha256_text(json.dumps(items, ensure_ascii=False, sort_keys=True)),
                    "supplied_evidence": items, "generation": generation,
                    "parsed_output": parsed, "evaluation": evaluation, "completed_at": utc_now(),
                })
    results = [json.loads((question_dir / f"{item}.json").read_text(encoding="utf-8")) for item in ids]
    metrics = summarize(results, load_seconds)
    manifest = {
        "schema_version": 1, "run_id": run_id, "created_at": utc_now(),
        "model_key": model_key, "model": model, "model_path": str(model_path),
        "model_sha256": actual_model_hash, "runtime": runtime, "settings": settings,
        "split": split_name, "question_ids": ids, "evaluation_mode": evaluation_mode,
        "prompt_strategy": prompt_strategy, "context_strategy": context_strategy,
        "specialist_instruction": specialist_instruction, "frozen_input_hashes": hashes,
        "metrics": metrics,
    }
    write_json_atomic(run_dir / "run_manifest.json", manifest)
    write_jsonl_atomic(run_dir / "results.jsonl", results)
    ledger_path = output_dir / "experiment_runs.jsonl"
    existing_ids = {row["run_id"] for row in read_jsonl(ledger_path)} if ledger_path.is_file() else set()
    if run_id not in existing_ids:
        _append_jsonl(ledger_path, {**manifest, "decision": "pending_review"})
    rebuild_leaderboard(output_dir)
    state = {
        "schema_version": 1, "updated_at": utc_now(), "current_phase": "controlled_runs",
        "last_completed_run": run_id, "last_valid_checkpoint": str(run_dir),
        "exact_next_action": "Review leaderboard and run the next bounded configuration.",
        "frozen_input_hashes": hashes,
    }
    write_json_atomic(output_dir / "experiment_state.json", state)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface for one resumable controlled run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--llama-server", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-key", required=True)
    parser.add_argument("--split", choices=("smoke", "development", "holdout", "all"), required=True)
    parser.add_argument("--evaluation-mode", choices=("gold", "retrieved"), required=True)
    parser.add_argument("--prompt", choices=PROMPT_STRATEGIES, required=True)
    parser.add_argument("--context", choices=CONTEXT_STRATEGIES, required=True)
    parser.add_argument("--port", type=int, default=18091)
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--specialist-instruction")
    return parser


def main(argv: list[str] | None = None) -> None:
    """Execute one configuration and print only its run ID and summary metrics."""
    args = build_parser().parse_args(argv)
    result = run_configuration(
        root=ROOT, config_path=args.config.resolve(), output_dir=args.output_dir.resolve(),
        llama_server=args.llama_server.resolve(), model_path=args.model.resolve(),
        model_key=args.model_key, split_name=args.split, evaluation_mode=args.evaluation_mode,
        prompt_strategy=args.prompt, context_strategy=args.context, port=args.port,
        max_output_tokens=args.max_output_tokens, temperature=args.temperature,
        thinking=args.thinking, specialist_instruction=args.specialist_instruction,
    )
    print(json.dumps({"run_id": result["run_id"], "metrics": result["metrics"]}, indent=2))


if __name__ == "__main__":
    main()
