# Class 10 textbook corpus extraction audit

This repository contains the Milestone 1 corpus preparation pipeline for a
textbook-grounded QA/RAG research project. It extracts every PDF page, preserves
PDF and printed-page identity, assigns index-grounded chapters, and produces a
human-readable suitability audit.

The repository also includes a page-level retrieval baseline. It does not call
an LLM or implement answer generation, query rewriting, reranking, or chunking.

## Source books

| `book_id` | Source file | PDF pages | Printed-page mapping |
|---|---|---:|---|
| `biology` | `books/X Biology EM 2025-26.pdf` | 257 | PDF page = printed page + 9 |
| `physical_sciences` | `books/X Physics EM 2025-26.pdf` | 327 | PDF page = printed page + 10 |

The second PDF is titled *Physical Sciences* and includes both physics and
chemistry chapters; its identifier is therefore `physical_sciences`.

## Repository layout

```text
books/                         Input PDFs (never modified)
data/processed/                Generated page JSONL and chapter maps
reports/                       Generated extraction suitability audit
scripts/audit_textbooks.py     Source-checkout compatibility entry point
scripts/generate_retrieval_benchmark.py
                               Candidate benchmark generator and validator
src/textbook_audit/
  config.py                    Immutable book/chapter/page-offset catalog
  cli.py                       Command-line interface
  pipeline.py                  Extraction, mapping, cleaning, and reporting
tests/test_pipeline.py         Mapping and artifact integrity checks
tests/test_retrieval.py        Loading, ranking, matching, and metric regressions
pyproject.toml                 Package metadata and dependencies
```

Generated artifacts are committed as reproducible Milestone 1 research inputs.
Running the pipeline overwrites only the four files in `data/processed/` and
`reports/book_extraction_audit.md`.

## Setup

Python 3.10 or newer is required. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Run the extraction audit

After installation:

```powershell
textbook-audit
```

Or run directly from a source checkout:

```powershell
python scripts/audit_textbooks.py
```

The optional `--root PATH` argument selects another project root containing a
`books/` directory:

```powershell
textbook-audit --root X:\teachingAssistantV2
```

Extraction is deterministic, uses `pypdf`, numbers PDF pages from one, and does
not discard low-text or front-matter pages.

## Outputs

- `data/processed/biology_pages.jsonl`
- `data/processed/physical_sciences_pages.jsonl`
- `data/processed/biology_chapter_map.json`
- `data/processed/physical_sciences_chapter_map.json`
- `reports/book_extraction_audit.md`

Each JSONL line is one page with this shape:

```json
{
  "book_id": "biology | physical_sciences",
  "source_file": "string",
  "pdf_page_number": 1,
  "textbook_page_number": "string | number | null",
  "chapter_number": "number | null",
  "chapter_title": "string | null",
  "section_title": "string | null",
  "raw_text": "string",
  "cleaned_text": "string",
  "text_length": 0,
  "has_image": false,
  "has_table": false,
  "has_equation_like_text": false,
  "extraction_notes": []
}
```

`raw_text` is the untouched text-layer output. `cleaned_text` removes the
repeated government running line, normalizes whitespace, and conservatively
repairs alphabetic line-break hyphenation. Detection flags are heuristics, not
semantic annotations.

## Validation

Run the test suite after generating outputs:

```powershell
python -m unittest discover -s tests -v
```

The tests verify chapter/page mapping boundaries, expected record counts, exact
record fields, sequential PDF numbering, cleaned-text lengths, and chapter-map
coverage. They also verify candidate benchmark counts, schema, IDs, page offsets,
and evidence-span presence. Current expected counts are 257 Biology records and
327 Physical Sciences records.

## Retrieval Benchmark v1 candidates

Generate the candidate benchmark after page extraction:

```powershell
python scripts/generate_retrieval_benchmark.py
```

This writes:

- `data/benchmarks/retrieval_benchmark_v1_candidates.csv`
- `data/benchmarks/retrieval_benchmark_v1_candidates.jsonl`
- `reports/retrieval_benchmark_v1_notes.md`

The two data files contain the same 40 candidate queries: 20 Biology and 20
Physical Sciences. Gold answer spans are deterministic windows anchored in the
page JSONL. Empty page lists and spans identify intentional not-answerable or
weak-evidence candidates. This is a review set, not frozen ground truth; consult
the notes report before using it for retrieval scoring.

## Current suitability and limitations

Both books are **Suitable with caveats** for page-aware Milestone 1 retrieval
experiments. Prose coverage and chapter/page mapping are strong. Important risks
for later retrieval work are:

- tables are flattened and lose row/column relationships;
- diagram labels may extract, but spatial relationships do not;
- displayed fractions, superscripts, subscripts, reaction arrows, charge signs,
  and Ω may be degraded or reordered;
- running chapter titles and printed page numbers can concatenate with body text;
- `section_title`, table, and equation flags are heuristic.

See `reports/book_extraction_audit.md` for chapter-level confidence, sampled
pages, representative formula issues, image/table counts, and the full verdict.

## Page-Level Retrieval Baseline v1

The canonical reviewed benchmark is
`data/benchmarks/retrieval_benchmark_v1.jsonl`. The runner deliberately fails
if that file is absent and never substitutes the `_candidates` artifact.

Install retrieval dependencies and run from the repository root:

```powershell
python -m pip install -e .
python scripts/run_page_retrieval.py
```

Equivalent installed entry point:

```powershell
page-retrieval --root X:\teachingAssistantV2 --top-k 5
```

Useful options are `--benchmark`, `--results`, `--metrics`, `--report`,
`--cache-dir`, `--top-k`, and `--device`. `--top-k` must be at least 5 because
the required evaluation includes Hit@5. Page embeddings are cached under
`data/retrieval/cache/` and invalidated when cleaned page text changes.

The methods are Okapi BM25 (`k1=1.5`, `b=0.75`), normalized cosine retrieval
with `BAAI/bge-small-en-v1.5`, and reciprocal rank fusion (`k=60`) of their full
rankings. Retrieval is book-scoped and indexes `cleaned_text` only; pages with
no printed textbook-page mapping are excluded as front matter.

Outputs:

- `data/retrieval/page_level_results.jsonl`
- `reports/page_level_retrieval_metrics.json`
- `reports/page_level_retrieval_baseline.md`

Run all regression tests with:

```powershell
python -m unittest discover -s tests -v
```

## Recommended next research step

Create a manually checked retrieval benchmark containing `book_id`, chapter,
printed page(s), answer span, and `visual_dependency`/`formula_dependency`
labels. Evaluate page retrieval before section or chunk retrieval, and report
visual- and formula-dependent questions as separate slices.
