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
| 2026-07-14 | Local BGE cross-encoder reranking at candidate budgets 10 and 20 | `temp\python-x64\python.exe scripts\run_reranker.py --device cpu --batch-size 32`; full regression suite | PASS — 66 queries, 1,320 top-five rows; budget 10 reranker reached 36/61 Hit@5 at 7.0 s/query |
| 2026-07-16 | Phase A candidate preservation: rank fusion, quotas, source preservation, MMR, dedup thresholds, query-aware fusion, and lossless fallback | `temp\python-x64\python.exe scripts\run_candidate_compression.py --stage a1`; `--stage a2`; `--stage a3`; `--stage a4`; `temp\python-x64\python.exe -m unittest tests.test_candidate_compression -v` | PASS — 20 immutable runs; capped pools reached at most 59/61 recall; full deduplicated union retained 61/61 with 40.8 average candidates |
| 2026-07-16 | Phase B deterministic page/chunk representations and four full-pool BGE reranker finalists | five staged `scripts\run_candidate_representation.py` commands through `--stage rerank`; `python -m pytest tests\test_candidate_compression.py tests\test_candidate_representation.py -q` | PASS — 28 immutable Phase B runs, 12 regressions; retained two-window + neighbour representation reached 40/61 Hit@5 with 61/61 candidate recall |
| 2026-07-16 | Root test discovery excludes bundled x64 dependencies; full Phase A/B artifact validation | `python -m pytest -q`; JSON/JSONL/CSV parse; `python -m py_compile`; `git diff --check` | PASS — 57 tests; 97 JSON, 49 JSONL, and 1 CSV experiment artifacts valid; compilation and diff checks clean |
| 2026-07-16 | Phase C full-pool fusion and 8/10/15-candidate pre-rerank recall gates | `temp\python-x64\python.exe scripts\run_fusion_reranking.py --stage all`; `python -m pytest tests\test_fusion_reranking.py -q` | PASS — 13 immutable runs; 7 full-pool methods retained 61/61 recall; all 6 capped paths were rejected before stronger reranking |
| 2026-07-16 | Phase D pinned local reranker bake-off with successive runtime screens | MiniLM full run; balanced BGE-v2/mxbai screens; `python -m pytest tests\test_reranker_bakeoff.py -q` | PASS — MiniLM retained at 43/61 Hit@5 and 8.1 s p95; BGE-v2 full run rejected after 154.4 s screen p95; mxbai stopped after >300 s without a completed query |
| 2026-07-16 | Phase H equation/table/caption specialists, PDF raster capability audit, and distributed evidence selectors | specialist stages; `scripts\extract_visual_assets.py`; `scripts\run_evidence_sets.py`; focused regressions | PASS — combined specialists reached 26/44/50 H@1/3/5; 350/350 marked pages had extractable rasters; final gate retained base top-5 at 50/61 direct hits |
| 2026-07-16 | Phase I context assembly and shared context-metric checkpoint logging | `scripts\run_context_assembly.py`; focused regressions | PASS — overlap merge retained 50/61 exact accepted spans and 55/61 complete page sets at 2,965 average tokens |
| 2026-07-16 | Final Phase H/I reproducibility, full regressions, compilation, artifact parsing, and diff hygiene | both retained-stage reruns; `python -m pytest -q`; `python -m compileall -q src scripts tests`; JSON/JSONL/CSV parse; `git diff --check` | PASS — winners reproduced; 105 tests; 243 JSON, 120 JSONL, and 1 CSV artifacts valid; compilation and diff checks clean |
| 2026-07-16 | Final leaderboard/frontier handoff and arbitrary-query production CLI | `python scripts\finalize_experiments.py`; focused finalization/query tests; balanced and lightweight smoke queries for “How do plants eat?” | PASS — 39 comparable runs, 15 Pareto runs, all 11 top-5 failures listed; balanced query reused every cached index and ranked accepted photosynthesis evidence first |
| 2026-07-16 | Full completion audit after final handoff | `python -m pytest -q`; `python -m compileall -q src scripts tests`; parse all experiment JSON/JSONL/CSV; `git diff --check` | PASS — 111 tests; 120/120 immutable run records reconciled with state and declared outputs; 246 JSON, 120 JSONL, and 3 CSV files valid; compilation and diff checks clean |
| 2026-07-16 | Metadata-preserving Phase I winner | `scripts\run_context_assembly.py`; context/finalization regressions | PASS — versioned run preserves the same 50/61 spans, 55/61 complete page sets, and 2,965-token average while retaining rank/page/chapter/section metadata for all five source chunks |
| 2026-07-16 | Final post-metadata completion validation | balanced live query; `python -m pytest -q`; compilation; structured-artifact parse; `git diff --check` | PASS — balanced query ranked accepted evidence first with 5/5 provenance records and all caches hit; 112 tests; 121/121 runs reconciled; 248 JSON, 121 JSONL, and 3 CSV files valid |
| 2026-07-16 | Git publication structure and artifact traceability | regenerate final handoff/manifest; docstring audit; `python -m pytest -q`; compilation; `git diff --check` | PASS — 362 declared artifacts hash-manifested; 242 compact traceability artifacts retained for Git and 120 reproducible detail JSONL files ignored; commit payload reduced from ~903 MB to ~4.6 MB; 112 tests passed |

