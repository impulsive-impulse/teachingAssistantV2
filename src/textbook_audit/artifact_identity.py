"""Explicit text-only compatibility for historical CRLF artifact identities."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .retrieval_baseline import sha256_file


TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".html", ".yaml", ".yml", ".csv", ".txt"}


def load_text_identity_profile(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    profile = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(profile, dict) or set(profile) != {"schema_version", "text_policy", "artifacts"}
        or profile["schema_version"] != 2 or profile["text_policy"] != "utf8-crlf-to-lf-only"
        or not isinstance(profile["artifacts"], list)
    ):
        raise ValueError("unsupported historical text identity profile")
    identities = {}
    for entry in profile["artifacts"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "historical_raw_sha256", "utf8_lf_sha256"}:
            raise ValueError("invalid historical text identity entry")
        relative = entry["path"]
        if (
            not isinstance(relative, str) or "\\" in relative or ":" in relative
            or PurePosixPath(relative).is_absolute() or ".." in PurePosixPath(relative).parts
            or PurePosixPath(relative).suffix not in TEXT_SUFFIXES or relative in identities
            or any(
                not isinstance(entry[key], str) or not re.fullmatch(r"[0-9a-f]{64}", entry[key])
                for key in ("historical_raw_sha256", "utf8_lf_sha256")
            )
        ):
            raise ValueError("text identities require distinct relative UTF-8 text paths and SHA-256 pins")
        identities[relative] = entry
    return identities


def verify_artifact_identity(
    root: Path, artifact: dict[str, Any], text_identities: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    relative, expected = artifact["path"], artifact["sha256"]
    path = root.joinpath(*PurePosixPath(relative).parts)
    actual = sha256_file(path) if path.is_file() else None
    result = {"path": relative, "expected": expected, "actual": actual, "valid": actual == expected}
    if result["valid"]:
        return {**result, "verification": "raw-sha256-v1"}
    entry = (text_identities or {}).get(relative)
    if (
        actual is None or entry is None or path.suffix not in TEXT_SUFFIXES
        or entry["historical_raw_sha256"] != expected
    ):
        return result
    raw = path.read_bytes()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return {**result, "error": "allowlisted text is not UTF-8"}
    normalized = raw.replace(b"\r\n", b"\n")
    if b"\r" in normalized:
        return {**result, "error": "allowlisted text contains a non-CRLF carriage return"}
    normalized_sha = hashlib.sha256(normalized).hexdigest()
    return {
        **result, "valid": normalized_sha == entry["utf8_lf_sha256"],
        "verification": "utf8-lf-text-v2", "normalized_sha256": normalized_sha,
    }
