"""Phase A gold-context generation smoke test for the local textbook RAG system.

The module deliberately keeps the approved benchmark immutable. It derives a
development/smoke slice, extracts only accepted textbook PDF pages, asks a local
llama.cpp server for claim-level JSON answers, validates citations, scores the
answer against the benchmark rubric, and checkpoints every question so an
interrupted eight-question run can resume safely.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import psutil
from pypdf import PdfReader

from textbook_audit.generation_benchmark import SOURCE_FILES, read_jsonl, validate_benchmark


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config/generation_phase_a_v1.json"
DEFAULT_OUTPUT_DIR = ROOT / "reports/generation_phase_a_v1"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "into", "is", "it", "of", "on", "or", "that", "the", "their",
    "this", "to", "was", "when", "where", "which", "with",
}
NEGATIONS = {"no", "not", "never", "neither", "nor", "without", "cannot"}
CITATION_SUPPORT_THRESHOLD = 0.55
EVALUATOR_VERSION = "deterministic_rubric_and_citation_v1_1"


def utc_now() -> str:
    """Return a stable second-resolution UTC timestamp for state records."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    """Hash a potentially large artifact without loading it into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    """Hash prompt and context text using canonical UTF-8 bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, value: Any) -> None:
    """Write a JSON checkpoint atomically so interruption cannot corrupt state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_jsonl_atomic(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    """Replace a derived JSONL view atomically using deterministic compact rows."""
    content = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Load the versioned Phase A settings and reject an unsupported schema."""
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != 1:
        raise ValueError(f"unsupported Phase A config schema: {config.get('schema_version')}")
    return config


def build_benchmark_split(
    rows: list[dict[str, Any]], config: dict[str, Any], benchmark_path: Path
) -> dict[str, Any]:
    """Build the fixed eight-row development/smoke split and 32-row held-out set."""
    row_by_id = {row["question_id"]: row for row in rows}
    development_ids = list(config["split"]["development_question_ids"])
    missing = sorted(set(development_ids) - set(row_by_id))
    if missing:
        raise ValueError(f"configured smoke question IDs are absent: {missing}")
    if len(development_ids) != 8 or len(set(development_ids)) != 8:
        raise ValueError("development/smoke subset must contain exactly eight unique rows")

    smoke_rows = [row_by_id[question_id] for question_id in development_ids]
    if Counter(row["book_id"] for row in smoke_rows) != {"biology": 4, "physical_sciences": 4}:
        raise ValueError("smoke subset must contain four rows from each book")
    if set(row["difficulty"] for row in smoke_rows) != {"easy", "medium", "hard"}:
        raise ValueError("smoke subset must cover every difficulty")
    if not any(row["requires_formula"] for row in smoke_rows):
        raise ValueError("smoke subset must include formula-dependent evidence")
    if not any(row["requires_visual"] for row in smoke_rows):
        raise ValueError("smoke subset must include visual-dependent evidence")
    if not any(row["requires_table"] for row in smoke_rows):
        raise ValueError("smoke subset must include table-dependent evidence")
    if not any(row["requires_multiple_passages"] for row in smoke_rows):
        raise ValueError("smoke subset must include multi-passage evidence")

    held_out_ids = sorted(set(row_by_id) - set(development_ids))
    return {
        "schema_version": 1,
        "benchmark_path": str(benchmark_path.relative_to(ROOT)).replace("\\", "/"),
        "benchmark_sha256": sha256_file(benchmark_path),
        "split_policy": "Fixed reviewed development slice; all other rows held out.",
        "development_question_ids": development_ids,
        "smoke_question_ids": development_ids,
        "held_out_question_ids": held_out_ids,
        "counts": {"development": len(development_ids), "held_out": len(held_out_ids)},
        "smoke_distribution": {
            "books": dict(Counter(row["book_id"] for row in smoke_rows)),
            "difficulty": dict(Counter(row["difficulty"] for row in smoke_rows)),
            "formula": sum(row["requires_formula"] for row in smoke_rows),
            "visual": sum(row["requires_visual"] for row in smoke_rows),
            "table": sum(row["requires_table"] for row in smoke_rows),
            "multiple_passages": sum(row["requires_multiple_passages"] for row in smoke_rows),
        },
    }


def normalize_page_text(text: str) -> str:
    """Clean PDF extraction whitespace without changing textbook wording."""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def build_gold_context(row: dict[str, Any], books_dir: Path) -> dict[str, Any]:
    """Extract accepted one-based PDF pages into labelled, citable evidence units."""
    source_file = SOURCE_FILES[row["book_id"]]
    pdf_path = books_dir / source_file
    if not pdf_path.is_file():
        raise FileNotFoundError(f"source textbook PDF is missing: {pdf_path}")
    reader = PdfReader(pdf_path)
    evidence = []
    for index, (pdf_page, textbook_page) in enumerate(
        zip(row["accepted_pdf_pages"], row["accepted_textbook_pages"]), 1
    ):
        if pdf_page > len(reader.pages):
            raise ValueError(f"{row['question_id']}: PDF page {pdf_page} is out of range")
        text = normalize_page_text(reader.pages[pdf_page - 1].extract_text() or "")
        if not text:
            raise ValueError(f"{row['question_id']}: PDF page {pdf_page} has no text layer")
        evidence.append({
            "evidence_id": f"E{index}",
            "book_id": row["book_id"],
            "source_file": source_file,
            "pdf_page": pdf_page,
            "textbook_page": textbook_page,
            "text": text,
            "text_sha256": sha256_text(text),
        })
    return {
        "question_id": row["question_id"],
        "question": row["normalized_question"],
        "book_id": row["book_id"],
        "evidence": evidence,
        "context_sha256": sha256_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True)),
        "text_only_limitation": bool(row["requires_visual"]),
    }


def render_generation_prompt(row: dict[str, Any], context: dict[str, Any]) -> str:
    """Render a gold-context-only prompt with a strict claim-level citation contract."""
    evidence_blocks = []
    for item in context["evidence"]:
        heading = (
            f"[{item['evidence_id']}] {item['source_file']} | "
            f"PDF page {item['pdf_page']} | textbook page {item['textbook_page']}"
        )
        evidence_blocks.append(f"{heading}\n{item['text']}")
    depth_guidance = {
        "short": "Use 1-3 concise factual claims.",
        "medium": "Use 2-5 concise factual claims.",
        "detailed": "Use 3-7 concise factual claims.",
    }[row["expected_answer_depth"]]
    return (
        "/no_think\n"
        "Answer the student question using only the textbook evidence below. "
        "Do not use outside knowledge. Every claim must cite at least one evidence ID. "
        "Return only valid JSON with exactly this shape: "
        '{"claims":[{"text":"claim text","citations":["E1"]}]}. '
        "Do not add markdown fences or any other keys. "
        f"{depth_guidance}\n\n"
        f"QUESTION:\n{row['normalized_question']}\n\n"
        "TEXTBOOK EVIDENCE:\n" + "\n\n".join(evidence_blocks)
    )


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    """Parse direct or fenced model JSON while rejecting trailing prose."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"model output is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("structured answer must be a JSON object")
    return parsed


def validate_structured_answer(
    raw_text: str,
    valid_evidence_ids: set[str],
    evidence_text_by_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Validate JSON shape, evidence IDs, and lexical support for every cited claim."""
    errors: list[str] = []
    try:
        parsed = _extract_json_object(raw_text)
    except ValueError as exc:
        return {"valid": False, "errors": [str(exc)], "claims": [], "answer_text": ""}
    if set(parsed) != {"claims"}:
        errors.append("top-level JSON must contain exactly the 'claims' key")
    claims = parsed.get("claims")
    if not isinstance(claims, list) or not claims:
        errors.append("claims must be a non-empty array")
        claims = []
    normalized_claims = []
    for index, claim in enumerate(claims, 1):
        if not isinstance(claim, dict) or set(claim) != {"text", "citations"}:
            errors.append(f"claim {index} must contain exactly text and citations")
            continue
        text = claim.get("text")
        citations = claim.get("citations")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"claim {index} text must be non-empty")
            continue
        if (
            not isinstance(citations, list)
            or not citations
            or any(not isinstance(item, str) for item in citations)
        ):
            errors.append(f"claim {index} citations must be a non-empty string array")
            continue
        unknown = sorted(set(citations) - valid_evidence_ids)
        if unknown:
            errors.append(f"claim {index} uses unknown citations: {unknown}")
        normalized_claims.append({"text": text.strip(), "citations": list(dict.fromkeys(citations))})
    structure_valid = not errors
    citation_support = []
    if evidence_text_by_id is not None:
        for index, claim in enumerate(normalized_claims, 1):
            cited_text = " ".join(
                evidence_text_by_id.get(citation, "") for citation in claim["citations"]
            )
            claim_tokens = content_tokens(claim["text"])
            support_recall = (
                len(claim_tokens & content_tokens(cited_text)) / len(claim_tokens)
                if claim_tokens else 0.0
            )
            supported = support_recall >= CITATION_SUPPORT_THRESHOLD
            citation_support.append({
                "claim_index": index,
                "citations": claim["citations"],
                "claim_token_support": round(support_recall, 4),
                "supported": supported,
            })
            if not supported:
                errors.append(
                    f"claim {index} citation support {support_recall:.4f} is below "
                    f"{CITATION_SUPPORT_THRESHOLD:.2f}"
                )
    return {
        "valid": not errors,
        "structure_valid": structure_valid,
        "citation_support_valid": structure_valid and all(
            item["supported"] for item in citation_support
        ),
        "errors": errors,
        "claims": normalized_claims,
        "answer_text": " ".join(claim["text"] for claim in normalized_claims),
        "cited_evidence_ids": sorted({
            citation for claim in normalized_claims for citation in claim["citations"]
        }),
        "citation_support": citation_support,
        "validator": EVALUATOR_VERSION,
    }


def _stem(token: str) -> str:
    """Apply a small deterministic English suffix reducer for rubric matching."""
    for suffix in ("ization", "ation", "ingly", "edly", "ing", "ies", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[:-len(suffix)]
    return token


def content_tokens(text: str) -> set[str]:
    """Normalize prose and formula fragments into content tokens."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {_stem(token) for token in tokens if token not in STOPWORDS and len(token) > 1}


def token_recall(reference: str, candidate: str) -> float:
    """Measure how much rubric content appears in an answer on a 0-1 scale."""
    reference_tokens = content_tokens(reference)
    if not reference_tokens:
        return 1.0
    return len(reference_tokens & content_tokens(candidate)) / len(reference_tokens)


def evaluate_rubric(
    row: dict[str, Any], structured: dict[str, Any], evaluation_config: dict[str, Any]
) -> dict[str, Any]:
    """Score required/optional points and conservatively flag unsupported claims."""
    answer = structured["answer_text"]
    threshold = float(evaluation_config["required_point_match_threshold"])
    required_details = []
    for point in row["required_answer_points"]:
        score = token_recall(point, answer)
        required_details.append({"point": point, "token_recall": round(score, 4),
                                 "matched": score >= threshold})
    optional_details = []
    for point in row["optional_answer_points"]:
        score = token_recall(point, answer)
        optional_details.append({"point": point, "token_recall": round(score, 4),
                                 "matched": score >= threshold})

    possible_unsupported = []
    asserted_unsupported = []
    unsupported_threshold = float(evaluation_config["unsupported_claim_match_threshold"])
    for prohibited in row["prohibited_or_unsupported_claims"]:
        for claim in structured["claims"]:
            claim_tokens = content_tokens(claim["text"])
            # Negated statements often repeat a misconception only to correct it;
            # do not treat those as asserted unsupported claims.
            if claim_tokens & NEGATIONS:
                continue
            score = token_recall(prohibited, claim["text"])
            if score >= unsupported_threshold:
                possible_unsupported.append({
                    "prohibited": prohibited, "claim": claim["text"],
                    "token_recall": round(score, 4),
                })
                # Token overlap can confuse antonyms such as identical/diverse.
                # Only a normalized verbatim assertion is safe to penalize
                # automatically; every looser match remains visible for review.
                prohibited_normalized = " ".join(re.findall(r"[a-z0-9]+", prohibited.lower()))
                claim_normalized = " ".join(re.findall(r"[a-z0-9]+", claim["text"].lower()))
                if prohibited_normalized in claim_normalized:
                    asserted_unsupported.append({
                        "prohibited": prohibited, "claim": claim["text"],
                        "match": "normalized_verbatim",
                    })
                break

    required_matched = sum(detail["matched"] for detail in required_details)
    required_coverage = required_matched / len(required_details)
    optional_coverage = (
        sum(detail["matched"] for detail in optional_details) / len(optional_details)
        if optional_details else None
    )
    citation_score = 1.0 if structured["valid"] else 0.0
    score = max(0.0, min(1.0, 0.75 * required_coverage + 0.25 * citation_score
                         - 0.25 * len(asserted_unsupported)))
    passed = (
        structured["valid"]
        and required_coverage >= float(evaluation_config["question_pass_required_coverage"])
        and not asserted_unsupported
    )
    return {
        "required_points": required_details,
        "optional_points": optional_details,
        "required_coverage": round(required_coverage, 4),
        "optional_coverage": round(optional_coverage, 4) if optional_coverage is not None else None,
        "possible_unsupported_claims": possible_unsupported,
        "asserted_unsupported_claims": asserted_unsupported,
        "rubric_score": round(score, 4),
        "automatic_pass": passed,
        "manual_review_required": bool(evaluation_config["manual_review_required"]),
        "evaluator": EVALUATOR_VERSION,
    }


@dataclass
class LlamaServerConfig:
    """Resolved local paths and fixed runtime parameters for llama.cpp."""

    executable: Path
    model: Path
    port: int
    runtime: dict[str, Any]
    generation: dict[str, Any]
    log_dir: Path
    extra_arguments: tuple[str, ...] = ()


class LocalLlamaServer:
    """Manage one local llama-server process and its OpenAI-compatible API."""

    def __init__(self, config: LlamaServerConfig) -> None:
        """Store runtime configuration without starting a process."""
        self.config = config
        self.process: subprocess.Popen[bytes] | None = None
        self._stdout_handle: Any = None
        self._stderr_handle: Any = None
        self._stderr_session_offset = 0
        self.load_seconds: float | None = None

    def command(self) -> list[str]:
        """Build the exact server command recorded in experiment state."""
        runtime = self.config.runtime
        command = [
            str(self.config.executable), "--model", str(self.config.model),
            "--host", "127.0.0.1", "--port", str(self.config.port),
            "--ctx-size", str(runtime["context_size"]),
            "--threads", str(runtime["threads"]),
            "--threads-batch", str(runtime["threads_batch"]),
            "--batch-size", str(runtime["batch_size"]),
            "--ubatch-size", str(runtime["ubatch_size"]),
            "--n-gpu-layers", str(runtime["gpu_layers"]),
            "--parallel", str(runtime["parallel_slots"]),
            "--seed", str(self.config.generation["seed"]),
            "--no-webui",
        ]
        command.extend(self.config.extra_arguments)
        return command

    def start(self, timeout_seconds: float = 180.0) -> None:
        """Start llama-server, persist both logs, and wait for model readiness."""
        if self.process is not None:
            raise RuntimeError("llama-server is already started")
        self.config.log_dir.mkdir(parents=True, exist_ok=True)
        # Append sessions so a resume attempt never destroys the original
        # backend initialization and request timing trace.
        self._stdout_handle = (self.config.log_dir / "llama_server.stdout.log").open("ab")
        self._stderr_handle = (self.config.log_dir / "llama_server.stderr.log").open("ab")
        marker = f"\n=== llama-server session started {utc_now()} ===\n".encode("utf-8")
        self._stdout_handle.write(marker)
        self._stderr_handle.write(marker)
        self._stdout_handle.flush()
        self._stderr_handle.flush()
        self._stderr_session_offset = self._stderr_handle.tell()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        started = time.perf_counter()
        self.process = subprocess.Popen(
            self.command(), cwd=self.config.executable.parent,
            stdout=self._stdout_handle, stderr=self._stderr_handle,
            creationflags=flags,
        )
        health_url = f"http://127.0.0.1:{self.config.port}/health"
        while time.perf_counter() - started < timeout_seconds:
            if self.process.poll() is not None:
                raise RuntimeError(f"llama-server exited during load with {self.process.returncode}")
            try:
                with urllib.request.urlopen(health_url, timeout=1) as response:
                    if response.status == 200:
                        self.load_seconds = time.perf_counter() - started
                        return
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.1)
        raise TimeoutError(f"llama-server was not healthy within {timeout_seconds} seconds")

    def stderr_session_text(self) -> str:
        """Return only stderr emitted by the current server session."""

        if self._stderr_handle is not None:
            self._stderr_handle.flush()
        path = self.config.log_dir / "llama_server.stderr.log"
        if not path.is_file():
            return ""
        with path.open("rb") as handle:
            handle.seek(self._stderr_session_offset)
            return handle.read().decode("utf-8", errors="replace")

    def generate(self, prompt: str) -> dict[str, Any]:
        """Stream one JSON completion to measure first-token and total latency.

        Reasoning-channel tokens, when a diagnostic enables Qwen thinking, are
        counted only for first-token timing and are never retained.  Only final
        answer content is assembled into ``raw_text``.
        """
        generation = self.config.generation
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": generation["temperature"],
            "seed": generation["seed"],
            "max_tokens": generation["max_output_tokens"],
            "stream": True,
            "stream_options": {"include_usage": True},
            "response_format": {"type": "json_object"},
        }
        for key in (
            "top_p",
            "top_k",
            "min_p",
            "repeat_penalty",
            "presence_penalty",
            "frequency_penalty",
        ):
            if key in generation:
                payload[key] = generation[key]
        if "chat_template_kwargs" in generation:
            payload["chat_template_kwargs"] = generation["chat_template_kwargs"]
        elif "thinking" in generation:
            payload["chat_template_kwargs"] = {
                "enable_thinking": generation["thinking"]
            }
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.config.port}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        stderr_path = self.config.log_dir / "llama_server.stderr.log"
        request_log_offset = stderr_path.stat().st_size if stderr_path.is_file() else 0
        started = time.perf_counter()
        first_token_seconds: float | None = None
        content_parts: list[str] = []
        usage: dict[str, Any] = {}
        response_id: str | None = None
        with urllib.request.urlopen(request, timeout=600) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                response_id = response_id or chunk.get("id")
                if chunk.get("usage"):
                    usage = chunk["usage"]
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                token_observed = delta.get("content") or delta.get("reasoning_content")
                if token_observed and first_token_seconds is None:
                    first_token_seconds = time.perf_counter() - started
                # Hidden reasoning is intentionally not stored in experiment artifacts.
                if delta.get("content"):
                    content_parts.append(delta["content"])
        latency = time.perf_counter() - started
        timings = self._request_timings(stderr_path, request_log_offset)
        memory = psutil.Process(self.process.pid).memory_info() if self.process else None
        gpu_memory = self._windows_gpu_process_memory()
        return {
            "raw_text": "".join(content_parts),
            "time_to_first_token_seconds": first_token_seconds,
            "latency_seconds": latency,
            "usage": usage,
            "response_id": response_id,
            "peak_rss_bytes": getattr(memory, "peak_wset", memory.rss) if memory else None,
            "gpu_local_memory_bytes": gpu_memory["local"] if gpu_memory else None,
            "gpu_nonlocal_memory_bytes": gpu_memory["nonlocal"] if gpu_memory else None,
            "prompt_tokens_per_second": timings.get("prompt_tokens_per_second"),
            "generation_tokens_per_second": timings.get("generation_tokens_per_second"),
            "prompt_eval_seconds": timings.get("prompt_eval_seconds"),
            "generation_eval_seconds": timings.get("generation_eval_seconds"),
        }

    @staticmethod
    def _request_timings(path: Path, offset: int) -> dict[str, float]:
        """Parse llama.cpp's authoritative per-request timing lines."""

        if not path.is_file():
            return {}
        # The server writes its timing lines immediately before completing the
        # streaming request. A tiny bounded retry handles filesystem buffering.
        text = ""
        for _ in range(5):
            with path.open("rb") as handle:
                handle.seek(offset)
                text = handle.read().decode("utf-8", errors="replace")
            if "eval time =" in text:
                break
            time.sleep(0.05)
        prompt_matches = re.findall(
            r"prompt eval time\s*=\s*([0-9.]+)\s*ms\s*/\s*\d+\s*tokens.*?"
            r"([0-9.]+)\s*tokens per second",
            text,
        )
        generation_matches = re.findall(
            r"(?<!prompt )eval time\s*=\s*([0-9.]+)\s*ms\s*/\s*\d+\s*tokens.*?"
            r"([0-9.]+)\s*tokens per second",
            text,
        )
        values: dict[str, float] = {}
        if prompt_matches:
            milliseconds, rate = prompt_matches[-1]
            values["prompt_eval_seconds"] = float(milliseconds) / 1000
            values["prompt_tokens_per_second"] = float(rate)
        if generation_matches:
            milliseconds, rate = generation_matches[-1]
            values["generation_eval_seconds"] = float(milliseconds) / 1000
            values["generation_tokens_per_second"] = float(rate)
        return values

    def _windows_gpu_process_memory(self) -> dict[str, int] | None:
        """Read current Windows GPU memory counters for the server process.

        OpenCL model allocations normally remain resident across requests, so
        the post-generation value is a useful comparable high-water proxy. The
        experiment still labels this as a sampled value rather than a true
        continuous peak.
        """

        if os.name != "nt" or self.process is None:
            return None
        script = (
            f"$targetProcessId={int(self.process.pid)};"
            "$samples=Get-Counter "
            "'\\GPU Process Memory(*)\\Local Usage',"
            "'\\GPU Process Memory(*)\\Non Local Usage' "
            "-ErrorAction SilentlyContinue | "
            "Select-Object -ExpandProperty CounterSamples | "
            "Where-Object { $_.InstanceName -like ('pid_'+$targetProcessId+'_*') };"
            "$local=($samples | Where-Object {$_.Path -like '*\\local usage'} | "
            "Measure-Object CookedValue -Sum).Sum;"
            "$nonlocal=($samples | Where-Object {$_.Path -like '*\\non local usage'} | "
            "Measure-Object CookedValue -Sum).Sum;"
            "[pscustomobject]@{local=[int64]$local;nonlocal=[int64]$nonlocal} | "
            "ConvertTo-Json -Compress"
        )
        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if completed.returncode != 0 or not completed.stdout.strip():
                return None
            value = json.loads(completed.stdout)
            return {
                "local": int(value.get("local") or 0),
                "nonlocal": int(value.get("nonlocal") or 0),
            }
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
            return None

    def stop(self) -> None:
        """Terminate the local server and close log handles even after failure."""
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=15)
        self.process = None
        for handle in (self._stdout_handle, self._stderr_handle):
            if handle is not None:
                handle.close()
        self._stdout_handle = None
        self._stderr_handle = None

    def __enter__(self) -> "LocalLlamaServer":
        """Start the server for a context-managed smoke run."""
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        """Always stop the server when leaving a managed smoke run."""
        self.stop()


