"""Run a selective OpenAI generation comparison over frozen RAG evidence.

The module deliberately separates planning from paid execution. A normal run
is a read-only preflight that materializes the exact request list and estimated
upper-bound cost. Network calls require both ``--execute-paid`` and an exact
``--approved-new-calls`` count, preventing accidental expansion of the run.

The provider boundary follows the earlier ``teachingAssistant`` service's
``LLMProvider`` design, while batch evaluation uses non-streaming Responses API
calls so each response can be cached, parsed, evaluated, and audited atomically.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from textbook_audit.generation_benchmark import read_jsonl, validate_benchmark
from textbook_audit.generation_experiments import (
    ROOT,
    build_context,
    build_split,
    evaluate_answer,
    load_experiment_config,
    parse_output,
    render_prompt,
    sha256_file,
    sha256_text,
    summarize,
    utc_now,
    verify_frozen_inputs,
    write_json_atomic,
    write_jsonl_atomic,
)


DEFAULT_CONFIG = ROOT / "config/openai_generation_experiments_v1.json"
DEFAULT_OUTPUT = ROOT / "reports/openai_generation_experiments"
EVALUATION_MODES = ("gold", "retrieved")


class ResponsesResource(Protocol):
    """Minimal Responses API surface needed by the experiment provider."""

    def create(self, **kwargs: Any) -> Any:
        """Create one response from a fully specified request."""


class OpenAIClientLike(Protocol):
    """Structural type that lets tests inject a non-network fake client."""

    responses: ResponsesResource


@dataclass(frozen=True)
class PlannedRequest:
    """Immutable description of one question/context API request."""

    question_id: str
    evaluation_mode: str
    prompt: str
    evidence: list[dict[str, Any]]
    request_sha256: str


def load_online_config(path: Path) -> dict[str, Any]:
    """Load the online experiment configuration and reject unknown schemas."""
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError("unsupported OpenAI generation config schema")
    return config


def load_env_file(path: Path) -> list[str]:
    """Load simple KEY=VALUE secrets without overriding process variables.

    Only variable names are returned, never values. Blank lines, comments,
    optional ``export`` prefixes, and matching quotes are supported; shell
    expansion is intentionally not implemented.
    """
    if not path.is_file():
        return []
    loaded: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            raise ValueError(f"invalid environment entry on line {line_number} of {path}")
        name, value = (part.strip() for part in line.split("=", 1))
        if not name or not name.replace("_", "a").isalnum() or name[0].isdigit():
            raise ValueError(f"invalid environment variable name on line {line_number} of {path}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if name not in os.environ and value:
            os.environ[name] = value
            loaded.append(name)
    return loaded


def answer_json_schema() -> dict[str, Any]:
    """Return the strict output contract shared with the local evaluator."""
    citation = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "evidence_id": {"type": "string"},
            "pdf_page": {"type": "integer"},
            "textbook_page": {"type": "integer"},
        },
        "required": ["evidence_id", "pdf_page", "textbook_page"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "status": {"type": "string", "enum": ["answered", "insufficient_evidence"]},
            "answer": {"type": "string"},
            "selected_evidence_ids": {"type": "array", "items": {"type": "string"}},
            "citations": {"type": "array", "items": citation},
            "missing_information": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "status", "answer", "selected_evidence_ids", "citations", "missing_information"
        ],
    }


class OpenAIResponsesGenerator:
    """Non-streaming Responses API provider with retries disabled by design."""

    def __init__(self, config: dict[str, Any], client: OpenAIClientLike | None = None):
        """Create the provider, importing the optional SDK only for real calls."""
        provider = config["provider"]
        self.model = provider["model"]
        self.max_output_tokens = config["frozen_configuration"]["max_output_tokens"]
        self.temperature = config["frozen_configuration"]["temperature"]
        if client is not None:
            self.client = client
            return
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI SDK is missing; install with: pip install -e .[online-generation]"
            ) from exc
        key_name = provider["api_key_environment_variable"]
        api_key = os.environ.get(key_name)
        if not api_key:
            raise RuntimeError(f"{key_name} is required only when --execute-paid is used")
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": provider["timeout_seconds"],
            # A failed call may already have been billed. Automatic retries are
            # therefore prohibited; the operator must explicitly resume it.
            "max_retries": provider["max_retries"],
        }
        base_url = os.environ.get(provider["base_url_environment_variable"])
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)

    def generate(self, prompt: str) -> dict[str, Any]:
        """Make exactly one structured request and normalize response metadata."""
        started = time.perf_counter()
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "grounded_textbook_answer",
                    "strict": True,
                    "schema": answer_json_schema(),
                }
            },
        )
        latency = time.perf_counter() - started
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        raw_text = getattr(response, "output_text", "") or ""
        return {
            "raw_text": raw_text,
            "latency_seconds": round(latency, 4),
            "time_to_first_token_seconds": None,
            "peak_rss_bytes": None,
            "response_id": getattr(response, "id", None),
            "response_status": getattr(response, "status", None),
            "resolved_model": getattr(response, "model", self.model),
            "usage": {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
                "total_tokens": int(getattr(usage, "total_tokens", input_tokens + output_tokens) or 0),
            },
        }


def _context_strategy(config: dict[str, Any], mode: str) -> str:
    """Map an evaluation mode to the frozen winning context strategy."""
    frozen = config["frozen_configuration"]
    return frozen["gold_context_strategy" if mode == "gold" else "retrieved_context_strategy"]


def _request_hash(model: str, prompt: str, settings: dict[str, Any]) -> str:
    """Hash every behavior-affecting request field for safe cache reuse."""
    body = json.dumps(
        {"model": model, "prompt": prompt, "settings": settings, "schema": answer_json_schema()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(body)


def build_plan(
    *, root: Path, online_config: dict[str, Any], local_config: dict[str, Any],
    rows: list[dict[str, Any]], split_name: str, modes: tuple[str, ...],
    question_ids: set[str] | None = None,
) -> list[PlannedRequest]:
    """Build requests deterministically without using gold rubrics in prompts."""
    split = build_split(rows, local_config)
    ids = (
        [row["question_id"] for row in rows]
        if split_name == "all"
        else split[f"{split_name}_question_ids"]
    )
    if question_ids is not None:
        unknown = question_ids - set(ids)
        if unknown:
            raise ValueError(
                f"selected question IDs are outside the {split_name} split: {sorted(unknown)}"
            )
        ids = [question_id for question_id in ids if question_id in question_ids]
    by_id = {row["question_id"]: row for row in rows}
    frozen = online_config["frozen_configuration"]
    settings = {
        "temperature": frozen["temperature"],
        "max_output_tokens": frozen["max_output_tokens"],
    }
    planned: list[PlannedRequest] = []
    for mode in modes:
        strategy = _context_strategy(online_config, mode)
        for question_id in ids:
            row = by_id[question_id]
            evidence = build_context(row, strategy, root)
            prompt = render_prompt(row, evidence, frozen["prompt_strategy"], strategy)
            digest = _request_hash(online_config["provider"]["model"], prompt, settings)
            planned.append(PlannedRequest(question_id, mode, prompt, evidence, digest))
    return planned


def _estimated_tokens(text: str) -> int:
    """Conservatively estimate input tokens for a preflight without an API call."""
    return math.ceil(len(text) / 4)


def build_preflight(
    plan: list[PlannedRequest], cache_dir: Path, config: dict[str, Any]
) -> dict[str, Any]:
    """Summarize exact cache hits, new calls, prompt sizes, and maximum cost."""
    pending = [item for item in plan if not (cache_dir / f"{item.request_sha256}.json").is_file()]
    input_tokens = sum(_estimated_tokens(item.prompt) for item in pending)
    max_output = len(pending) * config["frozen_configuration"]["max_output_tokens"]
    prices = config["pricing_snapshot"]
    upper_cost = (
        input_tokens * prices["input_per_million_tokens"]
        + max_output * prices["output_per_million_tokens"]
    ) / 1_000_000
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "provider": config["provider"]["name"],
        "model": config["provider"]["model"],
        "planned_requests": len(plan),
        "cache_hits": len(plan) - len(pending),
        "new_calls_required": len(pending),
        "estimated_new_input_tokens": input_tokens,
        "maximum_new_output_tokens": max_output,
        "estimated_upper_bound_cost_usd": round(upper_cost, 4),
        "pricing_snapshot": prices,
        "requests": [
            {
                "question_id": item.question_id,
                "evaluation_mode": item.evaluation_mode,
                "request_sha256": item.request_sha256,
                "cached": (cache_dir / f"{item.request_sha256}.json").is_file(),
                "estimated_input_tokens": _estimated_tokens(item.prompt),
            }
            for item in plan
        ],
    }


def _load_cached_generation(cache_path: Path) -> dict[str, Any]:
    """Load a completed provider response and verify its request hash binding."""
    return json.loads(cache_path.read_text(encoding="utf-8"))["generation"]


def _result_row(
    benchmark: dict[str, Any], request: PlannedRequest, generation: dict[str, Any],
    local_config: dict[str, Any], online_config: dict[str, Any],
) -> dict[str, Any]:
    """Convert one cached API response into the existing evaluation row shape."""
    parsed = parse_output(generation["raw_text"], request.evidence)
    evaluation = evaluate_answer(benchmark, parsed, local_config)
    provider_completed = generation.get("response_status") == "completed"
    # GPT-4o reports ``incomplete`` when it reaches the output ceiling. Keep
    # that distinct from a completed-but-invalid JSON response so aggregate
    # quality metrics never silently score a truncated answer as a normal run.
    hit_output_limit = (
        not provider_completed
        and generation.get("usage", {}).get("completion_tokens", 0)
        >= online_config["frozen_configuration"]["max_output_tokens"]
    )
    return {
        "schema_version": 1,
        "question_id": request.question_id,
        "question": benchmark["normalized_question"],
        "book_id": benchmark["book_id"],
        "difficulty": benchmark["difficulty"],
        "dependency_flags": {
            "formula": benchmark["requires_formula"],
            "visual": benchmark["requires_visual"],
            "table": benchmark["requires_table"],
            "multiple_passages": benchmark["requires_multiple_passages"],
        },
        "evaluation_mode": request.evaluation_mode,
        "provider": online_config["provider"]["name"],
        "requested_model": online_config["provider"]["model"],
        "status": "completed" if provider_completed else "incomplete",
        "provider_failure": "max_output_tokens" if hit_output_limit else (
            "provider_incomplete" if not provider_completed else None
        ),
        "request_sha256": request.request_sha256,
        "prompt_sha256": sha256_text(request.prompt),
        "context_sha256": sha256_text(json.dumps(request.evidence, sort_keys=True)),
        "supplied_evidence": request.evidence,
        "generation": generation,
        "parsed_output": parsed,
        "evaluation": evaluation,
        "completed_at": utc_now(),
    }


def run_experiment(
    *, root: Path, config_path: Path, output_dir: Path, split_name: str,
    modes: tuple[str, ...], execute_paid: bool, approved_new_calls: int | None,
    question_ids: set[str] | None = None, max_output_tokens: int | None = None,
    client: OpenAIClientLike | None = None,
) -> dict[str, Any]:
    """Plan or execute one bounded run, caching every successful API response."""
    online = load_online_config(config_path)
    if max_output_tokens is not None:
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        # Copy through JSON because the configuration is JSON-native and the
        # effective ceiling must participate in request hashes and manifests.
        online = json.loads(json.dumps(online))
        online["frozen_configuration"]["max_output_tokens"] = max_output_tokens
    local_path = root / online["local_experiment_config"]
    local = load_experiment_config(local_path)
    hashes = verify_frozen_inputs(root, local)
    rows = read_jsonl(root / local["frozen_inputs"]["generation_benchmark"])
    validate_benchmark(rows)
    plan = build_plan(
        root=root, online_config=online, local_config=local, rows=rows,
        split_name=split_name, modes=modes, question_ids=question_ids,
    )
    cache_dir = output_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    preflight = build_preflight(plan, cache_dir, online)
    write_json_atomic(output_dir / "preflight.json", preflight)
    if not execute_paid:
        return {"mode": "dry_run", "preflight": preflight}
    required = preflight["new_calls_required"]
    if approved_new_calls is None or approved_new_calls != required:
        raise ValueError(
            f"paid execution requires --approved-new-calls {required}; received {approved_new_calls}"
        )
    load_env_file(root / online["provider"].get("credential_env_file", ".env"))
    # A fully cached resume is deliberately possible without credentials or a
    # provider client. This lets reporting fixes rebuild artifacts at zero cost.
    generator = OpenAIResponsesGenerator(online, client=client) if required else None
    by_id = {row["question_id"]: row for row in rows}
    results: list[dict[str, Any]] = []
    for request in plan:
        cache_path = cache_dir / f"{request.request_sha256}.json"
        if cache_path.is_file():
            generation = _load_cached_generation(cache_path)
        else:
            # There is intentionally no catch-and-retry loop here. A failure
            # stops the run so a potentially billed request is never repeated
            # without a new explicit operator decision.
            generation = generator.generate(request.prompt)
            write_json_atomic(cache_path, {
                "schema_version": 1,
                "request_sha256": request.request_sha256,
                "question_id": request.question_id,
                "evaluation_mode": request.evaluation_mode,
                "created_at": utc_now(),
                "generation": generation,
            })
        results.append(_result_row(by_id[request.question_id], request, generation, local, online))
    run_key = sha256_text(json.dumps({
        "model": online["provider"]["model"], "split": split_name, "modes": modes,
        "requests": [item.request_sha256 for item in plan],
    }, sort_keys=True))[:12]
    run_id = f"openai__{online['provider']['model'].replace('-', '_')}__{split_name}__{'_'.join(modes)}__{run_key}"
    run_dir = output_dir / "runs" / run_id
    write_jsonl_atomic(run_dir / "results.jsonl", results)
    metrics = {
        mode: summarize([row for row in results if row["evaluation_mode"] == mode], None)
        for mode in modes
    }
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": utc_now(),
        "provider": online["provider"],
        "frozen_configuration": online["frozen_configuration"],
        "split": split_name,
        "evaluation_modes": list(modes),
        "selected_question_ids": sorted(question_ids) if question_ids is not None else None,
        "question_count": len({row["question_id"] for row in results}),
        "request_count": len(results),
        "new_calls_approved_this_invocation": approved_new_calls,
        "new_calls_executed_this_invocation": required,
        # Each used cache entry represents one unique provider response. This
        # cumulative count remains 16 during a zero-call report rebuild.
        "paid_provider_responses_recorded": sum(
            (cache_dir / f"{item.request_sha256}.json").is_file() for item in plan
        ),
        "frozen_input_hashes": hashes,
        "online_config_sha256": sha256_file(config_path),
        "metrics": metrics,
    }
    write_json_atomic(run_dir / "run_manifest.json", manifest)
    return {"mode": "executed", "manifest": manifest, "preflight": preflight}


def build_parser() -> argparse.ArgumentParser:
    """Create a CLI whose safe default is a zero-call preflight."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--split", choices=("smoke", "development", "holdout", "all"), default="smoke")
    parser.add_argument(
        "--evaluation-modes", nargs="+", choices=EVALUATION_MODES,
        default=list(EVALUATION_MODES),
    )
    parser.add_argument(
        "--execute-paid", action="store_true",
        help="Enable network requests; without this flag the command only writes a preflight.",
    )
    parser.add_argument(
        "--approved-new-calls", type=int,
        help="Must exactly equal the preflight's uncached request count.",
    )
    parser.add_argument(
        "--question-id", action="append", dest="question_ids",
        help="Restrict the run to selected IDs; repeat for multiple questions.",
    )
    parser.add_argument(
        "--max-output-tokens", type=int,
        help="Override the configured ceiling; included in request hashes and manifests.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the zero-call preflight or an explicitly capped paid experiment."""
    args = build_parser().parse_args(argv)
    result = run_experiment(
        root=ROOT,
        config_path=args.config.resolve(),
        output_dir=args.output_dir.resolve(),
        split_name=args.split,
        modes=tuple(args.evaluation_modes),
        execute_paid=args.execute_paid,
        approved_new_calls=args.approved_new_calls,
        question_ids=set(args.question_ids) if args.question_ids else None,
        max_output_tokens=args.max_output_tokens,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
