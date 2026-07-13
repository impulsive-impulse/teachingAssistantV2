# Test Run Log

Brief, append-only record of meaningful validation runs. Add one row after a
change is tested; keep commands and outcomes concise.

| Date | Change tested | Command | Result |
|---|---|---|---|
| 2026-07-12 | Initial page-retrieval implementation and regressions | `python -m unittest discover -s tests -v` | PASS — 11 tests |
| 2026-07-12 | End-to-end BM25, BGE-small, and hybrid evaluation with cached page embeddings | `python scripts/run_page_retrieval.py --device cpu` | PASS — 40 questions, 600 result rows, all reports generated |
| 2026-07-12 | Explanatory docstrings and inline comments | `python -m unittest discover -s tests -v`; `python -m py_compile src/textbook_audit/retrieval.py scripts/run_page_retrieval.py tests/test_retrieval.py`; `git diff --check` | PASS — 11 tests, compilation clean, no diff errors |
| 2026-07-12 | Test-log evaluation summary | Compared log values with `reports/page_level_retrieval_metrics.json`; `git diff --check` | PASS — all headline values match generated metrics |
| 2026-07-12 | Chunk construction, source metadata, conservative gold mapping, and metric exclusions | `python -m unittest tests.test_chunk_retrieval -v` | PASS — 7 chunk regressions |
| 2026-07-12 | End-to-end fixed and structured chunk retrieval with BM25, BGE-small, and RRF | `python scripts/run_chunk_retrieval.py --device cpu` | PASS — 40 questions, 1,200 result rows, 4 strategy/book embedding caches, all reports generated |
| 2026-07-12 | Final consecutive-section boundary fix and complete regression suite | `python -m unittest discover -s tests -v`; `python -m py_compile src/textbook_audit/chunk_retrieval.py scripts/run_chunk_retrieval.py tests/test_chunk_retrieval.py`; `git diff --check` | PASS — 18 tests, compilation clean, no diff errors |
| 2026-07-12 | Hierarchy detection, aggregation, strict filtering, soft fusion, gold matching, and metrics | `python -m unittest tests.test_hierarchical_retrieval -v` | PASS — 9 hierarchical regressions |
| 2026-07-12 | End-to-end hierarchical retrieval with level-specific BGE caches | `python scripts/run_hierarchical_retrieval.py --device cpu` | PASS — 40 questions, 1,200 result rows, hierarchy audit and reports generated |
| 2026-07-12 | Full post-implementation regression and artifact-integrity check | `python -m unittest discover -s tests -v`; `python -m py_compile src/textbook_audit/hierarchical_retrieval.py scripts/run_hierarchical_retrieval.py tests/test_hierarchical_retrieval.py`; JSON/JSONL validation; `git diff --check` | PASS — 27 tests, all definitions documented, 1,200 valid result rows |
| 2026-07-13 | Manual gold review for BIO-003/PSC-007 and six conversational query additions | Benchmark schema, source-page, normalized-span, ID, status, and hierarchy-mapping validation | PASS — 46 unique rows, 41 answerable, 5 negative; no uncertain hierarchy mappings |
| 2026-07-13 | Expanded benchmark across page, chunk, and hierarchical baselines | `python scripts/run_page_retrieval.py --device cpu`; `python scripts/run_chunk_retrieval.py --device cpu`; `python scripts/run_hierarchical_retrieval.py --device cpu` | PASS — 690 page rows, 1,380 chunk rows, 1,380 hierarchy rows; reports regenerated |
| 2026-07-14 | Approved 20-question natural-student slice, inherited-gold/PDF validation, slice metrics, and full regeneration | `python scripts/expand_natural_student_benchmark.py`; all three retrieval runners; `python -m unittest discover -s tests -v` | PASS — 66 questions, 61 scored and 5 negative; 990 page, 1,980 chunk, and 1,980 hierarchy result rows; 29 tests |

## Evaluation results — 2026-07-12

The reviewed evaluation set contained 40 questions: 36 answerable questions
used for Hit@K and MRR, plus 4 negative or weak-evidence questions reported
separately. Latency includes query-time retrieval only; model startup, corpus
loading, and page-embedding creation are excluded.

