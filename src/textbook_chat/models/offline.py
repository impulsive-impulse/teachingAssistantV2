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

from ..config import AppSettings


LLAMA_ARCHIVE_NAME = "llama-b10046-bin-win-cpu-arm64.zip"
LLAMA_ARCHIVE_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/b10046/"
    + LLAMA_ARCHIVE_NAME
)
LLAMA_ARCHIVE_SHA256 = "7f9958be4bdfc110c4eaa7bb49eeb115573d44d80a8b9400063bc49336923f1c"


@dataclass(frozen=True)
class OfflineArtifacts:
    model_path: Path
    server_path: Path
    model_size_bytes: int
    runtime_manifest: Path


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
        self.runtime_manifest = self.runtime_root / "runtime-manifest.json"
        self._cached: OfflineArtifacts | None = None

    def compatibility_error(self) -> str | None:
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

    def discover(self) -> OfflineArtifacts | None:
        if self.compatibility_error():
            return None
        if self._cached and self._cached.model_path.is_file() and self._cached.server_path.is_file():
            return self._cached
        model = next((path for path in self.model_candidates() if self.verify_model(path)), None)
        server = self.runtime_root / "bin" / "llama-server.exe"
        if model is None or not self.verify_runtime(server):
            return None
        self._cached = OfflineArtifacts(model, server, model.stat().st_size, self.runtime_manifest)
        return self._cached

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

    def verify_runtime(self, server: Path) -> bool:
        if not server.is_file() or not self.runtime_manifest.is_file():
            return False
        try:
            manifest = json.loads(self.runtime_manifest.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        expected = {
            "build_number": self.profile["engine_build"],
            "commit": self.profile["engine_commit"],
            "archive_sha256": LLAMA_ARCHIVE_SHA256,
            "architecture": self.runtime["architecture"],
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            return False
        files = manifest.get("files")
        if not isinstance(files, dict):
            return False
        for relative, digest in files.items():
            candidate = (self.runtime_root / "bin" / relative).resolve()
            if self.runtime_root.resolve() not in candidate.parents or not candidate.is_file():
                return False
            if _sha256(candidate) != digest:
                return False
        return self._version_matches(server)

    def write_runtime_manifest(self, binary_dir: Path) -> None:
        server = binary_dir / "llama-server.exe"
        if not self._version_matches(server):
            raise RuntimeError("llama-server version does not match frozen build 10046 and commit")
        files = {
            path.relative_to(binary_dir).as_posix(): _sha256(path)
            for path in sorted(binary_dir.rglob("*")) if path.is_file()
        }
        payload: dict[str, Any] = {
            "schema_version": 1,
            "source_url": LLAMA_ARCHIVE_URL,
            "archive_sha256": LLAMA_ARCHIVE_SHA256,
            "build_number": self.profile["engine_build"],
            "commit": self.profile["engine_commit"],
            "architecture": self.runtime["architecture"],
            "files": files,
        }
        self.runtime_manifest.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _version_matches(self, server: Path) -> bool:
        try:
            result = subprocess.run(
                [str(server), "--version"], cwd=server.parent, capture_output=True,
                text=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        output = f"{result.stdout}\n{result.stderr}".lower()
        return (
            str(self.profile["engine_build"]) in output
            and self.profile["engine_commit"][:7].lower() in output
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
