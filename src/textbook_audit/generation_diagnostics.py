"""Small abstention diagnostic over frozen weak/not-answerable retrieval rows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from textbook_audit.generation_benchmark import read_jsonl
from textbook_audit.generation_experiments import (
    ROOT,
    _retrieved_items,
    content_tokens,
    parse_output,
    render_prompt,
    sha256_text,
    utc_now,
    write_json_atomic,
    write_jsonl_atomic,
)
from textbook_audit.generation_phase_a import LlamaServerConfig, LocalLlamaServer


NEGATIVE_TYPES = {"not_answerable", "weak_evidence", "weak_evidence_conversational"}


def _synthetic_generation_row(row: dict[str, Any]) -> dict[str, Any]:
    """Expose only runtime-safe retrieval fields to the standard prompt renderer."""
    source = "X Biology EM 2025-26.pdf" if row["book_id"] == "biology" else "X Physics EM 2025-26.pdf"
    return {
        "question_id": row["question_id"], "book_id": row["book_id"],
        "normalized_question": row["question"], "expected_answer_depth": "medium",
        "accepted_evidence_references": [{"source_file": source}],
    }


def _citation_support(parsed: dict[str, Any], items: list[dict[str, Any]]) -> float:
    """Estimate whether the cited supplied text lexically supports the final answer."""
    selected = set(parsed.get("selected_evidence_ids", []))
    evidence_text = " ".join(item["text"] for item in items if item["evidence_id"] in selected)
    answer_tokens = content_tokens(parsed.get("answer", ""))
    if not answer_tokens:
        return 0.0
    return len(answer_tokens & content_tokens(evidence_text)) / len(answer_tokens)


def run_abstention_diagnostic(
    *, output_dir: Path, llama_server: Path, model_path: Path, runtime: dict[str, Any],
    settings: dict[str, Any], prompt_strategy: str, port: int,
) -> dict[str, Any]:
    """Run five frozen negative/weak rows and compare model vs support-aware abstention."""
    benchmark = read_jsonl(ROOT / "data/benchmarks/retrieval_benchmark_v1.jsonl")
    source_rows = [row for row in benchmark if row["question_type"] in NEGATIVE_TYPES]
    if len(source_rows) != 5:
        raise ValueError(f"expected five abstention diagnostic rows, found {len(source_rows)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows = [{
        "question_id": row["question_id"], "question": row["question"],
        "book_id": row["book_id"], "diagnostic_type": row["question_type"],
    } for row in source_rows]
    write_jsonl_atomic(output_dir / "abstention_diagnostic_v1.jsonl", manifest_rows)
    question_dir = output_dir / "abstention_questions"
    question_dir.mkdir(parents=True, exist_ok=True)
    pending = [row for row in source_rows if not (question_dir / f"{row['question_id']}.json").is_file()]
    if pending:
        server = LocalLlamaServer(LlamaServerConfig(
            executable=llama_server, model=model_path, port=port, runtime=runtime,
            generation=settings, log_dir=output_dir / "abstention_runtime_logs",
        ))
        with server:
            for source_row in pending:
                row = _synthetic_generation_row(source_row)
                items = _retrieved_items(row, "retrieved_top5_separate_compact", ROOT)
                prompt = render_prompt(row, items, prompt_strategy,
                                       "retrieved_top5_separate_compact")
                generation = server.generate(prompt)
                parsed = parse_output(generation["raw_text"], items)
                support = _citation_support(parsed, items)
                model_abstained = parsed.get("status") == "insufficient_evidence"
                combined_abstained = model_abstained or support < 0.55
                write_json_atomic(question_dir / f"{source_row['question_id']}.json", {
                    "question_id": source_row["question_id"], "question": source_row["question"],
                    "book_id": source_row["book_id"], "diagnostic_type": source_row["question_type"],
                    "prompt_sha256": sha256_text(prompt), "supplied_evidence": items,
                    "generation": generation, "parsed_output": parsed,
                    "model_abstained": model_abstained,
                    "deterministic_citation_support": round(support, 4),
                    "model_plus_support_check_abstained": combined_abstained,
                    "completed_at": utc_now(),
                })
    results = [json.loads((question_dir / f"{row['question_id']}.json").read_text(encoding="utf-8")) for row in source_rows]
    metrics = {
        "questions": 5,
        "prompt_only_correct_abstentions": sum(row["model_abstained"] for row in results),
        "model_plus_support_correct_abstentions": sum(row["model_plus_support_check_abstained"] for row in results),
        "fabricated_or_overconfident_answers": sum(not row["model_abstained"] for row in results),
        "invalid_structured_outputs": sum(not row["parsed_output"].get("valid") for row in results),
        "interpretation": "diagnostic only; five rows are not statistically strong",
    }
    write_json_atomic(output_dir / "abstention_metrics.json", metrics)
    write_jsonl_atomic(output_dir / "abstention_results.jsonl", results)
    return metrics
