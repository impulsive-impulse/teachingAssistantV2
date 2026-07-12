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
