"""Exact production prompt boundary for Generation Baseline v1.

This module intentionally delegates prompt rendering and output validation to
the frozen research implementation.  The only production-specific operation
is converting an immutable uploaded-book retrieval snapshot into the same
five page-ordered evidence records used during the accepted evaluation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from textbook_audit.generation_experiments import parse_output, render_prompt

from textbook_chat.retrieval.runtime import RetrievalSnapshotData


@dataclass(frozen=True)
class PromptPackage:
    """Prompt plus the evidence contract required to validate its response."""

    prompt: str
    evidence_items: list[dict[str, Any]]
    checksum: str


def build_prompt(snapshot: RetrievalSnapshotData | Mapping[str, Any]) -> PromptPackage:
    """Render the frozen P1 prompt from one persisted retrieval snapshot.

    Questions remain independent: no chat transcript or earlier answer enters
    this function.  Evidence IDs E1..E5 are assigned only after the frozen top
    five results are sorted into the accepted page-order context strategy.
    """

    payload = snapshot.to_dict() if isinstance(snapshot, RetrievalSnapshotData) else dict(snapshot)
    question = str(payload.get("question", "")).strip()
    evidence = payload.get("evidence")
    if not question:
        raise ValueError("retrieval snapshot question must not be empty")
    if not isinstance(evidence, list) or len(evidence) != 5:
        raise ValueError("Generation Baseline v1 requires exactly five retrieved evidence items")

    ordered = sorted(evidence, key=_page_order)
    items = [_to_prompt_item(item, index) for index, item in enumerate(ordered, 1)]
    prompt = render_prompt(
        {"normalized_question": question, "expected_answer_depth": "medium"},
        items,
        "P1",
        "retrieved_top5_page_order_compact",
        None,
    )
    checksum = hashlib.sha256(
        json.dumps(
            {"prompt": prompt, "evidence_items": items},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return PromptPackage(prompt=prompt, evidence_items=items, checksum=checksum)


def validate_answer(raw_text: str, package: PromptPackage) -> dict[str, Any]:
    """Apply the frozen five-field and citation-page validator unchanged."""

    return parse_output(raw_text, package.evidence_items)


def _page_order(item: object) -> tuple[int, int]:
    if not isinstance(item, Mapping):
        raise ValueError("retrieval evidence must contain objects")
    pages = _integer_pages(item.get("pdf_pages"), "pdf_pages")
    return min(pages), int(item.get("rank", 0))


def _to_prompt_item(item: object, index: int) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ValueError("retrieval evidence must contain objects")
    pdf_pages = _integer_pages(item.get("pdf_pages"), "pdf_pages")
    textbook_pages = _integer_pages(item.get("textbook_pages"), "textbook_pages")
    text = item.get("evidence_text")
    source_chunk_id = item.get("evidence_id")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("retrieval evidence text must not be empty")
    if not isinstance(source_chunk_id, str) or not source_chunk_id:
        raise ValueError("retrieval evidence must retain its source chunk ID")
    return {
        "evidence_id": f"E{index}",
        "pdf_page": pdf_pages[0],
        "textbook_page": textbook_pages[0],
        "pdf_pages": pdf_pages,
        "textbook_pages": textbook_pages,
        "source_file": "uploaded-textbook.pdf",
        "text": text,
        "retrieval_rank": int(item.get("rank", index)),
        "source_chunk_id": source_chunk_id,
    }


def _integer_pages(value: object, field: str) -> list[int]:
    if not isinstance(value, list) or not value or any(
        isinstance(page, bool) or not isinstance(page, int) or page < 1 for page in value
    ):
        raise ValueError(f"retrieval evidence {field} must be a non-empty positive integer list")
    return list(value)
