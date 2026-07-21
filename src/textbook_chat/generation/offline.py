"""Resident llama.cpp provider locked to the accepted local generation profile."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterator

from textbook_audit.generation_phase_a import LlamaServerConfig, LocalLlamaServer

from ..config import AppSettings
from ..models.offline import OfflineArtifactRegistry
from .online import (
    GenerationCancelled,
    IncrementalAnswerExtractor,
    ProviderStreamEvent,
)


class OfflineRuntimeManager:
    """Own one verified, CPU-only llama-server and serialize its generations."""

    def __init__(self, settings: AppSettings, artifacts: OfflineArtifactRegistry):
        self.settings = settings
        self.artifacts = artifacts
        config = json.loads(
            (settings.root / "config" / "generation_experiments_v1.json").read_text("utf-8")
        )
        baseline = json.loads(
            (settings.root / "config" / "generation_baseline_v1.json").read_text("utf-8")
        )["profiles"]["local_offline"]
        self.runtime = config["runtime"]
        self.generation = config["generation_defaults"]
        if int(self.generation["max_output_tokens"]) != int(baseline["max_output_tokens"]):
            raise ValueError("offline generation files disagree on the frozen output ceiling")
        if self.runtime["build_number"] != baseline["engine_build"]:
            raise ValueError("offline generation files disagree on llama.cpp build")
        self._state_lock = threading.RLock()
        self._generation_lock = threading.Lock()
        self._server: LocalLlamaServer | None = None

    @property
    def loaded(self) -> bool:
        with self._state_lock:
            return bool(
                self._server and self._server.process and self._server.process.poll() is None
            )

    def preflight(self) -> None:
        """Reject unavailable offline work before a user message is persisted."""

        if self.artifacts.discover() is None:
            error = self.artifacts.compatibility_error()
            raise RuntimeError(error or "Frozen offline provider setup is required.")

    def status(self) -> dict[str, Any]:
        compatibility = self.artifacts.compatibility_error()
        return {
            "state": "loaded" if self.loaded else "unloaded",
            "artifacts_ready": self.artifacts.discover() is not None,
            "compatible": compatibility is None,
            "detail": compatibility or (
                "Offline model is resident in memory." if self.loaded
                else "Offline model loads on first use or through this settings control."
            ),
        }

    def load(self) -> dict[str, Any]:
        """Load on first use and retain the exact model until explicit unload/shutdown."""

        with self._state_lock:
            if self.loaded:
                return {"state": "loaded", "load_seconds": self._server.load_seconds}
            resolved = self.artifacts.discover()
            if resolved is None:
                error = self.artifacts.compatibility_error()
                raise RuntimeError(error or "Frozen offline provider setup is required.")
            server = LocalLlamaServer(LlamaServerConfig(
                executable=resolved.server_path,
                model=resolved.model_path,
                port=_free_loopback_port(),
                runtime=self.runtime,
                generation=self.generation,
                log_dir=self.settings.data_dir / "logs" / "llama",
            ))
            try:
                server.start(timeout_seconds=180)
            except Exception:
                server.stop()
                raise
            self._server = server
            return {"state": "loaded", "load_seconds": server.load_seconds}

    def unload(self) -> dict[str, Any]:
        """Release RAM only when no generation owns the single offline slot."""

        if not self._generation_lock.acquire(blocking=False):
            raise RuntimeError("Offline generation is active; stop or wait for it before unloading.")
        try:
            with self._state_lock:
                if self._server:
                    self._server.stop()
                    self._server = None
            return {"state": "unloaded"}
        finally:
            self._generation_lock.release()

    def shutdown(self) -> None:
        with self._generation_lock:
            with self._state_lock:
                if self._server:
                    self._server.stop()
                    self._server = None

    def request_payload(self, prompt: str) -> dict[str, Any]:
        """Return the frozen OpenAI-compatible llama.cpp request contract."""

        return {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(self.generation["temperature"]),
            "seed": int(self.generation["seed"]),
            "max_tokens": int(self.generation["max_output_tokens"]),
            "stream": True,
            "stream_options": {"include_usage": True},
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": bool(self.generation["thinking"])},
        }

    def stream(
        self, prompt: str, cancel: threading.Event | None = None
    ) -> Iterator[ProviderStreamEvent]:
        """Stream content deltas from the one resident offline server slot."""

        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        if cancel is not None and cancel.is_set():
            raise GenerationCancelled("generation cancelled by user")
        with self._generation_lock:
            load = self.load()
            server = self._server
            if server is None:
                raise RuntimeError("offline runtime did not become ready")
            yield ProviderStreamEvent("started", {
                "model": self.artifacts.model_filename,
                "load_seconds": load["load_seconds"],
            })
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.config.port}/v1/chat/completions",
                data=json.dumps(self.request_payload(prompt)).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            started = time.perf_counter()
            first_delta_at: float | None = None
            raw_parts: list[str] = []
            usage: dict[str, Any] = {}
            response_id: str | None = None
            extractor = IncrementalAnswerExtractor()
            with urllib.request.urlopen(request, timeout=600) as response:
                for raw_line in response:
                    if cancel is not None and cancel.is_set():
                        raise GenerationCancelled("generation cancelled by user")
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
                    content = str(delta.get("content") or "")
                    # Reasoning content is timing-only and is never stored or sent to the UI.
                    observed = content or delta.get("reasoning_content")
                    if observed and first_delta_at is None:
                        first_delta_at = time.perf_counter()
                    if not content:
                        continue
                    raw_parts.append(content)
                    yield ProviderStreamEvent("raw_delta", {"delta": content})
                    answer_delta = extractor.feed(content)
                    if answer_delta:
                        yield ProviderStreamEvent("answer_delta", {"delta": answer_delta})
            elapsed = time.perf_counter() - started
            yield ProviderStreamEvent("completed", {
                "raw_text": "".join(raw_parts),
                "latency_seconds": round(elapsed, 4),
                "time_to_first_token_seconds": (
                    round(first_delta_at - started, 4) if first_delta_at is not None else None
                ),
                "response_id": response_id,
                "response_status": "completed",
                "resolved_model": (
                    f"{self.artifacts.model_filename} · llama.cpp b{self.runtime['build_number']}"
                ),
                "usage": {
                    "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                    "total_tokens": int(usage.get("total_tokens", 0) or 0),
                },
            })


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
