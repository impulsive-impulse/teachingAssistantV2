# Shared source provenance

`source-provenance-v1` is the assessment track's source and evidence contract.
It connects PDF pages and HotpotQA sentences to the existing chunking and
context helpers without changing the frozen, legacy v1 path.

The implementation is `src/textbook_audit/source_provenance.py`. It does not
retrieve answers, call a model, or grade semantic support. Collection ingestion,
the benchmark runner, and claim-level answer validation remain later tasks.

## Source identity and addresses

| Source | Document identity | Source unit | Citation location |
|---|---|---|---|
| PDF | SHA-256 of the original PDF bytes | Every physical PDF page, numbered from 1 | Physical PDF page plus exact character ranges |
| HotpotQA paragraph | Semantic SHA-256 of its exact title and original sentence array | Original zero-based sentence indices | Exact article title, sentence index, and character ranges |

A renamed PDF is still the same document. Its chapters and pages cannot become
separate documents. Two PDFs with identical extracted text but different source
bytes retain different identities.

Benchmark IDs do not depend on the question, gold answer, support labels,
paragraph order, retrieval rank, or chunking configuration. Exact titles are
preserved for official support scoring; title normalization does not rewrite
source addresses. Empty sentences retain their original indices; an empty
paragraph still has a document identity but cannot supply invented evidence.

Every document also records the source artifact SHA-256 and a semantic content
SHA-256 covering that artifact identity, extraction profile, and all ordered
source units. PDF extraction records the actual pypdf version. Evidence from a
different extraction or source artifact cannot silently reuse an old identity.
The JSON checksums are independent of checkout indentation and line endings;
characters and line breaks inside the original source text remain significant.

IDs are opaque values, not Windows filenames or filesystem paths.

## Printed pages are not verified addresses

The current legacy textbook adapter derives printed page numbers from a
constant PDF offset. The two demonstration PDFs do not supply explicit PDF
page-label metadata, and an offset alone does not prove the printed labels.

The new contract therefore omits printed-page labels. Its compatibility
`textbook_page_number` is `None`, chunk/context `textbook_pages` arrays are empty,
and resolved citations contain physical `pdf_page` locations instead. It does
not rewrite old processing artifacts, saved answers, or frozen research claims.
The existing application still uses its legacy generation contract until the
collection/API migration; these new fields must not be presented as an already
completed application citation fix.

## Text transformations

`SourceSpan` records a document ID, source unit ID, source character range,
and corresponding evidence character range. Offsets are zero-based, half-open
Python string positions: `[start, end)`. They are not UTF-8 byte offsets,
printed lines, OCR boxes, or PDF drawing coordinates.

Every non-whitespace evidence character must map to an exact original source
character. Formatting may add whitespace, but cannot invent factual words.
Whitespace normalization, running-line removal, and dehyphenation preserve
the original ranges instead of searching for an approximate quote afterward.
Cleaning is optional and does not change the immutable source units.

The existing fixed and structured chunkers accept this metadata through
`source_provenance`. The exact mode rejects mixed documents, mixed legacy/exact
records, modified page text, and mismatched source-unit/page addresses.
Structured tail merging updates the complete source map and evidence identity.
Legacy records without the field retain their previous outputs.

The context helpers preserve the maps through ordering, redundancy selection,
overlap merging, and word-budget clipping. Overlap removal requires identical
words at identical source addresses; matching prose on another page or in
another document is not the same evidence. Different documents remain separate
context segments. Clipping recalculates retained pages, source ranges, chunk
contributors, and evidence IDs, so removed text cannot remain citable.

These helpers use their existing word budgets. They are not the assessment's
final 1,024 `o200k_base` token packer, which belongs to T07.

## Persistence and citation resolution

`write_source_bundle` publishes documents and evidence using the existing
atomic JSON writer. `read_source_bundle` checks the bundle checksum, document
identities, unit hashes, evidence IDs, and every source/text span. Existing
SQLite snapshot JSON also preserves the metadata without a schema migration.

`resolve_citation` accepts an evidence object and a document/unit pair. It
returns the original document/title, artifact/content/unit hashes, physical
page or sentence index, and only the retained source character ranges.
`validate_citation` rejects altered IDs, mismatched page/sentence addresses,
expanded ranges, boolean coordinates, and citations to removed text.

This establishes address validity, not semantic support. A real source can
still fail to support a model's claim. Claim coverage, insufficient evidence,
and semantic-support review remain T08 responsibilities.

The T08 contract is `assessment_generation.py`: it has no free-form answer
channel outside declared claims. Each answered claim requires an exact
quotation from a retained evidence/unit pair. Its resolved character ranges
refer to that quotation, not an entire original page. Unknown addresses,
empty citations, unquoted numbers, and weak lexical support fail explicitly;
raw responses remain available to the calling runner. The lexical screen is
not an entailment proof, and semantic source review remains a separate rubric.

## Local inspection example

Run this Python code from the repository root using the assessment environment.
The PDF must already be legally available for local indexing. The generated
bundle contains source text and belongs under ignored `app_data/`, not in Git
or a shared submission without separate distribution rights.

```python
from pathlib import Path

from textbook_audit.chunk_retrieval import fixed_chunks
from textbook_audit.context_assembly import assemble_context
from textbook_audit.source_provenance import (
    ProvenanceText, pdf_document, retrieval_units, write_source_bundle,
)

document = pdf_document(Path(r"books\X Biology EM 2025-26.pdf"))
chunks = fixed_chunks(retrieval_units(document), target=600, overlap=100)
segments = assemble_context(
    "overlap_merge_metadata_preserving", list(range(5)), chunks,
)
write_source_bundle(
    Path(r"app_data\assessment\source_inspection.json"),
    [document],
    [ProvenanceText.from_dict(segment["source_provenance"]) for segment in segments],
)
```

This example inspects provenance only. It does not select answer-bearing
evidence, create a collection, or make an API request.

## Verification

```powershell
.\.venv-assessment\Scripts\python.exe -m pytest -q `
  tests\test_source_provenance.py tests\test_chunk_retrieval.py `
  tests\test_context_assembly.py tests\test_textbook_chat_persistence.py
```

Coverage includes synthetic and authorized real PDFs, exact benchmark sentence
locations, gold-label isolation, Unicode offsets, cleaning, fixed/structured
chunking, source-aware overlap, clipping, strict citation resolution, semantic
JSON reloads, and SQLite restart/regeneration. Missing demonstration inputs
are explicit skips, not proof that those inputs passed.

The completed T03 check used the locked x64 environment: 130 focused checks
passed, including all 600 frozen benchmark context documents, both authorized
PDFs, and frozen v1 golden fixtures. Model-backed checks used the exact T02
application-local BGE snapshot via a process-local test resolver because the
old research/home cache was absent; production discovery was not changed.
Separately, 224 direct chunk/context comparisons matched the pushed pre-T03
implementation exactly. These checks do not replace T15's final clean-clone
evaluation rerun or demonstrate a benchmark quality gain.