## Phase B evaluation results — 2026-07-16

All runs use the same lossless Phase A candidate union and local
`BAAI/bge-reranker-base` model. Latency includes representation construction
and warm cross-encoder scoring on CPU; the five negative/weak-evidence rows are
excluded from retrieval metrics.

| Representation | Hit@1 | Hit@3 | Hit@5 | MRR | Natural Hit@1 | Natural Hit@3 | Natural Hit@5 | p95 latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Shortest member + leading page text + headings | 13/61 (21.3%) | 28/61 (45.9%) | 31/61 (50.8%) | 0.372 | 3/20 (15.0%) | 10/20 (50.0%) | 11/20 (55.0%) | 33.8 s |
| Dense-best member + leading page text + headings | 17/61 (27.9%) | 29/61 (47.5%) | 35/61 (57.4%) | 0.409 | 4/20 (20.0%) | 9/20 (45.0%) | 13/20 (65.0%) | 36.3 s |
| Dense-best member + leading page text + neighbours | 16/61 (26.2%) | 27/61 (44.3%) | 37/61 (60.7%) | 0.408 | 3/20 (15.0%) | 8/20 (40.0%) | 14/20 (70.0%) | 40.7 s |
| Dense-best member + two page windows + neighbours (retained) | 16/61 (26.2%) | 31/61 (50.8%) | 40/61 (65.6%) | 0.422 | 4/20 (20.0%) | 10/20 (50.0%) | 15/20 (75.0%) | 48.3 s |

Outcome: targeted windows plus neighbouring context produced the strongest
Hit@3, Hit@5, MRR, and natural-student Hit@5, but not the strongest Hit@1 and
with a material CPU latency cost. Phase C must therefore retain a lighter
representation on the quality–latency frontier while testing smaller budgets.

## Phase C evaluation results — 2026-07-16

| Full-pool method | Hit@1 | Hit@3 | Hit@5 | MRR | Natural Hit@1 | Natural Hit@3 | Natural Hit@5 | p95 latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Soft-fusion-ranked deduplicated union (retained lightweight) | 26/61 (42.6%) | 37/61 (60.7%) | 47/61 (77.0%) | 0.557 | 7/20 (35.0%) | 10/20 (50.0%) | 14/20 (70.0%) | 0.2 ms |
| Plain RRF | 15/61 (24.6%) | 24/61 (39.3%) | 29/61 (47.5%) | 0.373 | 5/20 (25.0%) | 7/20 (35.0%) | 9/20 (45.0%) | 0.2 ms |
| Weighted RRF | 16/61 (26.2%) | 23/61 (37.7%) | 29/61 (47.5%) | 0.379 | 5/20 (25.0%) | 6/20 (30.0%) | 9/20 (45.0%) | 0.2 ms |
| BGE reranker score | 16/61 (26.2%) | 31/61 (50.8%) | 40/61 (65.6%) | 0.422 | 4/20 (20.0%) | 10/20 (50.0%) | 15/20 (75.0%) | 47.0 s |
| BGE rank + RRF rank (retained quality) | 16/61 (26.2%) | 32/61 (52.5%) | 41/61 (67.2%) | 0.432 | 5/20 (25.0%) | 12/20 (60.0%) | 15/20 (75.0%) | 47.0 s |
| BGE score + normalized RRF | 14/61 (23.0%) | 21/61 (34.4%) | 28/61 (45.9%) | 0.366 | 5/20 (25.0%) | 7/20 (35.0%) | 10/20 (50.0%) | 47.0 s |
| BGE rank + Soft-fusion rank | 20/61 (32.8%) | 36/61 (59.0%) | 44/61 (72.1%) | 0.484 | 5/20 (25.0%) | 12/20 (60.0%) | 15/20 (75.0%) | 47.0 s |