| Retriever | Hit@1 | Hit@3 | Hit@5 | MRR | Average latency (ms) | p95 latency (ms) |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 38.9% | 63.9% | 77.8% | 0.536 | 3.93 | 7.10 |
| BGE-small dense | 44.4% | 72.2% | 80.6% | 0.609 | 43.38 | 57.62 |
| Hybrid RRF | 50.0% | 72.2% | 80.6% | 0.634 | 47.84 | 62.89 |

Outcome: dense retrieval improved over BM25 at every effectiveness cutoff.
Hybrid RRF produced the best Hit@1 and MRR, but did not improve Hit@3 or Hit@5
over dense retrieval.

## Chunk evaluation results — 2026-07-12

All 36 answerable rows mapped reliably to answer-bearing chunks for both
strategies. The 4 negative rows remained separate. Latency excludes chunk
construction, model startup, and embedding creation.

| Retrieval unit | Retriever | Hit@1 | Hit@3 | Hit@5 | MRR | Average latency (ms) | p95 latency (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| Page | BM25 | 38.9% | 63.9% | 77.8% | 0.536 | 3.93 | 7.10 |
| Page | BGE-small dense | 44.4% | 72.2% | 80.6% | 0.609 | 43.38 | 57.62 |
| Page | Hybrid RRF | 50.0% | 72.2% | 80.6% | 0.634 | 47.84 | 62.89 |
| Fixed 400/80 | BM25 | 36.1% | 61.1% | 83.3% | 0.541 | 3.69 | 6.71 |
| Fixed 400/80 | BGE-small dense | 22.2% | 52.8% | 66.7% | 0.423 | 36.37 | 40.90 |
| Fixed 400/80 | Hybrid RRF | 27.8% | 69.4% | 77.8% | 0.504 | 40.52 | 46.25 |
| Structured 250–500 | BM25 | 19.4% | 61.1% | 77.8% | 0.423 | 3.26 | 5.97 |
| Structured 250–500 | BGE-small dense | 22.2% | 61.1% | 72.2% | 0.447 | 31.05 | 37.51 |
| Structured 250–500 | Hybrid RRF | 27.8% | 69.4% | 80.6% | 0.500 | 34.74 | 41.56 |

Outcome: fixed chunks improved BM25 Hit@5 by 5.5 points over pages, but dense
chunk retrieval regressed. Structure-aware hybrid matched page dense/hybrid at
Hit@5, with lower MRR. Fixed 400/80 is the default lexical chunk baseline;
neighbour expansion is the next controlled experiment.

## Hierarchical evaluation results — 2026-07-12

The conservative automatic mapper scored 34 answerable questions. `BIO-003`
and `PSC-007` require manual paragraph-gold review; four negative questions
remain excluded. Latency excludes hierarchy construction and embedding creation.

| Approach | Retriever | Hit@1 | Hit@3 | Hit@5 | MRR | Average latency (ms) | p95 latency (ms) |
|---|---|---:|---:|---:|---:|---:|---:|
| Strict cascade | BM25 | 14.7% | 38.2% | 44.1% | 0.257 | 7.75 | 14.24 |
| Strict cascade | BGE-small dense | 35.3% | 61.8% | 70.6% | 0.503 | 45.02 | 53.60 |
| Strict cascade | Hybrid RRF | 44.1% | 52.9% | 67.6% | 0.521 | 53.64 | 69.81 |
| Soft fusion | BM25 | 29.4% | 55.9% | 70.6% | 0.449 | 10.91 | 17.43 |
| Soft fusion | BGE-small dense | 35.3% | 61.8% | 73.5% | 0.511 | 48.29 | 57.56 |
| Soft fusion | Hybrid RRF | 44.1% | 61.8% | 79.4% | 0.572 | 56.87 | 73.26 |

Outcome: soft Hybrid is the best hierarchical variant, but it neither exceeds
fixed BM25 Hit@5 of 83.3% nor preserves page Hybrid MRR of 0.634. Hierarchical
retrieval should remain an experiment rather than the default architecture.

## Expanded benchmark evaluation — 2026-07-13

The reviewed benchmark was expanded to 46 questions: 41 answerable and 5
negative. BIO-003 and PSC-007 were manually corrected; six conversational
stress queries were added. All three baselines were regenerated from their
existing embedding caches.

| Retrieval unit / approach | Retriever | Hit@1 | Hit@3 | Hit@5 | MRR | Avg ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|
| Page | BM25 | 36.6% | 56.1% | 68.3% | 0.491 | 3.42 | 6.75 |
| Page | BGE-small dense | 43.9% | 68.3% | 73.2% | 0.589 | 40.75 | 61.09 |
| Page | Hybrid RRF | 46.3% | 63.4% | 73.2% | 0.585 | 44.60 | 65.73 |
| Fixed 400/80 | BM25 | 34.1% | 58.5% | 75.6% | 0.507 | 3.50 | 6.93 |
| Fixed 400/80 | BGE-small dense | 24.4% | 51.2% | 63.4% | 0.425 | 36.80 | 42.53 |
| Fixed 400/80 | Hybrid RRF | 26.8% | 63.4% | 70.7% | 0.471 | 40.74 | 49.53 |
| Structured | BM25 | 19.5% | 53.7% | 68.3% | 0.392 | 3.11 | 5.61 |
| Structured | BGE-small dense | 24.4% | 58.5% | 65.9% | 0.447 | 32.65 | 37.59 |
| Structured | Hybrid RRF | 26.8% | 61.0% | 73.2% | 0.467 | 36.18 | 42.16 |
| Strict cascade | BM25 | 14.6% | 34.1% | 39.0% | 0.241 | 4.12 | 7.41 |
| Strict cascade | BGE-small dense | 36.6% | 61.0% | 68.3% | 0.502 | 24.52 | 31.32 |
| Strict cascade | Hybrid RRF | 41.5% | 48.8% | 61.0% | 0.486 | 29.16 | 36.73 |
| Soft fusion | BM25 | 31.7% | 53.7% | 65.9% | 0.447 | 5.96 | 9.52 |
| Soft fusion | BGE-small dense | 34.1% | 61.0% | 70.7% | 0.497 | 26.30 | 33.27 |
| Soft fusion | Hybrid RRF | 43.9% | 58.5% | 73.2% | 0.552 | 30.95 | 38.64 |

Outcome: fixed 400/80 BM25 remains best at Hit@5 on the harder expanded set
(75.6%). Page dense has the best MRR (0.589), narrowly ahead of page Hybrid.

## Natural-student slice evaluation — 2026-07-14

Twenty approved natural queries were added without changing canonical queries
or gold evidence. All 20 answerable rows mapped automatically at chunk and
hierarchy levels; the five existing negatives remain separately reported.

| Retrieval unit / approach | Retriever | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|
| Page | BM25 | 20.0% | 40.0% | 50.0% | 0.360 |
| Page | BGE-small dense | 25.0% | 60.0% | 65.0% | 0.441 |
| Page | Hybrid RRF | 20.0% | 50.0% | 65.0% | 0.399 |
| Fixed 400/80 | BM25 | 15.0% | 35.0% | 55.0% | 0.335 |
| Fixed 400/80 | BGE-small dense | 15.0% | 45.0% | 55.0% | 0.342 |
| Fixed 400/80 | Hybrid RRF | 20.0% | 45.0% | 65.0% | 0.390 |
| Structured | BM25 | 15.0% | 30.0% | 45.0% | 0.305 |
| Structured | BGE-small dense | 15.0% | 40.0% | 50.0% | 0.322 |
| Structured | Hybrid RRF | 10.0% | 50.0% | 55.0% | 0.312 |
| Strict cascade | BM25 | 10.0% | 15.0% | 20.0% | 0.140 |
| Strict cascade | BGE-small dense | 15.0% | 45.0% | 55.0% | 0.336 |
| Strict cascade | Hybrid RRF | 25.0% | 40.0% | 55.0% | 0.365 |
| Soft fusion | BM25 | 25.0% | 45.0% | 55.0% | 0.375 |
| Soft fusion | BGE-small dense | 15.0% | 50.0% | 55.0% | 0.357 |
| Soft fusion | Hybrid RRF | 35.0% | 50.0% | 60.0% | 0.463 |

Outcome: natural wording is substantially harder than the canonical slice.
Page dense has the best natural-query MRR (0.441) among flat baselines; page
dense, page Hybrid, and fixed-chunk Hybrid tie for best Hit@5 at 65.0%.
