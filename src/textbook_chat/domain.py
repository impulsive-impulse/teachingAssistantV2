"""Application domain values shared by persistence, services, and HTTP APIs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BookStatus(StrEnum):
    """Durable lifecycle states visible in the library."""

    VALIDATING = "validating"
    PROCESSING = "processing"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    DELETING = "deleting"


class JobState(StrEnum):
    """Terminal and non-terminal states for ingestion work."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Backend(StrEnum):
    """Locked generation profiles exposed to chats."""

    ONLINE = "online"
    OFFLINE = "offline"


class AttemptState(StrEnum):
    """Lifecycle of one answer attempt."""

    QUEUED = "queued"
    RETRIEVING = "retrieving"
    GENERATING = "generating"
    VALIDATING = "validating"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class FrozenProfileSummary:
    """Safe, public model metadata read from the frozen generation config."""

    online_model: str
    online_max_output_tokens: int
    offline_model: str
    offline_max_output_tokens: int
