"""Source-only rendering and exact o200k_base budgeting shared by all arms."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

from .assessment_assets import FileIdentity, child_path, load_assets, verify_file
from .assessment_protocol import fingerprint
from .source_provenance import (
    ProvenanceText, SourceDocument, join_text, normalize_words, require_retained_spans,
)


CONTEXT_VERSION = "assessment-packed-context-v1"


def context_encoder(root: Path):
    assets = load_assets(root)
    tokenizer = assets["context_tokenizer"]
    directory = child_path(root, tokenizer["cache_directory"])
    verify_file(child_path(directory, tokenizer["cache_key"]), FileIdentity.from_dict(tokenizer))
    os.environ["TIKTOKEN_CACHE_DIR"] = str(directory)
    import tiktoken
    return tiktoken.get_encoding(tokenizer["name"])


def unit_parts(text: ProvenanceText) -> list[tuple[str, ProvenanceText]]:
    if len(text.document_hashes) > 1:
        raise ValueError("one evidence block cannot conflate multiple documents")
    output, unit_id, start, end = [], None, 0, 0
    for span in text.spans:
        if unit_id is not None and span.unit_id != unit_id:
            output.append((unit_id, normalize_words(text.slice(start, end))))
            unit_id = None
        if unit_id is None:
            unit_id, start = span.unit_id, span.text_start
        end = max(end, span.text_end)
    if unit_id is not None:
        output.append((unit_id, normalize_words(text.slice(start, end))))
    return [(unit, part) for unit, part in output if part.text.strip()]


def render_segment(segment: dict[str, Any]) -> str:
    return (
        f"[{segment['evidence_id']}] {segment['document_title']}\n" +
        "\n".join(f"[{unit['unit_id']}]\n{unit['text']}" for unit in segment["units"])
    )


def _bounded_prefix(text: ProvenanceText, prefix: str, encoder: Any, budget: int) -> ProvenanceText:
    low, high, kept = 0, len(text.text), 0
    while low <= high:
        middle = (low + high) // 2
        if len(encoder.encode(prefix + text.text[:middle])) <= budget:
            kept, low = middle, middle + 1
        else:
            high = middle - 1
    while kept and len(encoder.encode(prefix + text.text[:kept])) > budget:
        kept -= 1
    while kept < len(text.text) and len(encoder.encode(prefix + text.text[:kept + 1])) <= budget:
        kept += 1
    return text.slice(0, kept)


def pack_units(
    evidence: Sequence[dict[str, Any]], catalog: dict[str, SourceDocument],
    encoder: Any, budget: int = 1024,
) -> dict[str, Any]:
    """Relevance-ordered baseline packing, truncating only the final source unit."""
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 1:
        raise ValueError("context token budget must be positive")
    segments, rendered, stop = [], "", False
    for rank, item in enumerate(evidence, 1):
        original = ProvenanceText.from_dict(item["source_provenance"])
        original.validate(catalog)
        if len(original.document_hashes) != 1 or item["document_id"] != original.document_hashes[0][0]:
            raise ValueError("context candidate source identity is inconsistent")
        document = catalog[item["document_id"]]
        segment = {
            "evidence_id": f"E{rank}", "source_evidence_id": item["evidence_id"],
            "document_id": document.document_id, "document_title": document.title,
            "source_chunk_ids": [item["chunk_id"]], "original_rank": item.get("rank", rank),
            "units": [], "truncated": False,
        }
        kept_parts = []
        for unit_id, part in unit_parts(original):
            prefix = rendered + ("\n\n" if rendered else "")
            if segment["units"]:
                prefix += render_segment(segment) + "\n"
            else:
                prefix += f"[{segment['evidence_id']}] {segment['document_title']}\n"
            prefix += f"[{unit_id}]\n"
            selected = part
            if len(encoder.encode(prefix + part.text)) > budget:
                selected = _bounded_prefix(part, prefix, encoder, budget)
                segment["truncated"], stop = True, True
            if selected.text.strip():
                segment["units"].append({
                    "unit_id": unit_id, "text": selected.text,
                    "source_provenance": selected.to_dict(),
                })
                kept_parts.append(selected)
            if stop:
                break
        if kept_parts:
            combined = join_text(kept_parts)
            segment["text"], segment["source_provenance"] = combined.text, combined.to_dict()
            segments.append(segment)
            rendered = "\n\n".join(render_segment(part) for part in segments)
        if stop:
            break
    count = len(encoder.encode(rendered))
    if count > budget:
        raise ValueError("rendered evidence exceeded the exact context token budget")
    core = {
        "version": CONTEXT_VERSION, "tokenizer": encoder.name, "token_budget": budget,
        "token_count": count, "rendered": rendered, "segments": segments,
        "evidence_state": "present" if segments else "insufficient_evidence",
    }
    return {**core, "checksum": fingerprint(core)}


def validate_context(
    packed: dict[str, Any], catalog: dict[str, SourceDocument],
    selected_evidence: Sequence[dict[str, Any]], encoder: Any,
) -> None:
    if not isinstance(packed, dict) or set(packed) != {
        "version", "tokenizer", "token_budget", "token_count", "rendered", "segments",
        "evidence_state", "checksum",
    } or packed["version"] != CONTEXT_VERSION:
        raise ValueError("packed context has invalid fields or version")
    if packed["checksum"] != fingerprint({key: value for key, value in packed.items() if key != "checksum"}):
        raise ValueError("packed context checksum changed")
    if packed["tokenizer"] != encoder.name or packed["rendered"] != "\n\n".join(
        render_segment(segment) for segment in packed["segments"]
    ):
        raise ValueError("packed context rendering or tokenizer differs")
    count = len(encoder.encode(packed["rendered"]))
    if (
        isinstance(packed["token_budget"], bool) or not isinstance(packed["token_budget"], int)
        or packed["token_budget"] < 1 or isinstance(packed["token_count"], bool)
        or not isinstance(packed["token_count"], int) or packed["token_count"] != count
        or count > packed["token_budget"]
    ):
        raise ValueError("packed context token count exceeds its declared budget")
    if packed["evidence_state"] != ("present" if packed["segments"] else "insufficient_evidence"):
        raise ValueError("packed evidence state is inconsistent")
    originals = [ProvenanceText.from_dict(item["source_provenance"]) for item in selected_evidence]
    by_id = {item["evidence_id"]: item for item in selected_evidence}
    if len(by_id) != len(selected_evidence):
        raise ValueError("selected evidence contains duplicate identities")
    evidence_ids = set()
    for original in originals:
        original.validate(catalog)
    for segment in packed["segments"]:
        if segment["evidence_id"] in evidence_ids or segment["source_evidence_id"] not in by_id:
            raise ValueError("packed evidence identity is duplicate or unselected")
        evidence_ids.add(segment["evidence_id"])
        document = catalog.get(segment["document_id"])
        selected = by_id[segment["source_evidence_id"]]
        if (
            document is None or segment["document_title"] != document.title
            or selected["document_id"] != document.document_id
            or not isinstance(segment["units"], list) or not segment["units"]
        ):
            raise ValueError("packed context source title/identity changed")
        parts = []
        for unit in segment["units"]:
            part = ProvenanceText.from_dict(unit["source_provenance"])
            part.validate(catalog)
            if (
                part.text != unit["text"]
                or {(span.document_id, span.unit_id) for span in part.spans} != {(document.document_id, unit["unit_id"])}
            ):
                raise ValueError("packed source unit text/address changed")
            require_retained_spans(part, [ProvenanceText.from_dict(selected["source_provenance"])])
            parts.append(part)
        combined = join_text(parts)
        if combined.to_dict() != segment["source_provenance"] or combined.text != segment["text"]:
            raise ValueError("packed context source map differs from its retained units")
