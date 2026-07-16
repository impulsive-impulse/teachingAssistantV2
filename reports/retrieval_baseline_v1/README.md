# Retrieval Baseline v1

Retrieval Baseline v1 freezes the verified winning experiment
`phase_h_h3_combined_specialist_priors` at semantic version `1.0.0`. The
machine-readable source of truth is
[`config/retrieval_baseline_v1.yaml`](../../config/retrieval_baseline_v1.yaml),
whose frozen SHA-256 is
`736fb9325794caead4439316b6ca546bd782cd7029b4f9f7788f545c5b43baa6`.

## Frozen pipeline

The caller supplies a student question and explicit `book_id`. Ordered static
textbook-synonym rules append retrieval vocabulary when all rule triggers are
present. Within that book, fixed 600-token chunks with approximately 100-token
whole-boundary overlap are ranked independently by local Okapi BM25 and
normalized cosine similarity using `BAAI/bge-small-en-v1.5` revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`.

Static query-only rules may activate formula equation-context, repeated-header
table-row, or visual caption-context page representations. Each specialist
combines dense and BM25 page rankings with RRF, lifts page order to child
chunks, and contributes one equal-weight ranking. Full rankings are fused with
RRF `k=60`, stable corpus-order ties, and no reranker. The runtime returns five
chunks. It then removes exact 8–140-word suffix/prefix overlap in rank order and
preserves each source chunk's rank, pages, chapter, section, scores, and
retriever provenance.

Gold evidence and benchmark dependency flags are unavailable to the production
runtime. They are read only by the separate evaluation command after complete
rankings exist.

## Frozen benchmark results

The original selected-run measurements are authoritative. Fresh timing and
memory are validation observations, not replacements.

| Slice | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---:|---:|---:|---:|---:|
| Overall | 61 | 26 (42.6%) | 44 (72.1%) | 50 (82.0%) | 0.601 |
| Canonical | 41 | 17 (41.5%) | 31 (75.6%) | 34 (82.9%) | 0.602 |
| Natural student | 20 | 9 (45.0%) | 13 (65.0%) | 16 (80.0%) | 0.599 |
| Biology | 30 | 16 (53.3%) | 24 (80.0%) | 28 (93.3%) | 0.702 |
| Physical Sciences | 31 | 10 (32.3%) | 20 (64.5%) | 22 (71.0%) | 0.504 |
| Formula-dependent | 16 | 5 (31.3%) | 9 (56.3%) | 10 (62.5%) | 0.478 |
| Table-dependent | 3 | 3 (100%) | 3 (100%) | 3 (100%) | 1.000 |
| Visual-dependent | 6 | 3 (50.0%) | 6 (100%) | 6 (100%) | 0.667 |
| Multi-page | 21 | 8 (38.1%) | 15 (71.4%) | 17 (81.0%) | 0.567 |
| Multi-chunk | 27 | 10 (37.0%) | 19 (70.4%) | 23 (85.2%) | 0.565 |
| Easy | 9 | 6 (66.7%) | 9 (100%) | 9 (100%) | 0.833 |
| Medium | 33 | 15 (45.5%) | 22 (66.7%) | 24 (72.7%) | 0.590 |
| Hard | 19 | 5 (26.3%) | 13 (68.4%) | 17 (89.5%) | 0.511 |

Natural query-style slices and every other preserved slice are in
[`metrics.json`](metrics.json). The original warm p95 was `71.169 ms` and peak
RSS was `688.223 MB`. The clean validation on the same CPU host reproduced all
effectiveness counts and MRR exactly; its warm p95 was `84.943 ms` and peak RSS
was `677.227 MB`. These operational differences are environment-sensitive.

## Stable interface

Python callers use:

```python
from textbook_audit.retrieval_baseline import retrieve

result = retrieve("How do plants eat?", "biology", include_text=True)
```

`RetrievalResult.evidence` contains exactly five structured `EvidenceResult`
objects. The `balanced` and `quality` profile names are supported compatibility
aliases for this same frozen pipeline; they do not select different behavior.

## Canonical commands

Run from the repository root with the tested x64 environment:

```powershell
# 1. Prepare the corpus.
temp\python-x64\python.exe scripts\audit_textbooks.py

# 2. Build indexes or validate/reuse every cache.
temp\python-x64\python.exe scripts\manage_retrieval_baseline_v1.py build

# 3. Validate config, full benchmark, golden fixture, determinism, and manifest.
temp\python-x64\python.exe scripts\manage_retrieval_baseline_v1.py validate

# 4. Re-run the full benchmark evaluation without the golden checks.
temp\python-x64\python.exe scripts\manage_retrieval_baseline_v1.py evaluate

# 5. Query one book.
temp\python-x64\python.exe scripts\query_final_pipeline.py `
  "How do plants eat?" --book-id biology --include-text

# 6. Rebuild only the named v1 indexes from scratch.
temp\python-x64\python.exe scripts\manage_retrieval_baseline_v1.py build --force-rebuild

# 7. Verify every repository artifact checksum in the manifest.
temp\python-x64\python.exe scripts\manage_retrieval_baseline_v1.py checksums
```

The fixture is
[`tests/fixtures/retrieval_baseline_v1_golden.json`](../../tests/fixtures/retrieval_baseline_v1_golden.json).
The complete provenance record is [`manifest.json`](manifest.json).

## Immutability policy

Retrieval Baseline v1 is frozen. Any change to its model/revision, corpus,
chunking, tokenization, query rules, specialist representations or activation,
BM25, fusion, candidate limits, context assembly, metadata, or defaults must
create a new semantic baseline version and metrics report. The v1 config,
manifest, metrics, fixture, and historical experiment outputs must remain
available and unchanged. New versions must compare themselves explicitly with
v1; they may never silently reinterpret v1 defaults.
