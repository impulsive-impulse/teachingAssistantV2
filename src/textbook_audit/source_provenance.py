"""Versioned, exact source addresses for PDFs and benchmark sentences.

Offsets are zero-based, half-open Python string positions in the persisted
source unit, not byte offsets or PDF drawing coordinates. Printed textbook
page labels are deliberately absent: an inferred offset is not a source label.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .assessment_protocol import fingerprint, read_json
from .experiment_tracking import write_json


PROVENANCE_VERSION = "source-provenance-v1"
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
UNIT_RE = re.compile(r"(pdf_page|sentence):(\d{6,})\Z")


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return value


def _integer(value: Any, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def _object(value: Any, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} has an invalid shape")
    return value


def _unit_address(unit_id: str) -> tuple[str, int]:
    if not isinstance(unit_id, str) or (match := UNIT_RE.fullmatch(unit_id)) is None:
        raise ValueError("source unit ID must identify a PDF page or benchmark sentence")
    kind, ordinal = match.group(1), int(match.group(2))
    if kind == "pdf_page" and ordinal < 1:
        raise ValueError("physical PDF pages start at one")
    if unit_id != f"{kind}:{ordinal:06d}":
        raise ValueError("source unit ID must use its canonical ordinal")
    return kind, ordinal


@dataclass(frozen=True)
class SourceUnit:
    unit_id: str
    text: str
    text_sha256: str

    def __post_init__(self) -> None:
        _unit_address(self.unit_id)
        if not isinstance(self.text, str):
            raise ValueError("source unit text must be a string")
        _hash(self.text_sha256, "source unit text hash")
        if self.text_sha256 != hashlib.sha256(self.text.encode("utf-8")).hexdigest():
            raise ValueError("source unit text does not match its hash")

    @classmethod
    def create(cls, kind: str, ordinal: int, text: str) -> SourceUnit:
        _integer(ordinal, "source unit ordinal")
        if not isinstance(text, str):
            raise ValueError("source unit text must be a string")
        return cls(f"{kind}:{ordinal:06d}", text, hashlib.sha256(text.encode("utf-8")).hexdigest())

    @classmethod
    def from_dict(cls, value: Any) -> SourceUnit:
        return cls(**_object(value, {"unit_id", "text", "text_sha256"}, "source unit"))


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    kind: str
    title: str
    source_sha256: str
    content_sha256: str
    extraction_profile: str
    units: tuple[SourceUnit, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind not in {"pdf", "hotpotqa"}:
            raise ValueError("source document kind must be pdf or hotpotqa")
        for field in ("title", "extraction_profile"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"source document {field} must be a non-empty string")
        _hash(self.source_sha256, "source artifact hash")
        _hash(self.content_sha256, "source content hash")
        if (
            not isinstance(self.units, tuple) or (self.kind == "pdf" and not self.units)
            or any(not isinstance(unit, SourceUnit) for unit in self.units)
        ):
            raise ValueError("source document must contain immutable source units")
        unit_kind, start = ("pdf_page", 1) if self.kind == "pdf" else ("sentence", 0)
        if [unit.unit_id for unit in self.units] != [
            f"{unit_kind}:{index:06d}" for index in range(start, start + len(self.units))
        ]:
            raise ValueError("source units must retain every original page or sentence ordinal")
        if self.content_sha256 != fingerprint(self._content()):
            raise ValueError("source document content does not match its hash")
        expected = (
            f"pdf:{self.source_sha256}" if self.kind == "pdf"
            else "hotpotqa:" + fingerprint({
                "title": self.title, "sentences": [unit.text for unit in self.units],
            })
        )
        if self.document_id != expected:
            raise ValueError("source document ID does not match its original content")

    def _content(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "extraction_profile": self.extraction_profile,
            "source_sha256": self.source_sha256,
            "units": [asdict(unit) for unit in self.units],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "provenance_version": PROVENANCE_VERSION, **asdict(self),
            "units": [asdict(unit) for unit in self.units],
        }

    @classmethod
    def from_dict(cls, value: Any) -> SourceDocument:
        payload = _object(value, {
            "provenance_version", "document_id", "kind", "title", "source_sha256",
            "content_sha256", "extraction_profile", "units",
        }, "source document")
        if payload["provenance_version"] != PROVENANCE_VERSION or not isinstance(payload["units"], list):
            raise ValueError("source document version or units are invalid")
        return cls(**{
            key: value for key, value in payload.items()
            if key not in {"provenance_version", "units"}
        }, units=tuple(SourceUnit.from_dict(unit) for unit in payload["units"]))

    def unit(self, unit_id: str) -> SourceUnit:
        kind, ordinal = _unit_address(unit_id)
        expected_kind, start = ("pdf_page", 1) if self.kind == "pdf" else ("sentence", 0)
        index = ordinal - start
        if kind != expected_kind or not 0 <= index < len(self.units):
            raise ValueError("source location is outside its document")
        return self.units[index]


def _document(
    kind: str, title: str, source_sha256: str, profile: str, units: tuple[SourceUnit, ...],
) -> SourceDocument:
    content = {
        "kind": kind, "extraction_profile": profile, "source_sha256": source_sha256,
        "units": [asdict(unit) for unit in units],
    }
    document_id = (
        f"pdf:{source_sha256}" if kind == "pdf"
        else "hotpotqa:" + fingerprint({"title": title, "sentences": [unit.text for unit in units]})
    )
    return SourceDocument(document_id, kind, title, source_sha256, fingerprint(content), profile, units)


def pdf_document(source: Path, title: str | None = None) -> SourceDocument:
    """Read one PDF snapshot; renaming it never creates another document."""
    import pypdf

    data = source.read_bytes()
    reader = pypdf.PdfReader(io.BytesIO(data), strict=True)
    if reader.is_encrypted:
        raise ValueError("encrypted PDFs cannot provide reliable source text")
    units = []
    for index, page in enumerate(reader.pages, 1):
        text = page.extract_text()
        if text is None:
            text = ""
        units.append(SourceUnit.create("pdf_page", index, text))
    return _document(
        "pdf", source.stem if title is None else title, hashlib.sha256(data).hexdigest(),
        f"pypdf-{pypdf.__version__}-default-text-v1", tuple(units),
    )


def benchmark_document(
    title: str, sentences: Sequence[str], source_sha256: str,
) -> SourceDocument:
    """Accept only runtime paragraph content, never a gold-bearing question row."""
    if not isinstance(sentences, (list, tuple)):
        raise ValueError("benchmark sentences must be an ordered string sequence")
    units = tuple(SourceUnit.create("sentence", index, text) for index, text in enumerate(sentences))
    return _document("hotpotqa", title, source_sha256, "hotpotqa-original-sentences-v1", units)


@dataclass(frozen=True)
class SourceSpan:
    document_id: str
    unit_id: str
    source_start: int
    source_end: int
    text_start: int
    text_end: int

    def __post_init__(self) -> None:
        if not isinstance(self.document_id, str) or not self.document_id:
            raise ValueError("source span must retain its document ID")
        _unit_address(self.unit_id)
        for field in ("source_start", "source_end", "text_start", "text_end"):
            _integer(getattr(self, field), field)
        if self.source_start >= self.source_end or self.text_start >= self.text_end:
            raise ValueError("source spans must be non-empty half-open ranges")
        if self.source_end - self.source_start != self.text_end - self.text_start:
            raise ValueError("source spans must copy exact text, not approximate offsets")

    @classmethod
    def from_dict(cls, value: Any) -> SourceSpan:
        return cls(**_object(value, {
            "document_id", "unit_id", "source_start", "source_end", "text_start", "text_end",
        }, "source span"))


@dataclass(frozen=True)
class ProvenanceText:
    text: str
    spans: tuple[SourceSpan, ...]
    document_hashes: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not isinstance(self.spans, tuple):
            raise ValueError("provenance text and immutable spans are required")
        if not isinstance(self.document_hashes, tuple) or any(
            not isinstance(pair, tuple) or len(pair) != 2 for pair in self.document_hashes
        ):
            raise ValueError("provenance document hashes must be immutable pairs")
        references = dict(self.document_hashes)
        if len(references) != len(self.document_hashes):
            raise ValueError("provenance contains duplicate document identities")
        for document_id, content_hash in self.document_hashes:
            if not isinstance(document_id, str) or not document_id:
                raise ValueError("provenance document ID is missing")
            _hash(content_hash, "provenance document content hash")
        covered = bytearray(len(self.text))
        previous = -1
        used = set()
        for span in self.spans:
            if not isinstance(span, SourceSpan) or span.text_end > len(self.text) or span.text_start < previous:
                raise ValueError("provenance spans are invalid or out of text order")
            previous = span.text_start
            if span.document_id not in references:
                raise ValueError("provenance span has no document content identity")
            used.add(span.document_id)
            covered[span.text_start:span.text_end] = b"\1" * (span.text_end - span.text_start)
        if used != set(references):
            raise ValueError("provenance must not retain documents whose text was removed")
        if any(not char.isspace() and not covered[index] for index, char in enumerate(self.text)):
            raise ValueError("non-whitespace evidence text is missing exact source provenance")

    def _payload(self) -> dict[str, Any]:
        return {
            "provenance_version": PROVENANCE_VERSION, "text": self.text,
            "spans": [asdict(span) for span in self.spans],
            "document_hashes": dict(self.document_hashes),
        }

    @property
    def evidence_id(self) -> str:
        return "evidence:" + fingerprint(self._payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "evidence_id": self.evidence_id}

    @classmethod
    def from_dict(cls, value: Any) -> ProvenanceText:
        payload = _object(value, {
            "provenance_version", "text", "spans", "document_hashes", "evidence_id",
        }, "provenance text")
        if payload["provenance_version"] != PROVENANCE_VERSION:
            raise ValueError("unsupported source provenance version")
        if not isinstance(payload["spans"], list) or not isinstance(payload["document_hashes"], dict):
            raise ValueError("provenance spans and document hashes have invalid shapes")
        result = cls(
            payload["text"], tuple(SourceSpan.from_dict(span) for span in payload["spans"]),
            tuple(sorted(payload["document_hashes"].items())),
        )
        if payload["evidence_id"] != result.evidence_id:
            raise ValueError("evidence ID does not match its text and source spans")
        return result

    @classmethod
    def from_unit(cls, document: SourceDocument, unit_id: str) -> ProvenanceText:
        unit = document.unit(unit_id)
        if not unit.text:
            return cls("", (), ())
        return cls(
            unit.text, (SourceSpan(document.document_id, unit_id, 0, len(unit.text), 0, len(unit.text)),),
            ((document.document_id, document.content_sha256),),
        )

    def slice(self, start: int, end: int) -> ProvenanceText:
        _integer(start, "slice start")
        _integer(end, "slice end")
        if not start <= end <= len(self.text):
            raise ValueError("evidence slice is outside its text")
        spans = []
        for span in self.spans:
            left, right = max(start, span.text_start), min(end, span.text_end)
            if left < right:
                source_start = span.source_start + left - span.text_start
                spans.append(SourceSpan(
                    span.document_id, span.unit_id, source_start, source_start + right - left,
                    left - start, right - start,
                ))
        used = {span.document_id for span in spans}
        return ProvenanceText(
            self.text[start:end], tuple(spans),
            tuple(pair for pair in self.document_hashes if pair[0] in used),
        )

    def validate(self, documents: Mapping[str, SourceDocument]) -> None:
        for document_id, content_hash in self.document_hashes:
            document = documents.get(document_id)
            if (
                not isinstance(document, SourceDocument) or document.document_id != document_id
                or document.content_sha256 != content_hash
            ):
                raise ValueError("evidence source document is missing or has changed")
        for span in self.spans:
            unit = documents[span.document_id].unit(span.unit_id)
            if span.source_end > len(unit.text) or (
                unit.text[span.source_start:span.source_end] != self.text[span.text_start:span.text_end]
            ):
                raise ValueError("evidence text does not match its exact source span")


def join_text(parts: Iterable[ProvenanceText], separator: str = "\n") -> ProvenanceText:
    """Join mapped text; only whitespace may be added without a source."""
    if not isinstance(separator, str) or separator and not separator.isspace():
        raise ValueError("source-free evidence separators must be whitespace")
    text, spans, hashes = "", [], {}
    for index, part in enumerate(parts):
        if index:
            text += separator
        offset = len(text)
        text += part.text
        for document_id, content_hash in part.document_hashes:
            if document_id in hashes and hashes[document_id] != content_hash:
                raise ValueError("cannot join conflicting versions of the same source document")
            hashes[document_id] = content_hash
        spans.extend(SourceSpan(
            span.document_id, span.unit_id, span.source_start, span.source_end,
            span.text_start + offset, span.text_end + offset,
        ) for span in part.spans)
    return ProvenanceText(text, tuple(spans), tuple(sorted(hashes.items())))


def normalize_words(text: ProvenanceText) -> ProvenanceText:
    return join_text((text.slice(match.start(), match.end()) for match in re.finditer(r"\S+", text.text)), " ")


def truncate_words(text: ProvenanceText, maximum: int) -> ProvenanceText:
    _integer(maximum, "word budget")
    words = list(re.finditer(r"\S+", text.text))
    if maximum == 0 or not words:
        return ProvenanceText("", (), ())
    return normalize_words(text.slice(0, words[min(maximum, len(words)) - 1].end()))


def clean_pdf_text(text: ProvenanceText, repeated_lines: set[str]) -> ProvenanceText:
    """Apply the upload cleaner without guessing offsets after its deletions."""
    parts, offset = [], 0
    for line in text.text.splitlines(keepends=True):
        value = normalize_words(text.slice(offset, offset + len(line)))
        if value.text and value.text not in repeated_lines:
            parts.append(value)
        offset += len(line)
    cleaned = join_text(parts)
    output, offset = [], 0
    for match in re.finditer(r"(?<=[A-Za-z])-\s*\n\s*(?=[a-z])", cleaned.text):
        output.append(cleaned.slice(offset, match.start()))
        offset = match.end()
    output.append(cleaned.slice(offset, len(cleaned.text)))
    return join_text(output, "")


def retrieval_units(document: SourceDocument) -> list[dict[str, Any]]:
    """Adapt source units to the shared chunker, without textbook-only gates."""
    records = []
    for unit in document.units:
        kind, ordinal = _unit_address(unit.unit_id)
        records.append({
            "book_id": document.document_id, "document_id": document.document_id,
            "source_unit_id": unit.unit_id,
            "pdf_page_number": ordinal if kind == "pdf_page" else None,
            "textbook_page_number": None, "cleaned_text": unit.text,
            "source_provenance": ProvenanceText.from_unit(document, unit.unit_id).to_dict(),
        })
    return records


def merge_overlap(left: ProvenanceText, right: ProvenanceText, maximum: int, minimum: int) -> ProvenanceText:
    """Remove overlap only when both words and their exact source addresses agree."""
    _integer(maximum, "maximum overlap", 1)
    _integer(minimum, "minimum overlap", 1)
    if minimum > maximum:
        raise ValueError("minimum overlap exceeds maximum overlap")
    if len(left.document_hashes) != 1 or left.document_hashes != right.document_hashes:
        raise ValueError("overlap merging requires one identical source document")
    left, right = normalize_words(left), normalize_words(right)
    a, b = list(re.finditer(r"\S+", left.text)), list(re.finditer(r"\S+", right.text))
    for width in range(min(len(a), len(b), maximum), minimum - 1, -1):
        left_part = left.slice(a[-width].start(), len(left.text))
        right_part = right.slice(0, b[width - 1].end())
        if left_part.to_dict() == right_part.to_dict():
            if width == len(b):
                return left
            return join_text((left, right.slice(b[width].start(), len(right.text))), " ")
    return join_text((left, right), " ")


def source_locations(text: ProvenanceText) -> set[tuple[str, str]]:
    return {(span.document_id, span.unit_id) for span in text.spans}


def physical_pages(text: ProvenanceText) -> list[int]:
    return sorted({
        ordinal for _document, unit_id in source_locations(text)
        for kind, ordinal in [_unit_address(unit_id)] if kind == "pdf_page"
    })


def resolve_citation(
    text: ProvenanceText, document_id: str, unit_id: str, documents: Mapping[str, SourceDocument],
) -> dict[str, Any]:
    """Resolve only retained source characters, not any page from an old chunk."""
    text.validate(documents)
    if (document_id, unit_id) not in source_locations(text):
        raise ValueError("citation document/location pair is not present in this evidence")
    document = documents[document_id]
    unit = document.unit(unit_id)
    ranges: list[list[int]] = []
    for start, end in sorted({
        (span.source_start, span.source_end) for span in text.spans
        if span.document_id == document_id and span.unit_id == unit_id
    }):
        if ranges and start <= ranges[-1][1]:
            ranges[-1][1] = max(ranges[-1][1], end)
        else:
            ranges.append([start, end])
    kind, ordinal = _unit_address(unit_id)
    return {
        "provenance_version": PROVENANCE_VERSION, "evidence_id": text.evidence_id,
        "document_id": document_id, "document_title": document.title,
        "source_sha256": document.source_sha256, "content_sha256": document.content_sha256,
        "unit_id": unit_id, "unit_text_sha256": unit.text_sha256,
        "pdf_page": ordinal if kind == "pdf_page" else None,
        "sentence_index": ordinal if kind == "sentence" else None,
        "char_ranges": ranges,
    }


def validate_citation(
    citation: dict[str, Any], text: ProvenanceText, documents: Mapping[str, SourceDocument],
) -> None:
    _object(citation, {
        "provenance_version", "evidence_id", "document_id", "document_title",
        "source_sha256", "content_sha256", "unit_id", "unit_text_sha256",
        "pdf_page", "sentence_index", "char_ranges",
    }, "citation")
    if not isinstance(citation["document_id"], str) or not isinstance(citation["unit_id"], str):
        raise ValueError("citation must contain a document/location pair")
    if citation["pdf_page"] is not None:
        _integer(citation["pdf_page"], "citation PDF page", 1)
    if citation["sentence_index"] is not None:
        _integer(citation["sentence_index"], "citation sentence index")
    ranges = citation["char_ranges"]
    if not isinstance(ranges, list) or not ranges:
        raise ValueError("citation must retain source character ranges")
    for span in ranges:
        if not isinstance(span, list) or len(span) != 2:
            raise ValueError("citation character ranges must be pairs")
        _integer(span[0], "citation character start")
        _integer(span[1], "citation character end", span[0] + 1)
    expected = resolve_citation(text, citation["document_id"], citation["unit_id"], documents)
    if citation != expected:
        raise ValueError("citation does not match retained evidence and source identity")


def write_source_bundle(
    path: Path, documents: Sequence[SourceDocument], evidence: Sequence[ProvenanceText],
) -> None:
    catalog = {document.document_id: document for document in documents}
    if len(catalog) != len(documents):
        raise ValueError("source bundle must not contain duplicate documents")
    for item in evidence:
        item.validate(catalog)
    payload = {
        "provenance_version": PROVENANCE_VERSION,
        "documents": [document.to_dict() for document in documents],
        "evidence": [item.to_dict() for item in evidence],
    }
    write_json(path, {**payload, "checksum": fingerprint(payload)})


def read_source_bundle(path: Path) -> tuple[list[SourceDocument], list[ProvenanceText]]:
    payload = _object(read_json(path), {
        "provenance_version", "documents", "evidence", "checksum",
    }, "source bundle")
    if payload["provenance_version"] != PROVENANCE_VERSION or payload["checksum"] != fingerprint({
        key: value for key, value in payload.items() if key != "checksum"
    }):
        raise ValueError("source bundle version or checksum is invalid")
    if not isinstance(payload["documents"], list) or not isinstance(payload["evidence"], list):
        raise ValueError("source bundle documents and evidence must be arrays")
    documents = [SourceDocument.from_dict(item) for item in payload["documents"]]
    catalog = {document.document_id: document for document in documents}
    if len(catalog) != len(documents):
        raise ValueError("source bundle contains duplicate documents")
    evidence = [ProvenanceText.from_dict(item) for item in payload["evidence"]]
    for item in evidence:
        item.validate(catalog)
    return documents, evidence
