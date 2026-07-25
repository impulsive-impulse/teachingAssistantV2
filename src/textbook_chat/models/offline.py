"""Exact artifact identities for the frozen Windows ARM64 offline provider."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import AppSettings, OfflineBackend


LLAMA_ARCHIVE_NAME = "llama-b10046-bin-win-cpu-arm64.zip"
LLAMA_ARCHIVE_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/b10046/"
    + LLAMA_ARCHIVE_NAME
)
LLAMA_ARCHIVE_SHA256 = "7f9958be4bdfc110c4eaa7bb49eeb115573d44d80a8b9400063bc49336923f1c"
LLAMA_OPENCL_ARCHIVE_NAME = "llama-b10107-bin-win-opencl-adreno-arm64.zip"
LLAMA_OPENCL_ARCHIVE_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/b10107/"
    + LLAMA_OPENCL_ARCHIVE_NAME
)
LLAMA_OPENCL_ARCHIVE_SHA256 = (
    "1adca072b5ef8203409bb75258faa5ab7476d93fcf1bd38fbc44cb68cb3b1eef"
)


@dataclass(frozen=True)
class RuntimeArtifactSpec:
    backend: OfflineBackend
    build_number: int
    commit: str
    archive_name: str
    archive_url: str
    archive_sha256: str
    required_files: tuple[str, ...]


CPU_RUNTIME_SPEC = RuntimeArtifactSpec(
    backend="cpu",
    build_number=10046,
    commit="32e789fdfd598e9a1872da55ac941e4d94f030bd",
    archive_name=LLAMA_ARCHIVE_NAME,
    archive_url=LLAMA_ARCHIVE_URL,
    archive_sha256=LLAMA_ARCHIVE_SHA256,
    required_files=("llama-server.exe",),
)
OPENCL_RUNTIME_SPEC = RuntimeArtifactSpec(
    backend="opencl_gpu",
    build_number=10107,
    commit="c0bc8591e",
    archive_name=LLAMA_OPENCL_ARCHIVE_NAME,
    archive_url=LLAMA_OPENCL_ARCHIVE_URL,
    archive_sha256=LLAMA_OPENCL_ARCHIVE_SHA256,
    required_files=("llama-server.exe", "ggml-opencl.dll"),
)


@dataclass(frozen=True)
class OfflineArtifacts:
    model_path: Path
    server_path: Path
    model_size_bytes: int
    runtime_manifest: Path
    backend: OfflineBackend
    runtime_build: int


class OfflineArtifactRegistry:
    """Discover only the model and engine used by Generation Baseline v1."""

    def __init__(self, settings: AppSettings):
        self.settings = settings
        baseline = json.loads(
            (settings.root / "config" / "generation_baseline_v1.json").read_text("utf-8")
        )["profiles"]["local_offline"]
        experiment = json.loads(
            (settings.root / "config" / "generation_experiments_v1.json").read_text("utf-8")
        )
        self.profile = baseline
        self.runtime = experiment["runtime"]
        self.model_root = settings.data_dir / "models" / "generation"
        self.runtime_root = settings.data_dir / "models" / "llama.cpp"
        self.model_repository = baseline["model_repository"]
        self.model_revision = baseline["model_revision"]
        self.model_filename = baseline["model_file"]
        self.model_sha256 = baseline["model_sha256"]
        self._cached: dict[OfflineBackend, OfflineArtifacts] = {}

    @property
    def backend(self) -> OfflineBackend:
        return self.settings.offline_generation.backend

    @property
    def runtime_manifest(self) -> Path:
        """Retain the original CPU manifest property for existing callers."""

        return self.runtime_manifest_for("cpu")

    def runtime_spec(self, backend: OfflineBackend | None = None) -> RuntimeArtifactSpec:
        selected = backend or self.backend
        return CPU_RUNTIME_SPEC if selected == "cpu" else OPENCL_RUNTIME_SPEC

    def runtime_directory(self, backend: OfflineBackend | None = None) -> Path:
        selected = backend or self.backend
        return self.runtime_root if selected == "cpu" else self.runtime_root / "opencl_gpu"

    def runtime_manifest_for(self, backend: OfflineBackend | None = None) -> Path:
        return self.runtime_directory(backend) / "runtime-manifest.json"

    def compatibility_error(self, backend: OfflineBackend | None = None) -> str | None:
        if platform.system() != "Windows":
            return "Generation Baseline v1 offline runtime supports Windows only."
        machines = {
            platform.machine().lower(),
            os.environ.get("PROCESSOR_ARCHITEW6432", "").lower(),
            os.environ.get("PROCESSOR_ARCHITECTURE", "").lower(),
        }
        if not machines.intersection({"arm64", "aarch64"}):
            return "The frozen offline runtime is Windows ARM64 and is incompatible with this CPU architecture."
        return None

    def discover(self, backend: OfflineBackend | None = None) -> OfflineArtifacts | None:
        selected = backend or self.backend
        if self.compatibility_error(selected):
            return None
        cached = self._cached.get(selected)
        if cached and cached.model_path.is_file() and cached.server_path.is_file():
            return cached
        model = next((path for path in self.model_candidates() if self.verify_model(path)), None)
        runtime_dir = self.runtime_directory(selected)
        server = runtime_dir / "bin" / "llama-server.exe"
        if model is None or not self.verify_runtime(server, selected):
            return None
        spec = self.runtime_spec(selected)
        artifact = OfflineArtifacts(
            model, server, model.stat().st_size, self.runtime_manifest_for(selected),
            selected, spec.build_number,
        )
        self._cached[selected] = artifact
        return artifact

    def artifact_error(self, backend: OfflineBackend | None = None) -> str | None:
        """Explain exactly why the selected model/runtime cannot be used."""

        selected = backend or self.backend
        compatibility = self.compatibility_error(selected)
        if compatibility:
            return compatibility
        if not any(self.verify_model(path) for path in self.model_candidates()):
            return (
                f"Verified {self.model_filename} is missing; run offline setup to "
                "download or reuse the frozen model."
            )
        runtime_dir = self.runtime_directory(selected)
        server = runtime_dir / "bin" / "llama-server.exe"
        if not server.is_file():
            return (
                f"{selected} llama-server is missing under {runtime_dir}; "
                "run offline setup for the selected backend."
            )
        spec = self.runtime_spec(selected)
        for filename in spec.required_files:
            if not (server.parent / filename).is_file():
                return (
                    f"{selected} runtime is missing required {filename}; rerun offline "
                    "setup to restore the verified runtime."
                )
        if not self.runtime_manifest_for(selected).is_file():
            return (
                f"{selected} runtime manifest is missing; rerun offline setup to "
                "verify the runtime files."
            )
        if not self.verify_runtime(server, selected):
            return (
                f"{selected} llama.cpp runtime failed build or checksum verification; "
                "rerun offline setup."
            )
        return None

    def model_candidates(self) -> list[Path]:
        cache_name = "models--" + self.model_repository.replace("/", "--")
        relative = Path(cache_name) / "snapshots" / self.model_revision / self.model_filename
        return [
            self.model_root / relative,
            Path.home() / ".cache" / "huggingface" / "hub" / relative,
            self.model_root / self.model_filename,
        ]

    def verify_model(self, path: Path) -> bool:
        return path.is_file() and _sha256(path) == self.model_sha256

    def verify_runtime(
        self, server: Path, backend: OfflineBackend | None = None
    ) -> bool:
        selected = backend or self.backend
        manifest_path = self.runtime_manifest_for(selected)
        if not server.is_file() or not manifest_path.is_file():
            return False
        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        spec = self.runtime_spec(selected)
        expected = {
            "build_number": spec.build_number,
            "commit": spec.commit,
            "archive_sha256": spec.archive_sha256,
            "architecture": self.runtime["architecture"],
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            return False
        manifest_backend = manifest.get("backend")
        if manifest_backend is not None and manifest_backend != selected:
            return False
        if selected == "opencl_gpu" and manifest_backend != selected:
            return False
        files = manifest.get("files")
        if not isinstance(files, dict):
            return False
        if any(filename not in files for filename in spec.required_files):
            return False
        runtime_dir = self.runtime_directory(selected)
        for relative, digest in files.items():
            candidate = (runtime_dir / "bin" / relative).resolve()
            if runtime_dir.resolve() not in candidate.parents or not candidate.is_file():
                return False
            if _sha256(candidate) != digest:
                return False
        if any(not (server.parent / filename).is_file() for filename in spec.required_files):
            return False
        return self._version_matches(server, selected)

    def write_runtime_manifest(
        self, binary_dir: Path, backend: OfflineBackend | None = None
    ) -> None:
        selected = backend or self.backend
        spec = self.runtime_spec(selected)
        server = binary_dir / "llama-server.exe"
        if not self._version_matches(server, selected):
            raise RuntimeError(
                f"llama-server version does not match required {selected} build "
                f"{spec.build_number} and commit"
            )
        files = {
            path.relative_to(binary_dir).as_posix(): _sha256(path)
            for path in sorted(binary_dir.rglob("*")) if path.is_file()
        }
        payload: dict[str, Any] = {
            "schema_version": 1,
            "backend": selected,
            "source_url": spec.archive_url,
            "archive_sha256": spec.archive_sha256,
            "build_number": spec.build_number,
            "commit": spec.commit,
            "architecture": self.runtime["architecture"],
            "files": files,
        }
        self.runtime_manifest_for(selected).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _version_matches(
        self, server: Path, backend: OfflineBackend | None = None
    ) -> bool:
        spec = self.runtime_spec(backend)
        try:
            result = subprocess.run(
                [str(server), "--version"], cwd=server.parent, capture_output=True,
                text=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        output = f"{result.stdout}\n{result.stderr}".lower()
        return (
            str(spec.build_number) in output
            and spec.commit[:7].lower() in output
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
