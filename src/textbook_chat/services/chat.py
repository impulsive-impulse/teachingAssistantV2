"""Durable independent-question orchestration and live attempt events."""

from __future__ import annotations

import threading
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Protocol

from ..domain import AttemptState, Backend
from ..generation.online import (
    GenerationCancelled,
    OnlineGenerationProvider,
    OnlineProfile,
    ProviderStreamEvent,
)
from ..generation.prompt import build_prompt, validate_answer
from ..repositories import ChatRepository


class StreamingProvider(Protocol):
    def stream(self, prompt: str, cancel: threading.Event | None = None) -> Iterator[ProviderStreamEvent]: ...


@dataclass(frozen=True)
class AttemptEvent:
    sequence: int
    type: str
    data: dict[str, Any]


class AttemptEventHub:
    """Small in-process live-event buffer; SQLite remains the durable authority."""

    TERMINAL = {"completed", "failed", "cancelled"}

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._events: dict[str, list[AttemptEvent]] = {}

    def publish(self, attempt_uuid: str, event_type: str, data: dict[str, Any] | None = None) -> None:
        with self._condition:
            events = self._events.setdefault(attempt_uuid, [])
            events.append(AttemptEvent(len(events) + 1, event_type, data or {}))
            self._condition.notify_all()

    def stream(self, attempt_uuid: str, after: int = 0) -> Iterator[AttemptEvent | None]:
        cursor = max(0, after)
        while True:
            heartbeat = False
            with self._condition:
                events = self._events.get(attempt_uuid, [])
                pending = [event for event in events if event.sequence > cursor]
                if not pending:
                    self._condition.wait(timeout=15)
                    events = self._events.get(attempt_uuid, [])
                    pending = [event for event in events if event.sequence > cursor]
                if not pending:
                    heartbeat = True
            if heartbeat:
                yield None
                continue
            for event in pending:
                cursor = event.sequence
                yield event
                if event.type in self.TERMINAL:
                    return


class GenerationProviderRegistry:
    """Resolve an explicit backend without automatic cross-provider fallback."""

    def __init__(self, root, offline_provider: StreamingProvider | None = None):
        self.online_profile = OnlineProfile.load(root)
        self.offline_provider = offline_provider
        self._online: OnlineGenerationProvider | None = None
        self._lock = threading.Lock()

    def resolve(self, backend: Backend) -> StreamingProvider:
        if backend is Backend.OFFLINE:
            if self.offline_provider is None:
                raise RuntimeError("The frozen offline runtime is not ready on this machine.")
            preflight = getattr(self.offline_provider, "preflight", None)
            if callable(preflight):
                preflight()
            return self.offline_provider
        with self._lock:
            if self._online is None:
                self._online = OnlineGenerationProvider(self.online_profile)
            return self._online


