"""Typed HTTP request and response contracts.

The API never returns filesystem paths, API keys, or internal exception text in
normal responses.  Diagnostics requiring more detail use a separate endpoint.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .domain import Backend


class StrictModel(BaseModel):
    """Reject accidental fields so the browser cannot broaden operation scope."""

    model_config = ConfigDict(extra="forbid")


class PublicModel(BaseModel):
    """Ignore internal repository columns that are deliberately not serialized."""

    model_config = ConfigDict(extra="ignore")


class ComponentStatus(PublicModel):
    state: Literal["ready", "unavailable", "setup_required", "error"]
    detail: str


class FrozenProfiles(PublicModel):
    retrieval: str
    online_model: str
    online_max_output_tokens: int
    offline_model: str
    offline_max_output_tokens: int


class SystemStatusResponse(PublicModel):
    application: ComponentStatus
    database: ComponentStatus
    storage: ComponentStatus
    frozen_configs: ComponentStatus
    embedding_model: ComponentStatus
    online_provider: ComponentStatus
    offline_provider: ComponentStatus
    cpu: str
    memory: str
    profiles: FrozenProfiles


class ModelSetupJobResponse(PublicModel):
    id: str
    component: str
    state: str
    stage: str
    progress: float
    downloaded_bytes: int
    total_bytes: int | None = None
    error_code: str | None = None
    user_message: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class IngestionJobResponse(PublicModel):
    id: str
    checksum: str
    book_id: str | None = None
    stage: str
    stage_progress: float
    overall_progress: float
    state: str
    error_code: str | None = None
    user_message: str | None = None
    started_at: str | None = None
    updated_at: str
    completed_at: str | None = None


class BookResponse(PublicModel):
    id: str
    book_id: str
    sha256: str
    original_filename: str
    title: str
    status: str
    status_reason: str | None = None
    page_count: int | None = None
    searchable_page_count: int | None = None
    chapter_count: int | None = None
    ingestion_policy_version: str
    runtime_profile_version: str
    created_at: str
    indexed_at: str | None = None
    last_opened_at: str | None = None
    current_job: IngestionJobResponse | None = None


class UploadResponse(PublicModel):
    disposition: Literal["created", "duplicate_ready", "duplicate_active"]
    book: BookResponse
    job: IngestionJobResponse | None = None


class ChatCreateRequest(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=120)] = "New chat"
    default_backend: Backend = Backend.ONLINE


class ChatResponse(PublicModel):
    id: str
    book_id: str
    title: str
    default_backend: Backend
    created_at: str
    updated_at: str


class ChatUpdateRequest(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    default_backend: Backend | None = None


class MessageCreateRequest(StrictModel):
    question: Annotated[str, Field(min_length=1, max_length=4000)]
    backend: Backend | None = None
    online_disclosure_acknowledged: bool = False


class RegenerateRequest(StrictModel):
    backend: Backend
    online_disclosure_acknowledged: bool = False


class AttemptResponse(PublicModel):
    id: str
    message_id: str
    retrieval_snapshot_id: str | None = None
    backend: Backend
    state: str
    prompt_checksum: str | None = None
    output: dict | None = None
    provider_identity: str | None = None
    usage: dict | None = None
    timing: dict | None = None
    validation: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str
    completed_at: str | None = None


class MessageAcceptedResponse(PublicModel):
    message: dict
    attempt: AttemptResponse