| Preselector recall before reranking | Budget 8 | Budget 10 | Budget 15 |
|---|---:|---:|---:|
| RRF | 38/61 (62.3%) | 45/61 (73.8%) | 54/61 (88.5%) |
| Fast BM25 reranker | 42/61 (68.9%) | 46/61 (75.4%) | 50/61 (82.0%) |

Outcome: rank blending modestly improves BGE alone, but the deduplicated
Soft-fusion-ranked control remains the best balanced local result. Every tested
cap violates the pre-rerank recall invariant, so no stronger model was run on
those invalid pools.

## Phase D evaluation results — 2026-07-16

| Method | Scope | Hit@1 | Hit@3 | Hit@5 | MRR | Natural Hit@1/3/5 | p95 latency | Peak memory | Decision |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Soft-fusion-ranked control | 61 | 26/61 | 37/61 | 47/61 | 0.557 | 7/10/14 of 20 | 0.2 ms | no cross-encoder | Retain balanced |
| BGE-base rank + RRF | 61 | 16/61 | 32/61 | 41/61 | 0.432 | 5/12/15 of 20 | 47.0 s | 2,097 MiB | Superseded |
| MiniLM L6 rank + RRF | 61 | 14/61 | 33/61 | 43/61 | 0.421 | 6/13/16 of 20 | 8.1 s | 964 MiB | Retain reranker |
| BGE-v2-m3 | 8-row screen | 2/8 | 4/8 | 5/8 | 0.397 | 1/1/1 of 4 | 154.4 s | 2,817 MiB | Reject full run |
| mxbai-base-v1 | stopped screen | — | — | — | — | — | >300 s before first query | 1,121 MiB observed | Runtime infeasible |

Outcome: MiniLM is the only retained cross-encoder: it improves natural and
top-5 quality over BGE-base while cutting p95 latency by about 83%. It still
reduces overall Hit@1/MRR versus the near-free Soft-fusion-ranked control, so
that retrieval-only path remains the balanced default.

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

## Candidate complementarity audit — 2026-07-14

Change tested: added evidence-normalized top-5/10/20 candidate unions across all
15 existing page, chunk, and hierarchy variants. The run reused the committed
BGE-small caches, required contiguous answer-span evidence in addition to gold
page membership, and left all prior baseline outputs unchanged.

Commands:

```powershell
temp\python-x64\python.exe scripts\run_candidate_complementarity.py --device cpu
python -m unittest discover -s tests -v
```

Result: the audit completed from cached corpus embeddings and all 35 regression
tests passed. The detailed file contains 2,970 rows (66 questions × 15 methods ×
3 candidate depths).

| Primary retriever, all 61 answerable | Hit@5 | Hit@10 | Hit@20 | MRR |
|---|---:|---:|---:|---:|
| Page BGE-small | 38/61 (62.3%) | 49/61 (80.3%) | 56/61 (91.8%) | 0.441 |
| Page BM25 | 37/61 (60.7%) | 45/61 (73.8%) | 51/61 (83.6%) | 0.380 |
| Fixed 400/80 BM25 | 42/61 (68.9%) | 48/61 (78.7%) | 52/61 (85.2%) | 0.451 |
| Soft-fusion Hybrid | 42/61 (68.9%) | 47/61 (77.0%) | 52/61 (85.2%) | 0.523 |

