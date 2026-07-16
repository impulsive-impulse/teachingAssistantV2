# Class 10 textbook corpus extraction audit

This repository contains the Milestone 1 corpus preparation pipeline for a
textbook-grounded QA/RAG research project. It extracts every PDF page, preserves
PDF and printed-page identity, assigns index-grounded chapters, and produces a
human-readable suitability audit.

The repository also includes page-level and chunk-level retrieval baselines. They
do not call an LLM or implement answer generation, query rewriting, or reranking.

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
scripts/run_page_retrieval.py  Page-level retrieval source entry point
scripts/run_chunk_retrieval.py Chunk-level retrieval source entry point
scripts/run_hierarchical_retrieval.py
                               Hierarchical retrieval source entry point
scripts/run_candidate_complementarity.py
                               Existing-retriever candidate audit entry point
src/textbook_audit/
  config.py                    Immutable book/chapter/page-offset catalog
  cli.py                       Command-line interface
  pipeline.py                  Extraction, mapping, cleaning, and reporting
  retrieval.py                 Page BM25, dense, RRF, metrics, and reporting
  chunk_retrieval.py           Chunking, chunk retrieval, gold mapping, reports
  hierarchical_retrieval.py    Chapter/section/paragraph hierarchy and retrieval
  candidate_complementarity.py Evidence normalization, unions, overlap, decisions
tests/test_pipeline.py         Mapping and artifact integrity checks
tests/test_retrieval.py        Loading, ranking, matching, and metric regressions
tests/test_chunk_retrieval.py  Chunk boundaries, metadata, gold, and metrics tests
tests/test_hierarchical_retrieval.py
                               Hierarchy detection and ranking regressions
tests/test_candidate_complementarity.py
                               Deduplication, oracle, overlap, and slice regressions
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
The current reviewed set contains 66 questions: 46 canonical rows and 20
natural-student paraphrases. There are 61 answerable questions and 5 confirmed
negative/weak-evidence questions. The `_candidates` artifacts remain the
original 40-row proposal set and are not evaluation inputs.

Rebuild and validate the approved natural-student slice before retrieval runs:

```powershell
python scripts/expand_natural_student_benchmark.py
```

This idempotent command preserves canonical wording, derives each natural row
from its `parent_question_id`, and verifies inherited page mappings and answer
spans against both processed page records and the source PDFs. It writes
`reports/natural_student_query_additions.md`. Do not use it to introduce
unreviewed questions; its definitions represent the approved proposal.

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

Metrics and result rows carry `benchmark_slice`, `parent_question_id`, and
`query_style` where applicable. Page, chunk, and hierarchy reports compare the
canonical and `natural_student` slices separately; JSON metrics additionally
break natural-student performance down by query style.

## Chunk-Level Retrieval Baseline v1

Run the fixed-size and structure-aware experiment after the page baseline:

```powershell
python scripts/run_chunk_retrieval.py --device cpu
```

Equivalent installed entry point:

```powershell
chunk-retrieval --root X:\teachingAssistantV2 --top-k 5 --fixed-size 400 --overlap 80 --structured-min 250 --structured-max 500
```

Fixed chunks target 400 tokens with an 80-token overlap and do not cross chapter
boundaries. Structured chunks use chapter, section, paragraph, sentence, and
page-continuation boundaries, normally targeting 250–500 tokens. Both preserve
all contributing PDF/textbook pages and source indicators. Gold chunks are
derived after ranking from reviewed pages plus contiguous answer-span overlap;
uncertain mappings are reported for review and excluded from metrics.

Chunk embeddings have separate strategy/book caches under
`data/retrieval/cache/`. Use `--cache-dir`, `--results`, `--metrics`, and
`--report` to override output locations, and `--gold-min-coverage` to configure
the conservative automatic gold-mapping threshold.

Outputs:

