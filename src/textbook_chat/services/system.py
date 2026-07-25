"""Readiness checks that are safe to expose to the local browser."""

from __future__ import annotations

import importlib.util
import platform
from pathlib import Path

import psutil

from ..config import AppSettings, validate_frozen_configs
from ..database import Database, SCHEMA_VERSION
from ..models.embedding import EmbeddingArtifactRegistry
from ..models.offline import OfflineArtifactRegistry
from ..schemas import ComponentStatus, FrozenProfiles, SystemStatusResponse


def _gib(value: int) -> str:
    return f"{value / (1024 ** 3):.1f} GiB"


class SystemStatusService:
    """Combine fast local checks without downloading models or making paid calls."""

    def __init__(
        self, settings: AppSettings, database: Database,
        embedding_registry: EmbeddingArtifactRegistry,
        offline_registry: OfflineArtifactRegistry,
    ):
        self.settings = settings
        self.database = database
        self.embedding_registry = embedding_registry
        self.offline_registry = offline_registry

    def status(self) -> SystemStatusResponse:
        profiles = validate_frozen_configs(self.settings)
        storage = self._storage_status()
        embedding = self._embedding_status()
        offline = self._offline_status()
        online = (
            ComponentStatus(state="ready", detail="API key and OpenAI SDK are available.")
            if self.settings.openai_api_key_present and importlib.util.find_spec("openai")
            else ComponentStatus(
                state="unavailable",
                detail=("OpenAI SDK is not installed." if importlib.util.find_spec("openai") is None
                        else "OPENAI_API_KEY is missing from the environment or .env."),
            )
        )
        memory = psutil.virtual_memory()
        return SystemStatusResponse(
            application=ComponentStatus(state="ready", detail="Local application is running."),
            database=ComponentStatus(state="ready", detail=f"SQLite schema v{SCHEMA_VERSION} is ready."),
            storage=storage,
            frozen_configs=ComponentStatus(
                state="ready", detail="Retrieval Baseline v1 and Generation Baseline v1 validated."
            ),
            embedding_model=embedding,
            online_provider=online,
            offline_provider=offline,
            cpu=f"{platform.processor() or platform.machine()} · {psutil.cpu_count(logical=True)} logical CPUs",
            memory=f"{_gib(memory.available)} available of {_gib(memory.total)}",
            profiles=FrozenProfiles(
                retrieval="Retrieval Baseline v1 · uploaded-textbook derived runtime",
                online_model=profiles.online_model,
                online_max_output_tokens=profiles.online_max_output_tokens,
                offline_model=profiles.offline_model,
                offline_max_output_tokens=profiles.offline_max_output_tokens,
            ),
        )

    def _storage_status(self) -> ComponentStatus:
        probe = self.settings.data_dir / ".write_probe"
        try:
            probe.write_text("ready", encoding="utf-8")
            probe.unlink()
            return ComponentStatus(state="ready", detail="Application-data directory is writable.")
        except OSError:
            return ComponentStatus(state="error", detail="Application-data directory is not writable.")

    def _embedding_status(self) -> ComponentStatus:
        artifact = self.embedding_registry.discover()
        if not artifact:
            return ComponentStatus(
                state="setup_required",
                detail="Pinned BGE embedding snapshot is missing or failed integrity verification.",
            )
        model_runtime = importlib.util.find_spec("sentence_transformers") is not None
        if not model_runtime:
            return ComponentStatus(
                state="unavailable",
                detail="Pinned BGE files are verified, but the Sentence Transformers runtime is unavailable.",
            )
        return ComponentStatus(
            state="ready",
            detail=f"Pinned BGE snapshot verified ({artifact.size_bytes / (1024 ** 2):.1f} MiB).",
        )

    def _offline_status(self) -> ComponentStatus:
        compatibility = self.offline_registry.compatibility_error()
        if compatibility:
            return ComponentStatus(state="unavailable", detail=compatibility)
        artifacts = self.offline_registry.discover()
        if artifacts:
            return ComponentStatus(
                state="ready",
                detail=(
                    f"Qwen SHA-256 and {artifacts.backend} llama.cpp build "
                    f"{artifacts.runtime_build} manifest are verified."
                ),
            )
        if (
            self.settings.offline_generation.backend == "opencl_gpu"
            and self.settings.offline_generation.allow_fallback
        ):
            cpu_artifacts = self.offline_registry.discover("cpu")
            if cpu_artifacts:
                return ComponentStatus(
                    state="ready",
                    detail=(
                        "OpenCL runtime is not ready; explicit CPU fallback is enabled "
                        f"and verified at llama.cpp build {cpu_artifacts.runtime_build}."
                    ),
                )
        return ComponentStatus(
            state="setup_required",
            detail=(
                self.offline_registry.artifact_error()
                or "Pinned Qwen model or llama.cpp runtime requires setup."
            ),
        )