| All-primary oracle slice | Oracle Hit@5 | Oracle Hit@10 | Oracle Hit@20 |
|---|---:|---:|---:|
| All answerable | 47/61 (77.0%) | 54/61 (88.5%) | 60/61 (98.4%) |
| Canonical | 34/41 (82.9%) | 37/41 (90.2%) | 40/41 (97.6%) |
| Natural student | 13/20 (65.0%) | 17/20 (85.0%) | 20/20 (100.0%) |

Outcome: Page BGE-small, Fixed 400/80 BM25, and Soft-fusion Hybrid each supply
unique top-20 wins; Page BM25 supplies none. The required unions miss only
BIO-017 at depth 20, while Fixed 400/80 dense retrieves it at rank 12, bringing
the full existing-method pool to 61/61. Candidate fusion plus reranking is
therefore justified; improving first-stage generation is not the immediate
bottleneck on this benchmark.

## Local cross-encoder reranking — 2026-07-14

Change tested: added deterministic four-source RRF pool construction,
cross-unit deduplication, local `BAAI/bge-reranker-base` scoring, 10/20 budget
comparison, required slices, negatives, and regression diagnostics.

Commands:

```powershell
temp\python-x64\python.exe scripts\run_reranker.py --device cpu --batch-size 32
temp\python-x64\python.exe -m unittest discover -s tests -v
```

The host exposes a Qualcomm Adreno X1-85 GPU, but Sentence Transformers uses
PyTorch and the available PyTorch 2.13 runtime has no compatible Adreno/DirectML
backend. The measured run therefore correctly used CPU; model files were cached
locally for subsequent runs.

| Method / budget | Hit@1 | Hit@3 | Hit@5 | MRR | Avg latency/query |
|---|---:|---:|---:|---:|---:|
| Page BGE-small source | 16/61 (26.2%) | 33/61 (54.1%) | 38/61 (62.3%) | 0.441 | Candidate-generation baseline |
| Fixed 400/80 BM25 source | 17/61 (27.9%) | 31/61 (50.8%) | 42/61 (68.9%) | 0.451 | Candidate-generation baseline |
| Fixed 400/80 BGE-small source | 13/61 (21.3%) | 30/61 (49.2%) | 37/61 (60.7%) | 0.398 | Candidate-generation baseline |
| Soft-fusion Hybrid source | 25/61 (41.0%) | 34/61 (55.7%) | 42/61 (68.9%) | 0.523 | Candidate-generation baseline |
| Fused control, budget 10 | 15/61 (24.6%) | 24/61 (39.3%) | 29/61 (47.5%) | 0.356 | <0.01 ms |
| BGE reranker, budget 10 | 14/61 (23.0%) | 28/61 (45.9%) | 36/61 (59.0%) | 0.378 | 6,997.8 ms |
| Fused control, budget 20 | 15/61 (24.6%) | 24/61 (39.3%) | 29/61 (47.5%) | 0.371 | <0.01 ms |
| BGE reranker, budget 20 | 13/61 (21.3%) | 25/61 (41.0%) | 35/61 (57.4%) | 0.385 | 14,547.2 ms |

| Slice, reranker | Budget | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---:|---:|---:|---:|---:|---:|
| Canonical | 10 | 41 | 9/41 (22.0%) | 16/41 (39.0%) | 22/41 (53.7%) | 0.347 |
| Natural student | 10 | 20 | 5/20 (25.0%) | 12/20 (60.0%) | 14/20 (70.0%) | 0.442 |
| Canonical | 20 | 41 | 10/41 (24.4%) | 15/41 (36.6%) | 21/41 (51.2%) | 0.376 |
| Natural student | 20 | 20 | 3/20 (15.0%) | 10/20 (50.0%) | 14/20 (70.0%) | 0.405 |

Outcome: budget 10 is the better reranking budget on this CPU host. The
cross-encoder improves the compressed RRF control at Hit@3/5—especially for
natural questions—but regresses Hit@1 and remains below Soft-fusion Hybrid and
Fixed BM25. It stays a diagnostic baseline rather than entering the first
offline generation architecture.

## Phase E embedding bake-off — 2026-07-16

Change tested: compared the approved pinned local embedding families on one
front-matter-free fixed 400/80 corpus, with normalized cosine retrieval and
BM25 RRF. Every model used its documented query/document prefixes; page/chunk
embeddings were fingerprinted and cached.