class ChatCoordinator:
    """Run retrieval once per message and generation once per answer attempt."""

    def __init__(
        self,
        repository: ChatRepository,
        runtime_for_book: Callable[[dict[str, Any]], Any],
        provider_for_backend: Callable[[Backend], StreamingProvider],
        *,
        max_workers: int = 2,
    ):
        self.repository = repository
        self.runtime_for_book = runtime_for_book
        self.provider_for_backend = provider_for_backend
        self.events = AttemptEventHub()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="textbook-answer")
        self._lock = threading.Lock()
        self._active: dict[str, tuple[Future[None], threading.Event]] = {}
        self._closed = False

    def start(self) -> None:
        """Close out attempts that could not survive a previous process exit."""

        self.repository.interrupt_active_attempts()

    def submit_message(
        self, chat_uuid: str, question: str, backend: Backend | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        chat = self.repository.get(chat_uuid)
        if not chat:
            raise LookupError("chat not found")
        selected = backend or Backend(chat["default_backend"])
        provider = self.provider_for_backend(selected)
        message, attempt = self.repository.create_message_attempt(chat_uuid, question, selected)
        self.events.publish(attempt["id"], "queued", {"backend": selected.value})
        self._submit(attempt["id"], provider, retrieve=True)
        return message, attempt

    def regenerate(self, message_uuid: str, backend: Backend) -> dict[str, Any]:
        provider = self.provider_for_backend(backend)
        attempt = self.repository.create_regeneration(message_uuid, backend)
        self.events.publish(attempt["id"], "queued", {"backend": backend.value, "reuse": True})
        self._submit(attempt["id"], provider, retrieve=False)
        return attempt

    def cancel(self, attempt_uuid: str) -> bool:
        with self._lock:
            active = self._active.get(attempt_uuid)
            if active:
                active[1].set()
        cancelled = self.repository.cancel_attempt(attempt_uuid)
        if cancelled:
            self.events.publish(attempt_uuid, "cancelled", {})
        return cancelled

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            for _future, cancellation in self._active.values():
                cancellation.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _submit(self, attempt_uuid: str, provider: StreamingProvider, *, retrieve: bool) -> None:
        cancellation = threading.Event()
        with self._lock:
            if self._closed:
                raise RuntimeError("answer coordinator is shutting down")
            future = self._executor.submit(self._run, attempt_uuid, provider, cancellation, retrieve)
            self._active[attempt_uuid] = (future, cancellation)
            future.add_done_callback(lambda _future, key=attempt_uuid: self._finished(key))

    def _finished(self, attempt_uuid: str) -> None:
        with self._lock:
            self._active.pop(attempt_uuid, None)

    def _run(
        self,
        attempt_uuid: str,
        provider: StreamingProvider,
        cancellation: threading.Event,
        retrieve: bool,
    ) -> None:
        try:
            attempt = self.repository.get_attempt(attempt_uuid)
            if not attempt:
                return
            if cancellation.is_set():
                raise GenerationCancelled("generation cancelled by user")
            if retrieve:
                if not self.repository.set_attempt_state(attempt_uuid, AttemptState.RETRIEVING):
                    return
                self.events.publish(attempt_uuid, "retrieval_started", {})
                runtime = self.runtime_for_book(attempt)
                snapshot_data = runtime.retrieve(attempt["question"])
                if cancellation.is_set():
                    raise GenerationCancelled("generation cancelled by user")
                snapshot = snapshot_data.to_dict()
                self.repository.persist_retrieval_snapshot(attempt_uuid, snapshot)
                self.events.publish(attempt_uuid, "retrieval_completed", {
                    "latency_ms": snapshot["retrieval_latency_ms"],
                    "evidence_count": len(snapshot["evidence"]),
                    "snapshot_checksum": snapshot["checksum"],
                })
            else:
                snapshot = self.repository.get_snapshot_for_attempt(attempt_uuid)
                if snapshot is None:
                    raise RuntimeError("regeneration retrieval snapshot is unavailable")

            package = build_prompt(snapshot)
            if cancellation.is_set():
                raise GenerationCancelled("generation cancelled by user")
            self.repository.set_prompt_checksum(attempt_uuid, package.checksum)
            if not self.repository.set_attempt_state(attempt_uuid, AttemptState.GENERATING):
                return
            self.events.publish(attempt_uuid, "generation_started", {
                "backend": attempt["backend"], "prompt_checksum": package.checksum,
            })
            completion: dict[str, Any] | None = None
            for event in provider.stream(package.prompt, cancellation):
                if event.type == "answer_delta":
                    self.events.publish(attempt_uuid, "answer_delta", event.data)
                elif event.type == "completed":
                    completion = event.data
            if completion is None:
                raise RuntimeError("generation stream ended without a completion event")
            if not self.repository.set_attempt_state(attempt_uuid, AttemptState.VALIDATING):
                return
            self.events.publish(attempt_uuid, "validation_started", {})
            validation = validate_answer(completion["raw_text"], package)
            if not validation["valid"]:
                self.repository.fail_validation(
                    attempt_uuid,
                    raw_output=completion["raw_text"],
                    provider_identity=str(completion.get("resolved_model") or attempt["backend"]),
                    usage=completion.get("usage") or {},
                    timing={
                        "latency_seconds": completion.get("latency_seconds"),
                        "time_to_first_token_seconds": completion.get("time_to_first_token_seconds"),
                    },
                    validation=validation,
                )
                self.events.publish(attempt_uuid, "failed", {
                    "code": "structured_output_invalid", "validation_errors": validation["errors"],
                })
                return
            output = {key: validation[key] for key in (
                "status", "answer", "selected_evidence_ids", "citations", "missing_information"
            )}
            completed = self.repository.complete_attempt(
                attempt_uuid,
                raw_output=completion["raw_text"],
                output=output,
                provider_identity=str(completion.get("resolved_model") or attempt["backend"]),
                usage=completion.get("usage") or {},
                timing={
                    "latency_seconds": completion.get("latency_seconds"),
                    "time_to_first_token_seconds": completion.get("time_to_first_token_seconds"),
                },
                validation=validation,
            )
            if completed:
                self.events.publish(attempt_uuid, "completed", {"output": output})
        except GenerationCancelled:
            if self.repository.cancel_attempt(attempt_uuid):
                self.events.publish(attempt_uuid, "cancelled", {})
        except Exception as exc:
            self.repository.fail_attempt(
                attempt_uuid, "answer_pipeline_failed", _safe_error(exc)
            )
            self.events.publish(attempt_uuid, "failed", {
                "code": "answer_pipeline_failed", "message": _safe_error(exc),
            })
            # Preserve traceback in local worker logs without exposing it via HTTP events.
            traceback.print_exc()


def _safe_error(error: Exception) -> str:
    safe_messages = {
        "the pinned BGE embedding artifact is not installed",
        "generation stream ended without a completion event",
        "regeneration retrieval snapshot is unavailable",
        "attempt is no longer active",
    }
    if str(error).lower() in safe_messages:
        return str(error)[:300]
    return "The answer pipeline failed. Check local diagnostics and try again."
