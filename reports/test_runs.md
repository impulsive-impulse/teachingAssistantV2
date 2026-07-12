# Test Run Log

Brief, append-only record of meaningful validation runs. Add one row after a
change is tested; keep commands and outcomes concise.

| Date | Change tested | Command | Result |
|---|---|---|---|
| 2026-07-12 | Initial page-retrieval implementation and regressions | `python -m unittest discover -s tests -v` | PASS — 11 tests |
| 2026-07-12 | End-to-end BM25, BGE-small, and hybrid evaluation with cached page embeddings | `python scripts/run_page_retrieval.py --device cpu` | PASS — 40 questions, 600 result rows, all reports generated |
| 2026-07-12 | Explanatory docstrings and inline comments | `python -m unittest discover -s tests -v`; `python -m py_compile src/textbook_audit/retrieval.py scripts/run_page_retrieval.py tests/test_retrieval.py`; `git diff --check` | PASS — 11 tests, compilation clean, no diff errors |
| 2026-07-12 | Test-log evaluation summary | Compared log values with `reports/page_level_retrieval_metrics.json`; `git diff --check` | PASS — all headline values match generated metrics |

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