| Selected configuration | Overall H@1/3/5 | Overall MRR | Natural H@1/3/5 | Natural MRR | p95 | Decision |
|---|---:|---:|---:|---:|---:|---|
| BGE-small Hybrid RRF | 15/34/42 | 0.442 | 4/9/13 | 0.390 | 53.1 ms | Retain lightweight |
| BGE-M3 dense | 16/32/42 | 0.447 | 4/8/11 | 0.359 | 219.7 ms | Reject |
| BGE-M3 sparse | 17/33/42 | 0.464 | 4/9/10 | 0.354 | 719.0 ms | Reject |
| Nomic v1.5 full Hybrid | 16/37/43 | 0.460 | 3/12/14 | 0.389 | 145.2 ms | Reject |
| Nomic v1.5 512 Hybrid | 16/36/42 | 0.458 | 3/11/14 | 0.398 | 148.6 ms | Reject |
| E5-large-v2 dense | 22/35/46 | 0.524 | 5/8/12 | 0.400 | 455.8 ms | Retain quality |

Commands/results: the Phase E run IDs and exact reproduction commands are in
`reports/experiments/experiment_runs.jsonl`. Targeted embedding/cache tests
passed, and Phase E retained BGE-small plus E5-large-v2 for successive Phase F
testing. BGE-M3 and Nomic did not justify their quality/runtime tradeoffs.

## Phase F chunking and multi-granularity retrieval — 2026-07-16

Change tested: BM25-screened six approved chunk corpora, encoded only three E5
finalists, evaluated parent-page restriction, a soft page prior, neighbouring
expansion and query-relevant windows, then confirmed the winner with BGE-small.

| E5 finalist / method | Overall H@1/3/5 | MRR | Natural H@1/3/5 | Candidate recall | p95 | Decision |
|---|---:|---:|---:|---:|---:|---|
| Fixed 600/100 Hybrid | 19/36/43 | 0.490 | 5/10/13 | 61/61 | 561.9 ms | Retain base |
| Paragraph groups Hybrid | 17/33/41 | 0.445 | 4/8/12 | 61/61 | 744.1 ms | Reject |
| Fixed 400/80 dense | 22/35/46 | 0.524 | 5/8/12 | 61/61 | 511.7 ms | Retain control |
| Parent-page/child | 19/36/43 | 0.490 | 5/10/13 | 60/61 | 203.3 ms | Reject |
| Page-prior RRF | 18/42/48 | 0.518 | 5/13/14 | 61/61 | 203.6 ms | Retain E5 quality |
| Neighbour expansion | 19/33/49 | 0.490 | 5/12/16 | 61/61 | 203.2 ms | Retain context option |
| Query-relevant windows | 14/31/42 | 0.409 | 3/8/14 | 56/61 | 210.2 ms | Reject |

| BGE-small confirmation | Overall H@1/3/5 | MRR | Natural H@1/3/5 | Natural MRR | p95 | Decision |
|---|---:|---:|---:|---:|---:|---|
| Fixed 600/100 Hybrid | 20/39/45 | 0.514 | 8/11/14 | 0.525 | 29.0 ms | Retain lightweight/balanced |
| Fixed 600/100 Page-prior RRF | 24/39/48 | 0.558 | 7/11/16 | 0.511 | 30.8 ms | Reject as default |

Commands:

```powershell
temp\python-x64\python.exe scripts\run_chunking_bakeoff.py --stage bm25_screen
temp\python-x64\python.exe scripts\run_chunking_bakeoff.py --stage e5_finalists --device cpu --batch-size 8
temp\python-x64\python.exe scripts\run_chunking_bakeoff.py --stage multi_granularity --device cpu --batch-size 8
temp\python-x64\python.exe scripts\run_chunking_bakeoff.py --stage bge_confirmation --device cpu --batch-size 16
python -m pytest tests\test_chunking_bakeoff.py tests\test_candidate_compression.py -q
```

Result: 14 targeted tests passed. One E5 page-encoding batch was delayed by a
machine scheduling/power stall; cached artifacts validated and the rerun used
cache hits. Two implementation wiring errors (`summarize` import and legacy
run-record corpus counts) were caught before checkpoints, fixed, regression
tested and rerun. Historical run artifacts were not overwritten.