- `data/processed/biology_chunks_fixed.jsonl`
- `data/processed/biology_chunks_structured.jsonl`
- `data/processed/physical_sciences_chunks_fixed.jsonl`
- `data/processed/physical_sciences_chunks_structured.jsonl`
- `data/retrieval/chunk_level_results.jsonl`
- `reports/chunk_level_retrieval_metrics.json`
- `reports/chunk_level_retrieval_baseline.md`

## Hierarchical Chunking and Retrieval v1

Run the chapter → section → paragraph-group experiment after the earlier
baselines so their metrics are available for comparison:

```powershell
python scripts/run_hierarchical_retrieval.py --device cpu
```

Equivalent installed entry point:

```powershell
hierarchical-retrieval --root X:\teachingAssistantV2 --chapter-k 3 --section-k 8 --paragraph-target 250 --paragraph-min 150 --paragraph-max 350
```

Chapter assignment uses the verified chapter-map PDF ranges, excluding all
pages outside those ranges. Numbered headings create high-confidence sections;
conservative page-title matches may create medium-confidence sections. Leaf
paragraph groups are the final targets. Strict cascade filters through top
chapters and sections, while soft fusion combines paragraph and parent ranks
without eliminating any paragraph.

Hierarchy-level embeddings use `BAAI/bge-small-en-v1.5` and are cached by book
and level. Long section vectors are normalized means of child paragraph
vectors; chapter vectors aggregate section vectors with a separately embedded
chapter title. Useful options include `--section-weight`, `--chapter-weight`,
`--gold-min-coverage`, `--cache-dir`, and all output-path overrides.

Outputs:

- `data/processed/biology_hierarchy.jsonl`
- `data/processed/physical_sciences_hierarchy.jsonl`
- `data/retrieval/hierarchical_results.jsonl`
- `reports/hierarchical_retrieval_metrics.json`
- `reports/hierarchical_retrieval_baseline.md`
- `reports/hierarchy_detection_audit.md`

## Candidate Complementarity Audit v1

Run the complementarity audit after the three retrieval baselines exist:

```powershell
python scripts/run_candidate_complementarity.py --device cpu
```

Equivalent installed entry point:

```powershell
candidate-complementarity --root X:\teachingAssistantV2 --depths 5 10 20
```

The audit does not add a retriever or reranker. It reconstructs the existing
page, fixed/structured chunk, strict-cascade, and soft-fusion rankings to depth
20 while reusing the validated BGE-small embedding caches. Existing baseline
result and report files are not rewritten. Use `--benchmark`, `--results`,
`--metrics`, `--report`, `--cache-dir`, `--depths`, and
`--gold-min-coverage` to override defaults.

Each union member contributes its own top-K list before deterministic
cross-method deduplication. Evidence is considered duplicate only when it
shares a source PDF page and has at least 80% five-token-shingle containment.
A candidate is correct only when it is on a reviewed primary/alternative page
and satisfies the baseline's contiguous answer-span coverage rule; gold labels
never influence ranking.

Outputs:

- `data/retrieval/candidate_complementarity_results.jsonl`
- `reports/candidate_complementarity_metrics.json`
- `reports/candidate_complementarity_audit.md`

## Local Cross-Encoder Reranking Baseline v1

Run the local reranker after the candidate-complementarity artifact exists:

```powershell
python scripts/run_reranker.py --device cpu --batch-size 32 --candidate-budgets 10 20
```

Equivalent installed entry point:

```powershell
local-reranker --root X:\teachingAssistantV2 --device cpu --batch-size 32
```

The runner loads the four audited depth-20 source rankings (Page BGE-small,
Fixed 400/80 BM25, Fixed 400/80 BGE-small, and Soft-fusion Hybrid), joins their
IDs to full processed text, deduplicates evidence, and caps the deterministic
RRF pool at 20. It then scores every query/passage pair locally with
`BAAI/bge-reranker-base` through Sentence Transformers `CrossEncoder`.

