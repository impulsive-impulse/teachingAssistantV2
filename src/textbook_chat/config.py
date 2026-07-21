"""Validated operational settings for the localhost application.

Operational settings are deliberately separate from the frozen retrieval and
generation files.  The application can relocate its data directory or port,
but cannot use environment variables to change a baseline model or parameter.
"""

from __future__ import annotations

import json
import os
import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .domain import FrozenProfileSummary


RETRIEVAL_CONFIG = Path("config/retrieval_baseline_v1.yaml")
GENERATION_CONFIG = Path("config/generation_baseline_v1.json")


def repository_root() -> Path:
    """Return the source-checkout root independently of the current directory."""

    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AppSettings:
    """The complete set of mutable operational settings."""

    root: Path
    data_dir: Path
    database_path: Path
    host: str
    port: int
    max_upload_bytes: int
    max_pdf_pages: int
    openai_api_key_present: bool

    @classmethod
    def load(cls, root: Path | None = None) -> "AppSettings":
        """Load `.env` without overriding values already in the process."""

        resolved_root = (root or repository_root()).resolve()
        load_dotenv(resolved_root / ".env", override=False)
        data_value = os.getenv("TEXTBOOK_CHAT_DATA_DIR", "app_data")
        data_dir = Path(data_value)
        if not data_dir.is_absolute():
            data_dir = resolved_root / data_dir
        data_dir = data_dir.resolve()
        port = _bounded_int("TEXTBOOK_CHAT_PORT", 8765, minimum=1, maximum=65535)
        upload_mb = _bounded_int("TEXTBOOK_CHAT_MAX_UPLOAD_MB", 500, 1, 4096)
        max_pages = _bounded_int("TEXTBOOK_CHAT_MAX_PDF_PAGES", 1500, 1, 10000)
        return cls(
            root=resolved_root,
            data_dir=data_dir,
            database_path=data_dir / "app.db",
            host="127.0.0.1",
            port=port,
            max_upload_bytes=upload_mb * 1024 * 1024,
            max_pdf_pages=max_pages,
            openai_api_key_present=bool(os.getenv("OPENAI_API_KEY", "").strip()),
        )

    def ensure_directories(self) -> None:
        """Create only runtime-owned paths; research directories stay untouched."""

        for path in (
            self.data_dir,
            self.data_dir / "books",
            self.data_dir / "jobs",
            self.data_dir / "models" / "embeddings",
            self.data_dir / "models" / "generation",
            self.data_dir / "models" / "llama.cpp",
            self.data_dir / "logs" / "app",
            self.data_dir / "logs" / "llama",
        ):
            path.mkdir(parents=True, exist_ok=True)


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = default if raw is None else int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def validate_frozen_configs(settings: AppSettings) -> FrozenProfileSummary:
    """Fail fast if either immutable baseline config is absent or incompatible."""

    generation_path = settings.root / GENERATION_CONFIG
    payload = json.loads(generation_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("baseline", {}).get("semantic_version") != "1.0.0":
        raise ValueError("only Generation Baseline v1 schema/version is supported")
    if payload.get("baseline", {}).get("frozen") is not True:
        raise ValueError("generation baseline must be frozen")
    retrieval_path = settings.root / RETRIEVAL_CONFIG
    retrieval = yaml.safe_load(retrieval_path.read_text(encoding="utf-8"))
    _validate_retrieval_identity(retrieval)
    expected_hash = payload["frozen_inputs"]["retrieval_baseline"]["sha256"]
    if _sha256(retrieval_path) != expected_hash:
        raise ValueError("retrieval baseline does not match Generation Baseline v1's frozen input")
    online = payload["profiles"]["online_quality"]
    offline = payload["profiles"]["local_offline"]
    return FrozenProfileSummary(
        online_model=online["resolved_and_frozen_model"],
        online_max_output_tokens=int(online["max_output_tokens"]),
        offline_model=offline["model_file"],
        offline_max_output_tokens=int(offline["max_output_tokens"]),
    )


def _validate_retrieval_identity(payload: object) -> None:
    """Validate startup-critical invariants without importing Torch/model code.

    The full research validator still runs when a retrieval worker loads.  This
    lightweight gate lets the application report model incompatibility instead
    of making the entire localhost server unbootable.
    """

    if not isinstance(payload, dict):
        raise ValueError("retrieval baseline must contain a mapping")
    baseline = payload.get("baseline", {})
    if baseline.get("semantic_version") != "1.0.0" or baseline.get("frozen") is not True:
        raise ValueError("only frozen Retrieval Baseline v1 is supported")
    if payload.get("chunking", {}).get("target_tokens") != 600:
        raise ValueError("Retrieval Baseline v1 requires 600-token chunks")
    if payload.get("chunking", {}).get("overlap_tokens") != 100:
        raise ValueError("Retrieval Baseline v1 requires 100-token overlap")
    if payload.get("output", {}).get("final_top_k") != 5:
        raise ValueError("Retrieval Baseline v1 requires top five evidence")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