## Phase G deterministic query processing — 2026-07-16

Change tested: screened raw queries, conservative spelling and grammar cleanup,
static textbook synonyms, acronym expansion, and formula/symbol aliases on the
retained BGE-small fixed-600/100 Hybrid pipeline. Only the two strongest
processors advanced to original-plus-processed RRF fusion.

| Method | Changed queries | Overall H@1/3/5 | MRR | Natural H@1/3/5 | Natural MRR | p95 | Outcome |
|---|---:|---:|---:|---:|---:|---:|---|
| Raw | 0 | 20/39/45 | 0.514 | 8/11/14 | 0.525 | 44.0 ms | Control |
| Spelling | 0 | 20/39/45 | 0.514 | 8/11/14 | 0.525 | 56.4 ms | Reject: no rule fired |
| Grammar | 5 | 20/39/45 | 0.514 | 8/11/14 | 0.525 | 48.4 ms | Do not advance |
| Textbook synonyms | 19 | 21/43/50 | 0.551 | 8/13/16 | 0.563 | 46.7 ms | Retain winner |
| Acronyms | 5 | 21/39/45 | 0.522 | 8/11/14 | 0.527 | 41.7 ms | Do not advance |
| Formula/symbols | 11 | 22/38/47 | 0.530 | 8/12/15 | 0.550 | 42.1 ms | Advance to fusion |
| Original + synonyms | 19 | 20/42/48 | 0.528 | 8/13/16 | 0.544 | 146.5 ms | Reject vs standalone |
| Original + formula/symbols | 11 | 22/37/45 | 0.524 | 8/11/14 | 0.527 | 125.0 ms | Reject vs standalone |

Commands/results:

```powershell
temp\python-x64\python.exe scripts\run_query_processing.py --stage screen --device cpu --batch-size 16
temp\python-x64\python.exe scripts\run_query_processing.py --stage fusion --device cpu --batch-size 16
python -m pytest tests\test_query_processing.py tests\test_chunking_bakeoff.py tests\test_candidate_compression.py -q
```

Result: 19 targeted tests passed after adding a regression test that requires
the final selector to compare screen and fusion runs together. Standalone
synonym expansion is the deterministic Phase G winner; no LLM was called.

## Phase H specialist retrieval — 2026-07-16

Change tested: added equation-context, table-row/header, and figure-caption
page priors with static query activation; audited embedded visual assets; and
compared six gold-blind ways to form a five-chunk evidence set.

| Configuration | Overall H@1/3/5 | MRR | Natural H@1/3/5 | Target result | Outcome |
|---|---:|---:|---:|---:|---|
| Phase G synonym baseline | 21/43/50 | 0.551 | 8/13/16 | Formula 3/9/10; table 2/3/3; visual 1/5/6 | Control |
| Combined specialists | 26/44/50 | 0.601 | 9/13/16 | Formula 5/9/10; table 3/3/3; visual 3/6/6 | Retain |

| Evidence selector | Overall direct@5 | Multi-page complete@5 | Multi-chunk direct@5 | Outcome |
|---|---:|---:|---:|---|
| Base top-5 | 50/61 | 18/21 | 23/27 | Retain final |
| Coverage diversity | 46/61 | 19/21 | 20/27 | Reject at preservation gate |
| Multi-stage distinct pages | 50/61 | 18/21 | 23/27 | Reject: no quality gain, slightly larger |

Result: the combined static specialists improve early ranks without changing
Hit@5. All 350 front-matter-free pages marked as containing images yielded at
least one embedded raster (650 total), but no image-semantic claim was made.
The unmodified top five wins the final evidence-preservation gate.

## Phase I context assembly — 2026-07-16

Change tested: compared top-3/top-5, 1,200/1,800/2,400-token ceilings,
overlap and same-page merging, redundancy removal, diversity selection, and
relevance/textbook/support ordering over the retained Phase H pool.