Model files are cached under `data/retrieval/cache/models/`. Passage content is
whitespace-normalized and limited to 1,800 characters at a word boundary; the
complete model pair is also capped at 512 tokens. Use `--model-name`,
`--model-cache`, `--candidate-budgets`, `--batch-size`, `--device`, and output
path options to override defaults. CPU is the portable default; `--device cuda`
requires a CUDA-enabled PyTorch runtime. A physical Windows GPU is not enough
when PyTorch has no compatible backend (for example, the Adreno/ARM test host).

Outputs:

- `data/retrieval/reranker_results.jsonl`
- `reports/reranker_metrics.json`
- `reports/reranker_baseline.md`

## Long-lived local RAG experiments

The approved research loop starts by repairing candidate compression before
introducing another model. Run the controlled Phase A comparison from a source
checkout with:

```powershell
temp\python-x64\python.exe scripts\run_candidate_compression.py --stage all
```

For inspection or recovery, the two stages can be run independently with
`--stage a1` and `--stage a2`. A single registered selector can be diagnosed
without changing the plan, for example:

```powershell
temp\python-x64\python.exe scripts\run_candidate_compression.py `
  --stage single --selector plain_rrf --dedup-threshold 0.8
```

Each completed configuration has an immutable directory under
`reports/experiments/runs/`. The append-only run history is
`reports/experiments/experiment_runs.jsonl`; current state, the sortable
leaderboard, important decisions, and restart instructions live alongside it.
Candidate construction uses source ranks and candidate text only. Reviewed
gold evidence is read only after selection to compute recall and ranking
metrics. Phase A rejects compression that loses accepted evidence available in
the four source rankings.

Phase B compares deterministic candidate text representations without using
gold labels for selection. Reproduce its successive-narrowing stages in order:

```powershell
temp\python-x64\python.exe scripts\run_candidate_representation.py --stage prescreen
temp\python-x64\python.exe scripts\run_candidate_representation.py --stage member_prescreen
temp\python-x64\python.exe scripts\run_candidate_representation.py --stage combination_prescreen
temp\python-x64\python.exe scripts\run_candidate_representation.py --stage boundary_prescreen
temp\python-x64\python.exe scripts\run_candidate_representation.py --stage rerank
```

Completed stage/run IDs are skipped on rerun rather than overwritten. The
Phase B comparison report is
`reports/experiments/phase_b_candidate_representation.md`; the retained
representation uses the query-dense-best duplicate member, two non-overlapping
query-relevant page windows, and neighbouring chunk context.

Phase C reuses those cached full-pool scores to compare fusion logic, then
audits 8/10/15-candidate preselectors before allowing another expensive model
call:

```powershell
temp\python-x64\python.exe scripts\run_fusion_reranking.py --stage all
```

Use `--stage logic` or `--stage budgets` for an isolated resumable stage. The
report is `reports/experiments/phase_c_fusion_reranking.md`. A capped run that
loses accepted evidence is recorded and rejected before the stronger reranker
runs; existing Phase B scores are never presented as newly measured inference.

Phase D runs pinned local cross-encoders over the retained full pool. Reproduce
the retained MiniLM run and finalize the successive-stopping decision with:

```powershell
temp\python-x64\python.exe scripts\run_reranker_bakeoff.py `
  --model minilm_l6 --device cpu --batch-size 32 --maximum-length 512
temp\python-x64\python.exe scripts\run_reranker_bakeoff.py --finalize
```

The generic runner also supports `bge_v2_m3` and `mxbai_base_v1` plus
`--screen-per-group 2`. Their pinned snapshots must already exist in
`data/retrieval/cache/models`; inference always sets `local_files_only=True`.
The Phase D report records the rejected BGE-v2 screen and runtime-infeasible
mxbai attempt without treating either as a full benchmark result.

Phase E compares only approved, pinned local embedding models on the same
front-matter-free fixed 400/80 corpus. Reproduce an individual run with the
model-specific flags shown by `--help`; completed run IDs and fingerprinted
indexes are reused. Finalize the retained lightweight and quality models with:

```powershell
temp\python-x64\python.exe scripts\run_embedding_bakeoff.py --apply-bge-gate
temp\python-x64\python.exe scripts\run_embedding_bakeoff.py --finalize-phase-e
```

