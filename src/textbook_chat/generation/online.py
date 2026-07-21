"""Streaming OpenAI adapter locked to Generation Baseline v1.

The adapter emits provider-neutral events for the chat orchestrator.  It makes
one Responses API request, disables SDK retries, and applies the exact frozen
structured-output schema.  It never falls back to another provider or model.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Iterator, Literal

from textbook_audit.openai_generation import answer_json_schema


@dataclass(frozen=True)
class OnlineProfile:
    """All behavior-affecting online settings, resolved from frozen files."""

    model: str
    max_output_tokens: int
    temperature: float
    timeout_seconds: float
    max_retries: int
    api_key_environment_variable: str
    base_url_environment_variable: str

    @classmethod
    def load(cls, root: Path) -> "OnlineProfile":
        baseline = json.loads((root / "config" / "generation_baseline_v1.json").read_text("utf-8"))
        experiment = json.loads(
            (root / "config" / "openai_generation_experiments_v1.json").read_text("utf-8")
        )
        shared = baseline["shared_pipeline"]
        frozen = experiment["frozen_configuration"]
        provider = experiment["provider"]
        profile = baseline["profiles"]["online_quality"]
        invariants = {
            "prompt_strategy": (shared["prompt_strategy"], frozen["prompt_strategy"]),
            "context_strategy": (
                shared["retrieved_context_strategy"], frozen["retrieved_context_strategy"]
            ),
            "max_output_tokens": (profile["max_output_tokens"], frozen["max_output_tokens"]),
            "temperature": (shared["temperature"], frozen["temperature"]),
            "retries": (profile["retries"], provider["max_retries"]),
        }
        drift = [name for name, pair in invariants.items() if pair[0] != pair[1]]
        if drift:
            raise ValueError(f"online generation files disagree on frozen fields: {', '.join(drift)}")
        return cls(
            model=profile["resolved_and_frozen_model"],
            max_output_tokens=int(profile["max_output_tokens"]),
            temperature=float(shared["temperature"]),
            timeout_seconds=float(provider["timeout_seconds"]),
            max_retries=int(profile["retries"]),
            api_key_environment_variable=provider["api_key_environment_variable"],
            base_url_environment_variable=provider["base_url_environment_variable"],
        )


@dataclass(frozen=True)
class ProviderStreamEvent:
    """One provider-neutral generation lifecycle event."""

    type: Literal["started", "raw_delta", "answer_delta", "completed"]
    data: dict[str, Any]


class OnlineGenerationProvider:
    """OpenAI Responses streaming implementation with an injectable client."""

    def __init__(self, profile: OnlineProfile, client: Any | None = None):
        self.profile = profile
        if client is not None:
            self.client = client
            return
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI SDK is missing; install the online-generation optional dependency"
            ) from exc
        api_key = os.getenv(profile.api_key_environment_variable, "").strip()
        if not api_key:
            raise RuntimeError(f"{profile.api_key_environment_variable} is not configured")
        kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": profile.timeout_seconds,
            "max_retries": profile.max_retries,
        }
        base_url = os.getenv(profile.base_url_environment_variable, "").strip()
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)

    def stream(self, prompt: str, cancel: Event | None = None) -> Iterator[ProviderStreamEvent]:
        """Stream one structured response; cancellation never starts a retry."""

        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        started = time.perf_counter()
        first_delta_at: float | None = None
        raw_parts: list[str] = []
        final_response: Any = None
        extractor = IncrementalAnswerExtractor()
        stream = self.client.responses.create(
            model=self.profile.model,
            input=prompt,
            temperature=self.profile.temperature,
            max_output_tokens=self.profile.max_output_tokens,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "grounded_textbook_answer",
                    "strict": True,
                    "schema": answer_json_schema(),
                }
            },
            stream=True,
        )
        yield ProviderStreamEvent("started", {"model": self.profile.model})
        try:
            for event in stream:
                if cancel is not None and cancel.is_set():
                    raise GenerationCancelled("generation cancelled by user")
                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    delta = str(getattr(event, "delta", "") or "")
                    if not delta:
                        continue
                    if first_delta_at is None:
                        first_delta_at = time.perf_counter()
                    raw_parts.append(delta)
                    yield ProviderStreamEvent("raw_delta", {"delta": delta})
                    answer_delta = extractor.feed(delta)
                    if answer_delta:
                        yield ProviderStreamEvent("answer_delta", {"delta": answer_delta})
                elif event_type == "response.completed":
                    final_response = getattr(event, "response", None)
                elif event_type in {"response.failed", "error"}:
                    error = getattr(event, "error", None)
                    raise RuntimeError(f"OpenAI streaming response failed: {error or event_type}")
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()

        elapsed = time.perf_counter() - started
        usage = getattr(final_response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        yield ProviderStreamEvent(
            "completed",
            {
                "raw_text": "".join(raw_parts),
                "latency_seconds": round(elapsed, 4),
                "time_to_first_token_seconds": (
                    round(first_delta_at - started, 4) if first_delta_at is not None else None
                ),
                "response_id": getattr(final_response, "id", None),
                "response_status": getattr(final_response, "status", None),
                "resolved_model": getattr(final_response, "model", self.profile.model),
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": int(
                        getattr(usage, "total_tokens", input_tokens + output_tokens) or 0
                    ),
                },
            },
        )


class GenerationCancelled(RuntimeError):
    """Raised when the caller cancels an in-flight provider stream."""


class IncrementalAnswerExtractor:
    """Incrementally decode only the top-level JSON `answer` string.

    Raw structured JSON remains the source of truth and is validated after the
    stream.  This small state machine merely provides safe, unescaped answer
    deltas for the UI while the JSON object is incomplete.
    """

    _ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}

    def __init__(self) -> None:
        self._buffer = ""
        self._cursor = 0
        self._stage = "key"
        self._escape = False
        self._unicode = ""

    def feed(self, chunk: str) -> str:
        if self._stage == "done" or not chunk:
            return ""
        self._buffer += chunk
        output: list[str] = []
        if self._stage == "key":
            marker = self._buffer.find('"answer"')
            if marker < 0:
                # Retain enough suffix for a marker split across network chunks.
                if len(self._buffer) > 64:
                    self._buffer = self._buffer[-16:]
                return ""
            self._cursor = marker + len('"answer"')
            self._stage = "colon"

        while self._cursor < len(self._buffer) and self._stage != "done":
            character = self._buffer[self._cursor]
            self._cursor += 1
            if self._stage == "colon":
                if character.isspace():
                    continue
                if character != ":":
                    self._stage = "done"
                    break
                self._stage = "quote"
            elif self._stage == "quote":
                if character.isspace():
                    continue
                if character != '"':
                    self._stage = "done"
                    break
                self._stage = "value"
            elif self._unicode:
                self._unicode += character
                if len(self._unicode) == 4:
                    try:
                        output.append(chr(int(self._unicode, 16)))
                    except ValueError:
                        self._stage = "done"
                    self._unicode = ""
                    self._escape = False
            elif self._escape:
                if character == "u":
                    self._unicode = ""
                elif character in self._ESCAPES:
                    output.append(self._ESCAPES[character])
                    self._escape = False
                else:
                    self._stage = "done"
            elif character == "\\":
                self._escape = True
            elif character == '"':
                self._stage = "done"
            else:
                output.append(character)

        if self._cursor > 4096:
            self._buffer = self._buffer[self._cursor :]
            self._cursor = 0
        return "".join(output)