| Assembly | Direct evidence | Exact reviewed span | Complete pages | Multi-page complete | Avg tokens | Outcome |
|---|---:|---:|---:|---:|---:|---|
| Top-3 relevance | 44/61 | 44/61 | 50/61 | 17/21 | 1,813 | Reject |
| Top-5 relevance | 50/61 | 50/61 | 55/61 | 18/21 | 3,000 | Control |
| 2,400-token ceiling | 49/61 | 49/61 | 53/61 | 18/21 | 2,400 | Reject: loses one span |
| Overlap merge | 50/61 | 50/61 | 55/61 | 18/21 | 2,965 | Retain |

Result: overlap merging is the smallest tested context that preserves every
accepted span available in the top-five retrieval pool. Phase J is blocked
because the retrieval benchmark does not score generated-answer correctness,
faithfulness, citations, or abstention.

## Retrieval Baseline v1 freeze — 2026-07-16

Change tested: extracted the verified Phase H/I winner into a strict immutable
YAML configuration, added the structured public retrieval API, provenance
manifest, golden fixture, checksum protection, and canonical management CLI.

| Validation | Result |
|---|---:|
| Focused existing ranking/query/context regressions | 18 passed |
| New freeze/config/API/fixture/manifest regressions | 15 passed |
| Complete repository regression suite | 126 passed |
| Clean benchmark Hit@1 | 26/61 (42.6%) |
| Clean benchmark Hit@3 | 44/61 (72.1%) |
| Clean benchmark Hit@5 | 50/61 (82.0%) |
| Clean benchmark MRR | 0.601127 (exact original match) |
| Canonical Hit@5 | 34/41 (82.9%) |
| Natural-student Hit@5 | 16/20 (80.0%) |
| Golden fixture | 8/8 cases, identical top-five order across 2 runs |
| Original / fresh warm p95 | 71.169 / 84.943 ms |
| Original / fresh peak RSS | 688.223 / 677.227 MB |

Commands/results:

```powershell
python -m pytest tests/test_query_processing.py tests/test_specialist_retrieval.py tests/test_context_assembly.py tests/test_final_pipeline.py -q
temp\python-x64\python.exe -m pytest tests/test_retrieval_baseline_v1.py -q
temp\python-x64\python.exe -m pytest -q
temp\python-x64\python.exe scripts\manage_retrieval_baseline_v1.py validate
```

Result: effectiveness counts, full-rank MRR, every golden expectation, and
repeat ordering reproduced exactly. Timing varied as expected; all eight
embedding caches were valid hits and no historical experiment file changed.

## Generation Phase A gold-context smoke — 2026-07-17

Change tested: added the fixed 8/32 generation split, accepted-PDF-page gold
contexts, native ARM64 Qwen3-8B llama.cpp interface, claim-level JSON answers,
citation checks, deterministic rubric scoring, atomic per-question resume
state, and manual answer/citation review. No prompt comparison or other model
download was run.

| Question | Manual required coverage | Citation review | Strict pass | Latency |
|---|---:|---|---:|---:|
| GEN-BIO-002 | 1.00 | Supported | 1 | 20.73 s |
| GEN-BIO-005 | 1.00 | Partially supported | 0 | 40.71 s |
| GEN-BIO-012 | 0.80 | Partially supported | 0 | 44.25 s |
| GEN-BIO-014 | 0.60 | Supported | 0 | 32.81 s |
| GEN-PSC-002 | 0.50 | Partially supported | 0 | 35.24 s |
| GEN-PSC-006 | 1.00 | Supported | 1 | 26.81 s |
| GEN-PSC-009 | 0.25 | Supported | 0 | 32.91 s |
| GEN-PSC-015 | 0.40 | Supported | 0 | 43.05 s |

| Aggregate | Result |
|---|---:|
| Completed generations | 8/8 |
| Valid JSON and evidence IDs | 8/8 |
| Strict lexical citation-support checks | 3/8 |
| Fully supported after manual citation review | 5/8 |
| Strict manual answer-and-grounding passes | 2/8 |
| Mean strict required-point coverage | 0.6937 |
| Mean / maximum latency | 34.56 / 44.25 s |
| Unsupported claims found manually | 0 |

Commands/results:

```powershell
temp\python-x64\python.exe scripts\run_generation_phase_a.py --prepare-only
temp\python-x64\python.exe scripts\run_generation_phase_a.py --llama-server <arm64-llama-server.exe> --model <Qwen3-8B-Q4_K_M.gguf>
temp\python-x64\python.exe scripts\run_generation_phase_a.py --reevaluate-only
temp\python-x64\python.exe -m pytest -q tests\test_generation_phase_a.py tests\test_generation_benchmark_v1.py
temp\python-x64\python.exe -m pytest -q
```

Result: 20 focused tests and all 146 repository tests passed. Generation
Benchmark v1 remained at SHA-256 `f756e633...6680`; Retrieval Benchmark v1
remained at `d333768b...c046`. The infrastructure gate passed, but only 2/8
answers passed strict manual completeness plus grounding review, so prompt
comparisons and other model downloads remain gated.

## Local generation matrix and hardware backends — 2026-07-18

Change tested: completed the approved prompt, context, Qwen 8B/14B, output-cap,
thinking, specialist, holdout, final-40 and abstention screens; then compared
native CPU, Vulkan, DirectML and QNN under controlled local probes. Frozen
retrieval and generation inputs were not modified.

| Evaluation | Model / mode | Questions | Coverage | Citation | Unsupported | Formula | p95 latency | Outcome |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Holdout | Qwen3-8B gold | 24 | 0.5028 | 0.9583 | 0.0417 | 0.0000 | 97.33 s | Lightweight finalist |
| Holdout | Qwen3-8B retrieved | 24 | 0.4903 | 0.9583 | 0.0000 | 0.0000 | 351.70 s | Balanced winner |
| Holdout | Qwen3-14B gold | 24 | 0.5215 | 1.0000 | 0.0000 | 0.0000 | 186.91 s | Quality finalist |
| Holdout | Qwen3-14B retrieved | 24 | 0.5632 | 0.9583 | 0.0417 | 0.2000 | 469.42 s | Best automatic coverage |
| Final | Qwen3-8B gold | 40 | 0.4654 | 0.9750 | 0.0250 | 0.0000 | 85.74 s | Completed |
| Final | Qwen3-8B retrieved | 40 | 0.4704 | 0.9500 | 0.0250 | 0.1000 | 229.40 s | Provisional pipeline |
| Diagnostic | Prompt-only abstention | 5 | — | — | — | — | — | 4/5 correct |
| Diagnostic | Model + evidence check | 5 | — | — | — | — | — | 5/5 correct |

| Backend control | Valid output | Measured result | Decision |
|---|---:|---|---|
| Native ARM64 llama.cpp CPU | 1 | Qwen deterministic output valid | Reliable fallback / selected runtime |
| x64 llama.cpp Vulkan | 0 | Repeated invalid text | Reject |
| QNN HTP QDQ micrograph | 1 | 0.0648 ms p50 vs CPU 0.0569 ms | Provider works, no acceleration |
| DirectML QDQ micrograph | 0 | 0.3420 ms p50 vs CPU 0.0569 ms | Reject |
| ORT GenAI Gemma CPU | 0 | 0.308 tokens/s; truncated/weak answer | Reject |
| ORT GenAI Gemma DirectML | 0 | 4.404 tokens/s; corrupted token stream | Reject despite speed |

Commands/results:

```powershell
temp\python-x64\python.exe scripts\run_generation_experiment_matrix.py --llama-server <arm64-server> --qwen8 <8b-gguf> --qwen14 <14b-gguf>
temp\python-x64\python.exe -m pytest -q tests\test_generation_experiments.py tests\test_generation_phase_a.py tests\test_generation_benchmark_v1.py
temp\python-x64\python.exe -m pytest -q
temp\python-x64\python.exe scripts\manage_retrieval_baseline_v1.py validate
```

Result: the matrix and all 85 final/diagnostic generations completed. The CPU
probe initially exposed a contradictory CPU-fallback option; the probe was
fixed, rerun, and documented. Focused tests: 27 passed. Full suite: 153 passed.
Frozen retrieval validation reproduced Hit@1/3/5 = 26/44/50 and MRR 0.601127.
Generation benchmark, retrieval benchmark and frozen retrieval configuration
hashes remained `f756e633...6680`, `d333768b...c046` and `736fb932...baa6`.
The winner is useful as a reproducible baseline but misses the coverage and
formula targets, so it remains provisional pending blinded review.