Phase F uses successive narrowing: screen every approved chunk corpus with
BM25, encode only three finalists with E5-large-v2, evaluate page-aware
methods, then confirm the winner with BGE-small. Run the resumable stages in
order:

```powershell
temp\python-x64\python.exe scripts\run_chunking_bakeoff.py --stage bm25_screen
temp\python-x64\python.exe scripts\run_chunking_bakeoff.py --stage e5_finalists --device cpu --batch-size 8
temp\python-x64\python.exe scripts\run_chunking_bakeoff.py --stage multi_granularity --device cpu --batch-size 8
temp\python-x64\python.exe scripts\run_chunking_bakeoff.py --stage bge_confirmation --device cpu --batch-size 16
```

The retained lightweight Phase F retriever is BGE-small fixed 600/100 Hybrid
RRF. The retained E5 quality method adds the parent-page ranking as a third RRF
prior. Full configurations, candidate recall, slice metrics, and complete
rankings are under `reports/experiments/runs/`; the compact comparison is in
`reports/experiments/phase_f_chunking_bakeoff.md`.

Phase G screens deterministic query processing on that balanced pipeline and
stores every processed query plus its fired static rules. Run:

```powershell
temp\python-x64\python.exe scripts\run_query_processing.py --stage screen --device cpu --batch-size 16
temp\python-x64\python.exe scripts\run_query_processing.py --stage fusion --device cpu --batch-size 16
```

The retained deterministic method appends neutral textbook aliases while
keeping the student's original wording. Original-plus-expanded source fusion
was measured but was slower and weaker. See
`reports/experiments/phase_g_query_processing.md` for the comparison. Local
Gemma rewriting is a separate approval gate and is not started by these
commands.

Phase H adds static, gold-blind textbook specialists for equations, tables,
and nearby figure captions, then tests distributed evidence selectors. The
visual-asset command extracts embedded PDF rasters for a capability audit; it
does not run an unapproved multimodal model.

```powershell
temp\python-x64\python.exe scripts\run_specialist_retrieval.py --stage screen --device cpu --batch-size 16
temp\python-x64\python.exe scripts\run_specialist_retrieval.py --stage formula_activation_v2 --device cpu --batch-size 16
temp\python-x64\python.exe scripts\run_specialist_retrieval.py --stage table_activation_v2 --device cpu --batch-size 16
temp\python-x64\python.exe scripts\run_specialist_retrieval.py --stage combined --device cpu --batch-size 16
temp\python-x64\python.exe scripts\extract_visual_assets.py
temp\python-x64\python.exe scripts\run_evidence_sets.py
```

The retained combined specialist ranking reaches 26/44/50 Hit@1/3/5 and 0.601
MRR. The final distributed-evidence gate keeps its unmodified top five: a
coverage-diversity alternative completes one extra multi-page label but loses
four accepted-evidence hits. See
`reports/experiments/phase_h_specialist_retrieval.md` and
`reports/experiments/phase_h_distributed_evidence.md`.

Phase I compares top-K, hard token budgets, overlap/same-page merging,
redundancy removal, diversity, and output order over that fixed top-five pool:

```powershell
temp\python-x64\python.exe scripts\run_context_assembly.py
```

Overlap-aware merging is retained because it preserves all 50/61 accepted
chunks and 55/61 complete reviewed page sets available in the top five while
reducing average context from 3,000 to 2,965 word tokens. Inspect the comparison
in `reports/experiments/phase_i_context_assembly.md` and per-question assembled
text under
`reports/experiments/runs/phase_i_i0_overlap_merge_metadata_preserving/contexts.jsonl`.
Each merged context includes a `source_metadata` entry for every contributing
chunk, retaining its rank, PDF/textbook pages, chapter, and section.

Generate the final comparable leaderboard, Pareto frontier, selected pipeline
configurations, failure audit, and architecture handoff with:

