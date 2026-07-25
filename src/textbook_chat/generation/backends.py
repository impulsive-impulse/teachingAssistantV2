"""Backend-specific llama.cpp launch and initialization validation."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from textbook_audit.generation_phase_a import LocalLlamaServer

from ..config import OfflineBackend
from ..models.offline import CPU_RUNTIME_SPEC, OPENCL_RUNTIME_SPEC, OfflineArtifacts


EXPECTED_QWEN3_8B_LAYERS = 37
ADRENO_DEVICE = "Qualcomm(R) Adreno(TM) X1-85 GPU"


class BackendInitializationError(RuntimeError):
    """The selected runtime started but did not prove the requested backend."""


@dataclass(frozen=True)
class BackendInitialization:
    requested_backend: OfflineBackend
    active_backend: OfflineBackend
    runtime_build: int
    selected_device: str
    offloaded_layers: int
    expected_layers: int
    initialization_status: str
    fallback_used: bool = False
    initialization_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_backend": self.requested_backend,
            "active_backend": self.active_backend,
            "runtime_build": self.runtime_build,
            "selected_device": self.selected_device,
            "offloaded_layer_count": self.offloaded_layers,
            "expected_layer_count": self.expected_layers,
            "initialization_status": self.initialization_status,
            "fallback_used": self.fallback_used,
            "initialization_error": self.initialization_error,
        }


class OfflineBackendStrategy(ABC):
    """Keep backend launch differences outside the shared generation provider."""

    name: OfflineBackend

    @abstractmethod
    def runtime_config(self, shared_runtime: dict[str, Any]) -> dict[str, Any]:
        """Return execution settings without changing shared generation settings."""

    @abstractmethod
    def extra_arguments(self) -> tuple[str, ...]:
        """Return backend-only llama.cpp arguments."""

    @abstractmethod
    def validate_initialization(
        self, server: LocalLlamaServer, artifacts: OfflineArtifacts
    ) -> BackendInitialization:
        """Prove that the requested backend initialized as intended."""


class CpuBackendStrategy(OfflineBackendStrategy):
    name: OfflineBackend = "cpu"

    def runtime_config(self, shared_runtime: dict[str, Any]) -> dict[str, Any]:
        return dict(shared_runtime)

    def extra_arguments(self) -> tuple[str, ...]:
        return ()

    def validate_initialization(
        self, server: LocalLlamaServer, artifacts: OfflineArtifacts
    ) -> BackendInitialization:
        del server
        if artifacts.runtime_build != CPU_RUNTIME_SPEC.build_number:
            raise BackendInitializationError(
                f"CPU runtime build mismatch: expected {CPU_RUNTIME_SPEC.build_number}, "
                f"found {artifacts.runtime_build}."
            )
        return BackendInitialization(
            requested_backend="cpu",
            active_backend="cpu",
            runtime_build=artifacts.runtime_build,
            selected_device="CPU",
            offloaded_layers=0,
            expected_layers=0,
            initialization_status="ready",
        )


class OpenCLGpuBackendStrategy(OfflineBackendStrategy):
    name: OfflineBackend = "opencl_gpu"

    def runtime_config(self, shared_runtime: dict[str, Any]) -> dict[str, Any]:
        runtime = dict(shared_runtime)
        runtime.update({
            "build_number": OPENCL_RUNTIME_SPEC.build_number,
            "build_commit": OPENCL_RUNTIME_SPEC.commit,
            "backend": "opencl_gpu",
            "gpu_layers": 99,
        })
        return runtime

    def extra_arguments(self) -> tuple[str, ...]:
        return ("--device", "GPUOpenCL", "--log-verbosity", "5")

    def validate_initialization(
        self, server: LocalLlamaServer, artifacts: OfflineArtifacts
    ) -> BackendInitialization:
        if artifacts.runtime_build != OPENCL_RUNTIME_SPEC.build_number:
            raise BackendInitializationError(
                f"OpenCL runtime build mismatch: expected {OPENCL_RUNTIME_SPEC.build_number}, "
                f"found {artifacts.runtime_build}."
            )
        return parse_opencl_initialization(server.stderr_session_text())


def parse_opencl_initialization(log_text: str) -> BackendInitialization:
    """Require device selection, OpenCL loading, and complete Qwen3-8B offload."""

    missing: list[str] = []
    if "using device GPUOpenCL" not in log_text or ADRENO_DEVICE not in log_text:
        missing.append(f"{ADRENO_DEVICE} was not selected")
    if "using kernels optimized for Adreno" not in log_text:
        missing.append("Adreno-optimized OpenCL kernels were not enabled")
    matches = re.findall(r"offloaded\s+(\d+)/(\d+)\s+layers to GPU", log_text)
    offloaded, total = (map(int, matches[-1]) if matches else (0, 0))
    if not matches:
        missing.append("llama.cpp did not report layer offload")
    elif total != EXPECTED_QWEN3_8B_LAYERS or offloaded != total:
        missing.append(
            f"expected {EXPECTED_QWEN3_8B_LAYERS}/{EXPECTED_QWEN3_8B_LAYERS} "
            f"Qwen3-8B layers on GPU, observed {offloaded}/{total}"
        )
    if missing:
        raise BackendInitializationError(
            "OpenCL GPU initialization validation failed: " + "; ".join(missing)
            + ". CPU fallback is disabled unless offline_generation.allow_fallback is true."
        )
    return BackendInitialization(
        requested_backend="opencl_gpu",
        active_backend="opencl_gpu",
        runtime_build=OPENCL_RUNTIME_SPEC.build_number,
        selected_device=ADRENO_DEVICE,
        offloaded_layers=offloaded,
        expected_layers=EXPECTED_QWEN3_8B_LAYERS,
        initialization_status="ready",
    )


def backend_strategy(backend: OfflineBackend) -> OfflineBackendStrategy:
    """Resolve the feature gate once when the backend server starts."""

    if backend == "cpu":
        return CpuBackendStrategy()
    if backend == "opencl_gpu":
        return OpenCLGpuBackendStrategy()
    raise ValueError(f"unsupported offline generation backend: {backend}")
