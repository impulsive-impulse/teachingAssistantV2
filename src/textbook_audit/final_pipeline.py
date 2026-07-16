"""Compatibility facade for the frozen Retrieval Baseline v1 public API.

New code should import :func:`textbook_audit.retrieval_baseline.retrieve`.
This module retains the earlier ``load_pipeline``/``query_pipeline`` names but
delegates all behavior to the canonical YAML-backed runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .retrieval_baseline import (DEFAULT_CONFIG, RetrievalBaseline, load_config,
                                 main, retrieve)


def load_pipeline(root: Path, profile: str = "balanced", device: str = "cpu",
                  batch_size: int = 16,
                  config_path: Path | str = DEFAULT_CONFIG) -> RetrievalBaseline:
    """Load v1 through its canonical config while preserving the old helper name."""
    if profile not in {"balanced", "quality"}:
        raise ValueError("Retrieval Baseline v1 supports balanced/quality aliases only")
    config = load_config(config_path, root)
    if batch_size != config["embedding"]["batch_size"]:
        raise ValueError("batch_size is frozen by the v1 configuration")
    return RetrievalBaseline(root, config, device)


def query_pipeline(pipeline: RetrievalBaseline, question: str, book_id: str,
                   top_k: int = 5, include_text: bool = False) -> dict[str, Any]:
    """Return the legacy dictionary shape from the canonical five-result runtime."""
    if top_k != pipeline.config["output"]["final_top_k"]:
        raise ValueError("top_k is frozen at five for Retrieval Baseline v1")
    result = pipeline.retrieve(question, book_id, include_text).to_dict()
    # Preserve the earlier keys for callers while exposing richer provenance
    # inside each retrieved evidence row.
    result["retrieved"] = result.pop("evidence")
    result["profile"] = "balanced"
    return result


__all__ = ["RetrievalBaseline", "load_pipeline", "main", "query_pipeline", "retrieve"]


if __name__ == "__main__":
    main()