```powershell
python scripts\finalize_experiments.py
```

Query the frozen winning pipeline without benchmark labels:

```powershell
temp\python-x64\python.exe scripts\query_final_pipeline.py `
  "How do plants eat?" --book-id biology --include-text
```

The authoritative handoff is
`reports/experiments/final_experiment_report.md`; machine-readable selections
are in `reports/experiments/final_pipeline_selection.json`, with the full
comparable leaderboard and Pareto frontier beside them as CSV files.

## Retrieval Baseline v1 (frozen)

The verified winner is frozen as Retrieval Baseline v1 (`1.0.0`). Its only
behavioral source of truth is `config/retrieval_baseline_v1.yaml`; the public
Python interface is
`textbook_audit.retrieval_baseline.retrieve(question, book_id, config,
include_text, profile)` and the source-checkout CLI is
`scripts/query_final_pipeline.py`.

The baseline uses fixed 600/100 chunks, local Okapi BM25, normalized
`BAAI/bge-small-en-v1.5` revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, deterministic synonym expansion,
query-activated formula/table/visual page priors, equal-weight RRF `k=60`, five
results, and metadata-preserving exact-overlap assembly. It reproduced
26/44/50 Hit@1/3/5 and 0.601 MRR on 61 answerable rows.

Canonical commands:

```powershell
temp\python-x64\python.exe scripts\manage_retrieval_baseline_v1.py build
temp\python-x64\python.exe scripts\manage_retrieval_baseline_v1.py validate
temp\python-x64\python.exe scripts\manage_retrieval_baseline_v1.py evaluate
temp\python-x64\python.exe scripts\manage_retrieval_baseline_v1.py checksums
temp\python-x64\python.exe scripts\query_final_pipeline.py `
  "How do plants eat?" --book-id biology --include-text
```

Use `build --force-rebuild` to recreate only the named v1 indexes. Corpus
preparation remains `scripts/audit_textbooks.py`. See
`reports/retrieval_baseline_v1/README.md` for the architecture, complete frozen
metrics, provenance manifest, golden fixture, all rebuild commands, and the
immutability policy.

### Experiment artifact retention

Git tracks every run's compact `configuration.json` and `metrics.json`, the
append-only run ledger, current state, decisions, summary reports, final
leaderboard, Pareto frontier, and
`reports/experiments/experiment_artifact_manifest.jsonl`. The manifest records
the owner run, byte size, and SHA-256 digest for every declared run artifact.

Complete per-query rankings, representations, candidate pools, evidence sets,
and assembled contexts remain under `reports/experiments/runs/` locally but are
gitignored because they total roughly 900 MB. They can be regenerated with the
per-run commands in `experiment_runs.jsonl`; this keeps traceability without
bloating normal clones. The selected smoke-query outputs and final reports are
tracked directly.

Run all regression tests with:

```powershell
python -m unittest discover -s tests -v
```

To reproduce every benchmark artifact in dependency order:

```powershell
python scripts/expand_natural_student_benchmark.py
python scripts/run_page_retrieval.py --device cpu
python scripts/run_chunk_retrieval.py --device cpu
python scripts/run_hierarchical_retrieval.py --device cpu
python scripts/run_candidate_complementarity.py --device cpu
python scripts/run_reranker.py --device cpu --batch-size 32
python scripts/expand_natural_student_benchmark.py
python -m unittest discover -s tests -v
```

The second expansion command refreshes the additions report with the newly
generated slice metrics. On Windows ARM64, use an x64 Python runtime under
Windows emulation because official PyTorch Windows wheels target x86-64.

Keep brief validation history in `reports/test_runs.md`. After a meaningful
change, append one row describing what was tested, the command, and the result.

## Recommended next research step

Create and review a generation benchmark before Phase J. It must label answer
correctness, faithfulness to supplied context, citation support, and abstention
for the five negative questions. Answer generation remains blocked until that
benchmark exists; neither the separately gated Gemma rewrite nor a multimodal
encoder was downloaded or run.