def _initial_state(
    split: dict[str, Any], config: dict[str, Any], config_path: Path,
    model_path: Path, server_command: list[str],
) -> dict[str, Any]:
    """Create the immutable-input portion of a resumable smoke checkpoint."""
    return {
        "schema_version": 1,
        "experiment_id": config["experiment_id"],
        "phase": "Phase A — eight-question gold-context smoke test",
        "status": "initialized",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "benchmark_sha256": split["benchmark_sha256"],
        "config_path": str(config_path),
        "config_sha256": sha256_file(config_path),
        "runner_source_sha256": sha256_file(Path(__file__)),
        "model_path": str(model_path),
        "model_sha256": sha256_file(model_path),
        "server_command": server_command,
        "planned_question_ids": split["smoke_question_ids"],
        "completed_question_ids": [],
        "failed_question_ids": [],
        "next_question_id": split["smoke_question_ids"][0],
        "other_model_downloads_permitted": False,
        "prompt_comparisons_permitted": False,
    }


def load_or_initialize_state(
    state_path: Path, split: dict[str, Any], config: dict[str, Any], config_path: Path,
    model_path: Path, server_command: list[str],
) -> dict[str, Any]:
    """Resume a checkpoint only when every immutable input still matches."""
    expected = _initial_state(split, config, config_path, model_path, server_command)
    if not state_path.is_file():
        write_json_atomic(state_path, expected)
        return expected
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for field in (
        "experiment_id", "benchmark_sha256", "config_sha256", "runner_source_sha256",
        "model_sha256",
        "planned_question_ids", "server_command",
    ):
        if state.get(field) != expected[field]:
            raise ValueError(f"cannot resume: state {field} differs from current inputs")
    return state


