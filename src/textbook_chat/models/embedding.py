"""Exact discovery and integrity verification for the frozen BGE snapshot."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..config import AppSettings


@dataclass(frozen=True)
class EmbeddingArtifact:
    path: Path
    identity_sha256: str
    file_count: int
    size_bytes: int


class EmbeddingArtifactRegistry:
    """Locate only a snapshot that reproduces the frozen baseline identity."""

    def __init__(self, settings: AppSettings):
        self.settings = settings
        baseline = yaml.safe_load(
            (settings.root / "config" / "retrieval_baseline_v1.yaml").read_text(encoding="utf-8")
        )
        self.model_name = baseline["embedding"]["model_name"]
        self.revision = baseline["embedding"]["revision"]
        manifest = json.loads(
            (settings.root / "reports" / "retrieval_baseline_v1" / "manifest.json").read_text(encoding="utf-8")
        )
        identity = manifest["model"]["cache_identity"]
        self.expected_identity = identity["identity_sha256"]
        self.expected_file_count = int(identity["file_count"])
        self.expected_size_bytes = int(identity["size_bytes"])
        self._cached: EmbeddingArtifact | None = None

    @property
    def repository_cache_name(self) -> str:
        return "models--" + self.model_name.replace("/", "--")

    @property
    def application_cache(self) -> Path:
        return self.settings.data_dir / "models" / "embeddings"

    def candidates(self) -> list[Path]:
        relative = Path(self.repository_cache_name) / "snapshots" / self.revision
        return [
            self.application_cache / relative,
            Path.home() / ".cache" / "huggingface" / "hub" / relative,
        ]

    def discover(self) -> EmbeddingArtifact | None:
        """Return a verified app or standard-cache snapshot, never a near match."""

        if self._cached and self._cached.path.is_dir():
            return self._cached
        for candidate in self.candidates():
            if not candidate.is_dir():
                continue
            identity = directory_identity(candidate)
            if (
                identity.identity_sha256 == self.expected_identity
                and identity.file_count == self.expected_file_count
                and identity.size_bytes == self.expected_size_bytes
            ):
                self._cached = identity
                return identity
        return None

    def verify_path(self, path: Path) -> EmbeddingArtifact:
        identity = directory_identity(path)
        if (
            identity.identity_sha256 != self.expected_identity
            or identity.file_count != self.expected_file_count
            or identity.size_bytes != self.expected_size_bytes
        ):
            raise RuntimeError("downloaded embedding snapshot does not match the frozen identity")
        self._cached = identity
        return identity


def directory_identity(path: Path) -> EmbeddingArtifact:
    """Hash ordered relative names and file hashes exactly as the frozen manifest."""

    files = sorted(item for item in path.rglob("*") if item.is_file())
    digest = hashlib.sha256()
    total = 0
    for item in files:
        relative = item.relative_to(path).as_posix()
        total += item.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(item).encode("ascii"))
        digest.update(b"\n")
    return EmbeddingArtifact(path.resolve(), digest.hexdigest(), len(files), total)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