def rebuild_results_view(output_dir: Path, planned_ids: list[str]) -> list[dict[str, Any]]:
    """Rebuild authoritative smoke_results.jsonl from atomic per-question files."""
    rows = []
    for question_id in planned_ids:
        path = output_dir / "runs" / f"{question_id}.json"
        if path.is_file():
            rows.append(json.loads(path.read_text(encoding="utf-8")))
    write_jsonl_atomic(output_dir / "smoke_results.jsonl", rows)
    return rows


def summarize_smoke(results: list[dict[str, Any]], planned_count: int) -> dict[str, Any]:
    """Aggregate smoke structure, citation, rubric, latency, and dependency results."""
    successful = [row for row in results if row.get("status") == "completed"]
    latencies = [row["generation"]["latency_seconds"] for row in successful]
    return {
        "planned_questions": planned_count,
        "completed_questions": len(successful),
        "failed_questions": sum(row.get("status") == "failed" for row in results),
        "structured_output_valid": sum(
            row["citation_validation"].get("structure_valid", False) for row in successful
        ),
        "lexical_citation_support_valid": sum(
            row["citation_validation"].get("citation_support_valid", False) for row in successful
        ),
        "automatic_passes": sum(row["rubric_evaluation"]["automatic_pass"] for row in successful),
        "mean_required_coverage": round(
            sum(row["rubric_evaluation"]["required_coverage"] for row in successful)
            / len(successful), 4
        ) if successful else None,
        "mean_rubric_score": round(
            sum(row["rubric_evaluation"]["rubric_score"] for row in successful)
            / len(successful), 4
        ) if successful else None,
        "mean_latency_seconds": round(sum(latencies) / len(latencies), 4) if latencies else None,
        "max_latency_seconds": round(max(latencies), 4) if latencies else None,
        "manual_review_required": True,
        "prompt_comparisons_started": False,
        "other_models_downloaded": False,
    }


def load_manual_reviews(
    output_dir: Path, planned_ids: list[str], required: bool = False,
) -> list[dict[str, Any]]:
    """Load and validate the human-readable rubric/citation review artifact."""
    path = output_dir / "manual_review.jsonl"
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"manual review is missing: {path}")
        return []
    reviews = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    ids = [row.get("question_id") for row in reviews]
    if ids != planned_ids:
        raise ValueError("manual review rows must follow the exact smoke-question order")
    for row in reviews:
        total = row.get("required_points_total")
        met = row.get("required_points_met")
        if not isinstance(total, int) or not isinstance(met, int) or not 0 <= met <= total:
            raise ValueError(f"invalid manual rubric counts for {row.get('question_id')}")
        expected = round(met / total, 4)
        if row.get("strict_required_coverage") != expected:
            raise ValueError(f"manual coverage mismatch for {row.get('question_id')}")
        if row.get("citation_verdict") not in {"supported", "partially_supported", "unsupported"}:
            raise ValueError(f"invalid manual citation verdict for {row.get('question_id')}")
    return reviews


def add_manual_review_metrics(
    metrics: dict[str, Any], reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    """Add independently reviewed coverage and grounding outcomes to smoke metrics."""
    if not reviews:
        return metrics
    metrics["manual_review"] = {
        "reviewed_questions": len(reviews),
        "strict_gate_passes": sum(row["manual_gate_pass"] for row in reviews),
        "mean_strict_required_coverage": round(
            sum(row["strict_required_coverage"] for row in reviews) / len(reviews), 4
        ),
        "fully_supported_citations": sum(
            row["citation_verdict"] == "supported" for row in reviews
        ),
        "partially_supported_citations": sum(
            row["citation_verdict"] == "partially_supported" for row in reviews
        ),
        "unsupported_citations": sum(
            row["citation_verdict"] == "unsupported" for row in reviews
        ),
        "unsupported_claims_found": sum(
            len(row["unsupported_claims_found"]) for row in reviews
        ),
    }
    return metrics


def render_smoke_report(
    output_dir: Path, config: dict[str, Any], split: dict[str, Any],
    results: list[dict[str, Any]], metrics: dict[str, Any],
) -> None:
    """Write a concise Markdown gate report with one row per smoke question."""
    reviews = load_manual_reviews(output_dir, split["smoke_question_ids"])
    lines = [
        "# Phase A gold-context smoke test",
        "",
        "This gate uses the approved Qwen3-8B Q4_K_M model and accepted textbook PDF pages. "
        "No prompt comparison or additional model download is part of this run.",
        "",
        "## Summary",
        "",
        f"- Completed: {metrics['completed_questions']}/{metrics['planned_questions']}",
        f"- Valid structured outputs and evidence IDs: {metrics['structured_output_valid']}",
        f"- Strict lexical citation-support passes: "
        f"{metrics['lexical_citation_support_valid']}",
        f"- Deterministic automatic passes: {metrics['automatic_passes']}",
        f"- Mean required-point coverage: {metrics['mean_required_coverage']}",
        f"- Mean rubric score: {metrics['mean_rubric_score']}",
        f"- Mean latency: {metrics['mean_latency_seconds']} seconds",
        "- Manual review remains required before prompt comparisons.",
        "",
        "## Per-question results",
        "",
        "| Question | Book | Difficulty | JSON/IDs | Lexical citation support | Required coverage | Score | Pass | Latency (s) |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in results:
        if row.get("status") != "completed":
            lines.append(f"| {row['question_id']} | — | — | 0 | 0 | — | — | 0 | — |")
            continue
        lines.append(
            f"| {row['question_id']} | {row['book_id']} | {row['difficulty']} | "
            f"{int(row['citation_validation']['structure_valid'])} | "
            f"{int(row['citation_validation']['citation_support_valid'])} | "
            f"{row['rubric_evaluation']['required_coverage']:.4f} | "
            f"{row['rubric_evaluation']['rubric_score']:.4f} | "
            f"{int(row['rubric_evaluation']['automatic_pass'])} | "
            f"{row['generation']['latency_seconds']:.3f} |"
        )
    if reviews:
        manual = metrics["manual_review"]
        lines.extend([
            "", "## Manual rubric and citation review", "",
            f"- Strict answer-and-grounding passes: {manual['strict_gate_passes']}/8",
            f"- Mean strict required-point coverage: "
            f"{manual['mean_strict_required_coverage']}",
            f"- Fully supported citation sets: {manual['fully_supported_citations']}/8",
            f"- Partially supported citation sets: "
            f"{manual['partially_supported_citations']}/8",
            f"- Unsupported claims found: {manual['unsupported_claims_found']}",
            "", "| Question | Required coverage | Citation verdict | Strict pass |",
            "|---|---:|---|---:|",
        ])
        for review in reviews:
            lines.append(
                f"| {review['question_id']} | {review['strict_required_coverage']:.4f} | "
                f"{review['citation_verdict']} | {int(review['manual_gate_pass'])} |"
            )
        lines.extend([
            "", "## Gate decision", "",
            "The infrastructure smoke gate passed (8/8 completed and resumable), but the "
            "answer-quality and grounding gate did not: only 2/8 answers passed strict "
            "manual rubric plus citation review. Prompt comparisons and other model "
            "downloads therefore remain gated. The next action is to correct context "
            "sufficiency and answer instructions using this same Qwen baseline, after "
            "the user reviews these results.",
        ])
    lines.extend([
        "", "## Reproduction", "",
        "```powershell",
        "temp\\python-x64\\python.exe scripts\\run_generation_phase_a.py `",
        "  --llama-server <path-to-native-arm64-llama-server.exe> `",
        "  --model <path-to-Qwen3-8B-Q4_K_M.gguf>",
        "```",
        "",
        f"Configuration: `{config['experiment_id']}`. "
        f"Benchmark SHA-256: `{split['benchmark_sha256']}`.",
    ])
    (output_dir / "phase_a_smoke_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare_artifacts(
    root: Path, config_path: Path, output_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Validate frozen inputs and materialize split, smoke rows, and gold contexts."""
    config = load_config(config_path)
    benchmark_path = root / config["benchmark_path"]
    rows = read_jsonl(benchmark_path)
    validate_benchmark(rows)
    actual_benchmark_hash = sha256_file(benchmark_path)
    if actual_benchmark_hash != config["benchmark_sha256"]:
        raise ValueError("Generation Benchmark v1 hash differs from the approved config")
    split = build_benchmark_split(rows, config, benchmark_path)
    row_by_id = {row["question_id"]: row for row in rows}
    smoke_rows = [row_by_id[question_id] for question_id in split["smoke_question_ids"]]
    contexts = [build_gold_context(row, root / "books") for row in smoke_rows]
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_dir / "benchmark_split.json", split)
    write_jsonl_atomic(output_dir / "smoke_subset.jsonl", smoke_rows)
    write_jsonl_atomic(output_dir / "gold_contexts.jsonl", contexts)
    return config, split, smoke_rows, {row["question_id"]: row for row in contexts}


def run_smoke(
    root: Path, config_path: Path, output_dir: Path,
    llama_server: Path, model_path: Path, port: int,
) -> dict[str, Any]:
    """Run or resume all eight Qwen gold-context generations and persist the gate."""
    config, split, smoke_rows, context_by_id = prepare_artifacts(root, config_path, output_dir)
    if sha256_file(model_path) != config["model"]["sha256"]:
        raise ValueError("Qwen GGUF SHA-256 does not match the approved configuration")
    if not llama_server.is_file():
        raise FileNotFoundError(f"llama-server executable is missing: {llama_server}")

    server_config = LlamaServerConfig(
        executable=llama_server, model=model_path, port=port,
        runtime=config["runtime"], generation=config["generation"],
        log_dir=output_dir / "runtime_logs",
    )
    server = LocalLlamaServer(server_config)
    state_path = output_dir / "experiment_state.json"
    state = load_or_initialize_state(
        state_path, split, config, config_path, model_path, server.command()
    )
    existing_results = rebuild_results_view(output_dir, split["smoke_question_ids"])
    if (
        len(existing_results) == len(split["smoke_question_ids"])
        and all(result.get("status") == "completed" for result in existing_results)
    ):
        metrics = summarize_smoke(existing_results, len(split["smoke_question_ids"]))
        metrics["evaluator"] = EVALUATOR_VERSION
        add_manual_review_metrics(
            metrics, load_manual_reviews(output_dir, split["smoke_question_ids"])
        )
        write_json_atomic(output_dir / "smoke_metrics.json", metrics)
        state["status"] = "complete"
        state["updated_at"] = utc_now()
        state["next_question_id"] = None
        write_json_atomic(state_path, state)
        render_smoke_report(output_dir, config, split, existing_results, metrics)
        return metrics
    state["status"] = "running"
    state["updated_at"] = utc_now()
    write_json_atomic(state_path, state)

    row_by_id = {row["question_id"]: row for row in smoke_rows}
    output_runs = output_dir / "runs"
    output_runs.mkdir(parents=True, exist_ok=True)
    try:
        with server:
            state["model_load_seconds"] = server.load_seconds
            write_json_atomic(state_path, state)
            for question_id in split["smoke_question_ids"]:
                result_path = output_runs / f"{question_id}.json"
                if result_path.is_file():
                    if question_id not in state["completed_question_ids"]:
                        state["completed_question_ids"].append(question_id)
                    continue
                row = row_by_id[question_id]
                context = context_by_id[question_id]
                prompt = render_generation_prompt(row, context)
                try:
                    generation = server.generate(prompt)
                    valid_ids = {item["evidence_id"] for item in context["evidence"]}
                    structured = validate_structured_answer(
                        generation["raw_text"], valid_ids,
                        {item["evidence_id"]: item["text"] for item in context["evidence"]},
                    )
                    rubric = evaluate_rubric(row, structured, config["evaluation"])
                    result = {
                        "schema_version": 1,
                        "question_id": question_id,
                        "question": row["normalized_question"],
                        "book_id": row["book_id"],
                        "difficulty": row["difficulty"],
                        "question_type": row["question_type"],
                        "dependency_flags": {
                            "formula": row["requires_formula"],
                            "visual": row["requires_visual"],
                            "table": row["requires_table"],
                            "multiple_passages": row["requires_multiple_passages"],
                        },
                        "status": "completed",
                        "prompt_sha256": sha256_text(prompt),
                        "context_sha256": context["context_sha256"],
                        "evidence_references": [
                            {key: item[key] for key in (
                                "evidence_id", "source_file", "pdf_page", "textbook_page"
                            )} for item in context["evidence"]
                        ],
                        "generation": generation,
                        "citation_validation": structured,
                        "rubric_evaluation": rubric,
                        "completed_at": utc_now(),
                    }
                    write_json_atomic(result_path, result)
                    state["completed_question_ids"].append(question_id)
                except Exception as exc:  # Preserve the exact failure before stopping the gate.
                    failure = {
                        "schema_version": 1, "question_id": question_id,
                        "question": row["normalized_question"], "status": "failed",
                        "error_type": type(exc).__name__, "error": str(exc),
                        "failed_at": utc_now(),
                    }
                    write_json_atomic(result_path, failure)
                    state["failed_question_ids"].append(question_id)
                    raise
                finally:
                    remaining = [item for item in split["smoke_question_ids"]
                                 if item not in state["completed_question_ids"]]
                    state["next_question_id"] = remaining[0] if remaining else None
                    state["updated_at"] = utc_now()
                    write_json_atomic(state_path, state)
                    rebuild_results_view(output_dir, split["smoke_question_ids"])
    except Exception:
        state["status"] = "interrupted_or_failed"
        state["updated_at"] = utc_now()
        write_json_atomic(state_path, state)
        raise

    results = rebuild_results_view(output_dir, split["smoke_question_ids"])
    metrics = summarize_smoke(results, len(split["smoke_question_ids"]))
    metrics["evaluator"] = EVALUATOR_VERSION
    add_manual_review_metrics(
        metrics, load_manual_reviews(output_dir, split["smoke_question_ids"])
    )
    write_json_atomic(output_dir / "smoke_metrics.json", metrics)
    state["status"] = "complete" if metrics["completed_questions"] == 8 else "incomplete"
    state["updated_at"] = utc_now()
    state["next_question_id"] = None
    state["prompt_comparisons_permitted"] = False
    state["other_model_downloads_permitted"] = False
    write_json_atomic(state_path, state)
    render_smoke_report(output_dir, config, split, results, metrics)
    return metrics


def reevaluate_existing_results(
    root: Path, config_path: Path, output_dir: Path,
) -> dict[str, Any]:
    """Recompute derived citation/rubric fields without invoking the model again."""
    config, split, smoke_rows, context_by_id = prepare_artifacts(root, config_path, output_dir)
    row_by_id = {row["question_id"]: row for row in smoke_rows}
    for question_id in split["smoke_question_ids"]:
        result_path = output_dir / "runs" / f"{question_id}.json"
        if not result_path.is_file():
            raise FileNotFoundError(f"cannot re-evaluate missing result: {result_path}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("status") != "completed":
            raise ValueError(f"cannot re-evaluate failed result: {question_id}")
        context = context_by_id[question_id]
        if result.get("context_sha256") != context["context_sha256"]:
            raise ValueError(f"cannot re-evaluate changed context: {question_id}")
        if "initial_rubric_evaluation" not in result:
            result["initial_rubric_evaluation"] = result["rubric_evaluation"]
        valid_ids = {item["evidence_id"] for item in context["evidence"]}
        structured = validate_structured_answer(
            result["generation"]["raw_text"], valid_ids,
            {item["evidence_id"]: item["text"] for item in context["evidence"]},
        )
        result["citation_validation"] = structured
        result["rubric_evaluation"] = evaluate_rubric(
            row_by_id[question_id], structured, config["evaluation"]
        )
        result["reevaluated_at"] = utc_now()
        write_json_atomic(result_path, result)

    results = rebuild_results_view(output_dir, split["smoke_question_ids"])
    metrics = summarize_smoke(results, len(split["smoke_question_ids"]))
    metrics["evaluator"] = EVALUATOR_VERSION
    reviews = load_manual_reviews(output_dir, split["smoke_question_ids"])
    add_manual_review_metrics(metrics, reviews)
    write_json_atomic(output_dir / "smoke_metrics.json", metrics)
    state_path = output_dir / "experiment_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["evaluator"] = EVALUATOR_VERSION
    state["evaluator_source_sha256"] = sha256_file(Path(__file__))
    state["runner_source_sha256"] = sha256_file(Path(__file__))
    state["reevaluated_at"] = utc_now()
    write_json_atomic(state_path, state)
    render_smoke_report(output_dir, config, split, results, metrics)
    return metrics


def build_parser() -> argparse.ArgumentParser:
    """Create the public CLI for preparation-only and resumable smoke execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--prepare-only", action="store_true",
                        help="Build split and gold-context artifacts without loading a model.")
    parser.add_argument("--reevaluate-only", action="store_true",
                        help="Recompute citation/rubric fields from saved raw answers without inference.")
    parser.add_argument("--llama-server", type=Path,
                        help="Native ARM64 llama-server.exe; required unless --prepare-only.")
    parser.add_argument("--model", type=Path,
                        help="Approved Qwen3-8B Q4_K_M GGUF; required unless --prepare-only.")
    parser.add_argument("--port", type=int, default=18090)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Prepare Phase A artifacts or run/resume the eight-question smoke gate."""
    args = build_parser().parse_args(argv)
    if args.prepare_only:
        config, split, rows, contexts = prepare_artifacts(ROOT, args.config, args.output_dir)
        print(json.dumps({
            "experiment_id": config["experiment_id"],
            "smoke_questions": len(rows),
            "gold_contexts": len(contexts),
            "split": split["counts"],
            "output_dir": str(args.output_dir),
        }, indent=2))
        return
    if args.reevaluate_only:
        metrics = reevaluate_existing_results(ROOT, args.config.resolve(), args.output_dir.resolve())
        print(json.dumps(metrics, indent=2))
        return
    if args.llama_server is None or args.model is None:
        raise SystemExit("--llama-server and --model are required for a smoke run")
    metrics = run_smoke(
        ROOT, args.config.resolve(), args.output_dir.resolve(),
        args.llama_server.resolve(), args.model.resolve(), args.port,
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
