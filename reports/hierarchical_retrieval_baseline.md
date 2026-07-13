# Hierarchical Chunking and Retrieval v1

Final targets are paragraph groups; chapters and sections supply parent retrieval signals. Gold evidence is never used in hierarchy construction or ranking.

## Headline results

| Approach | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR | Avg ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| strict cascade | BM25 | 61 | 13.1% | 27.9% | 32.8% | 0.208 | 7.25 | 13.74 |
| strict cascade | BGE-small dense | 61 | 29.5% | 55.7% | 63.9% | 0.447 | 38.22 | 45.71 |
| strict cascade | Hybrid RRF | 61 | 36.1% | 45.9% | 59.0% | 0.446 | 46.37 | 58.42 |
| soft fusion | BM25 | 61 | 29.5% | 50.8% | 62.3% | 0.423 | 10.56 | 16.33 |
| soft fusion | BGE-small dense | 61 | 27.9% | 57.4% | 65.6% | 0.451 | 41.48 | 49.36 |
| soft fusion | Hybrid RRF | 61 | 41.0% | 55.7% | 68.9% | 0.523 | 49.74 | 61.33 |

## Stage-level recall

| Approach | Retriever | Chapter recall@K | Section recall@K | Independent paragraph Hit@5 | Chapter survival | Section survival |
|---|---|---:|---:|---:|---:|---:|
| strict cascade | BM25 | 45.9% | 80.3% | 60.7% | 45.9% | 41.0% |
| strict cascade | BGE-small dense | 95.1% | 85.2% | 65.6% | 95.1% | 83.6% |
| strict cascade | Hybrid RRF | 83.6% | 83.6% | 65.6% | 83.6% | 73.8% |
| soft fusion | BM25 | 45.9% | 80.3% | 60.7% | n/a | n/a |
| soft fusion | BGE-small dense | 95.1% | 85.2% | 65.6% | n/a | n/a |
| soft fusion | Hybrid RRF | 83.6% | 83.6% | 65.6% | n/a | n/a |

## Baseline comparison

| Baseline | Retriever | Hit@1 | Hit@5 | MRR |
|---|---|---:|---:|---:|
| Page | BM25 | 31.1% | 62.3% | 0.448 |
| Page | BGE-small dense | 37.7% | 70.5% | 0.541 |
| Page | Hybrid RRF | 37.7% | 70.5% | 0.524 |
| fixed chunks | BM25 | 27.9% | 68.9% | 0.451 |
| fixed chunks | BGE-small dense | 21.3% | 60.7% | 0.398 |
| fixed chunks | Hybrid RRF | 24.6% | 68.9% | 0.444 |
| structured chunks | BM25 | 18.0% | 60.7% | 0.364 |
| structured chunks | BGE-small dense | 21.3% | 60.7% | 0.406 |
| structured chunks | Hybrid RRF | 21.3% | 67.2% | 0.416 |

## Canonical versus natural-student queries

| Slice | Approach | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---:|---:|---:|---:|---:|
| canonical | strict cascade | BM25 | 41 | 14.6% | 34.1% | 39.0% | 0.241 |
| canonical | strict cascade | BGE-small dense | 41 | 36.6% | 61.0% | 68.3% | 0.502 |
| canonical | strict cascade | Hybrid RRF | 41 | 41.5% | 48.8% | 61.0% | 0.486 |
| natural_student | strict cascade | BM25 | 20 | 10.0% | 15.0% | 20.0% | 0.140 |
| natural_student | strict cascade | BGE-small dense | 20 | 15.0% | 45.0% | 55.0% | 0.336 |
| natural_student | strict cascade | Hybrid RRF | 20 | 25.0% | 40.0% | 55.0% | 0.365 |
| canonical | soft fusion | BM25 | 41 | 31.7% | 53.7% | 65.9% | 0.447 |
| canonical | soft fusion | BGE-small dense | 41 | 34.1% | 61.0% | 70.7% | 0.497 |
| canonical | soft fusion | Hybrid RRF | 41 | 43.9% | 58.5% | 73.2% | 0.552 |
| natural_student | soft fusion | BM25 | 20 | 25.0% | 45.0% | 55.0% | 0.375 |
| natural_student | soft fusion | BGE-small dense | 20 | 15.0% | 50.0% | 55.0% | 0.357 |
| natural_student | soft fusion | Hybrid RRF | 20 | 35.0% | 50.0% | 60.0% | 0.463 |

Natural-student results are also broken down by `query_style` in `hierarchical_retrieval_metrics.json`.

## Dependency and evidence-span slices

| Slice | Approach | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---:|---:|---:|---:|---:|
| formula dependent | strict cascade | BM25 | 16 | 0.0% | 12.5% | 18.8% | 0.068 |
| formula dependent | strict cascade | BGE-small dense | 16 | 12.5% | 25.0% | 37.5% | 0.244 |
| formula dependent | strict cascade | Hybrid RRF | 16 | 12.5% | 12.5% | 12.5% | 0.157 |
| formula dependent | soft fusion | BM25 | 16 | 12.5% | 31.2% | 43.8% | 0.244 |
| formula dependent | soft fusion | BGE-small dense | 16 | 12.5% | 37.5% | 43.8% | 0.280 |
| formula dependent | soft fusion | Hybrid RRF | 16 | 18.8% | 37.5% | 37.5% | 0.323 |
| visual dependent | strict cascade | BM25 | 6 | 0.0% | 33.3% | 33.3% | 0.139 |
| visual dependent | strict cascade | BGE-small dense | 6 | 33.3% | 66.7% | 66.7% | 0.489 |
| visual dependent | strict cascade | Hybrid RRF | 6 | 16.7% | 50.0% | 83.3% | 0.353 |
| visual dependent | soft fusion | BM25 | 6 | 16.7% | 83.3% | 100.0% | 0.458 |
| visual dependent | soft fusion | BGE-small dense | 6 | 33.3% | 66.7% | 66.7% | 0.489 |
| visual dependent | soft fusion | Hybrid RRF | 6 | 33.3% | 83.3% | 100.0% | 0.542 |
| table dependent | strict cascade | BM25 | 3 | 0.0% | 0.0% | 0.0% | 0.000 |
| table dependent | strict cascade | BGE-small dense | 3 | 33.3% | 66.7% | 100.0% | 0.583 |
| table dependent | strict cascade | Hybrid RRF | 3 | 100.0% | 100.0% | 100.0% | 1.000 |
| table dependent | soft fusion | BM25 | 3 | 100.0% | 100.0% | 100.0% | 1.000 |
| table dependent | soft fusion | BGE-small dense | 3 | 33.3% | 66.7% | 100.0% | 0.583 |
| table dependent | soft fusion | Hybrid RRF | 3 | 100.0% | 100.0% | 100.0% | 1.000 |
| multi page | strict cascade | BM25 | 21 | 4.8% | 19.0% | 19.0% | 0.111 |
| multi page | strict cascade | BGE-small dense | 21 | 28.6% | 61.9% | 66.7% | 0.456 |
| multi page | strict cascade | Hybrid RRF | 21 | 28.6% | 42.9% | 57.1% | 0.386 |
| multi page | soft fusion | BM25 | 21 | 28.6% | 57.1% | 61.9% | 0.427 |
| multi page | soft fusion | BGE-small dense | 21 | 28.6% | 66.7% | 71.4% | 0.485 |
| multi page | soft fusion | Hybrid RRF | 21 | 38.1% | 61.9% | 71.4% | 0.523 |
| multi chunk | strict cascade | BM25 | 27 | 11.1% | 29.6% | 29.6% | 0.204 |
| multi chunk | strict cascade | BGE-small dense | 27 | 33.3% | 66.7% | 74.1% | 0.506 |
| multi chunk | strict cascade | Hybrid RRF | 27 | 37.0% | 55.6% | 66.7% | 0.479 |
| multi chunk | soft fusion | BM25 | 27 | 29.6% | 59.3% | 63.0% | 0.449 |
| multi chunk | soft fusion | BGE-small dense | 27 | 33.3% | 66.7% | 74.1% | 0.520 |
| multi chunk | soft fusion | Hybrid RRF | 27 | 44.4% | 66.7% | 77.8% | 0.576 |

Book, difficulty, and heading-confidence metric blocks are recorded in `hierarchical_retrieval_metrics.json`.

## Top-five failures

| Question | Approach | Retriever | Gold rank | Category |
|---|---|---|---:|---|
| BIO-003 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-004 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-004 | strict cascade | BGE-small dense | > corpus | correct section missed during cascade |
| BIO-004 | soft fusion | BGE-small dense | 16 | paragraph ranked poorly despite correct parents |
| BIO-005 | soft fusion | BM25 | 7 | evidence spread across multiple sections or pages |
| BIO-008 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-009 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-009 | soft fusion | BM25 | 11 | evidence spread across multiple sections or pages |
| BIO-013 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-015 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-016 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-017 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-017 | soft fusion | BM25 | 79 | evidence spread across multiple sections or pages |
| BIO-017 | strict cascade | BGE-small dense | > corpus | correct section missed during cascade |
| BIO-017 | soft fusion | BGE-small dense | 45 | evidence spread across multiple sections or pages |
| BIO-017 | strict cascade | Hybrid RRF | > corpus | correct section missed during cascade |
| BIO-017 | soft fusion | Hybrid RRF | 47 | evidence spread across multiple sections or pages |
| BIO-018 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-018 | strict cascade | Hybrid RRF | > corpus | correct chapter missed during cascade |
| PSC-002 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-002 | soft fusion | BM25 | 32 | formula or symbol extraction |
| PSC-002 | strict cascade | BGE-small dense | > corpus | correct chapter missed during cascade |
| PSC-002 | soft fusion | BGE-small dense | 129 | formula or symbol extraction |
| PSC-002 | strict cascade | Hybrid RRF | > corpus | correct chapter missed during cascade |
| PSC-002 | soft fusion | Hybrid RRF | 54 | formula or symbol extraction |
| PSC-003 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-003 | soft fusion | BM25 | 50 | formula or symbol extraction |
| PSC-003 | strict cascade | Hybrid RRF | > corpus | correct chapter missed during cascade |
| PSC-003 | soft fusion | Hybrid RRF | 6 | formula or symbol extraction |
| PSC-004 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-004 | soft fusion | BM25 | 8 | paragraph ranked poorly despite correct parents |
| PSC-004 | strict cascade | BGE-small dense | 6 | paragraph ranked poorly despite correct parents |
| PSC-004 | strict cascade | Hybrid RRF | > corpus | correct chapter missed during cascade |
| PSC-005 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-005 | soft fusion | BM25 | 60 | formula or symbol extraction |
| PSC-005 | strict cascade | BGE-small dense | 9 | formula or symbol extraction |
| PSC-005 | soft fusion | BGE-small dense | 8 | formula or symbol extraction |
| PSC-005 | strict cascade | Hybrid RRF | 15 | formula or symbol extraction |
| PSC-005 | soft fusion | Hybrid RRF | 27 | formula or symbol extraction |
| PSC-006 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-006 | soft fusion | BM25 | 23 | formula or symbol extraction |
| PSC-006 | strict cascade | BGE-small dense | > corpus | correct section missed during cascade |
| PSC-006 | soft fusion | BGE-small dense | 21 | formula or symbol extraction |
| PSC-006 | strict cascade | Hybrid RRF | > corpus | correct section missed during cascade |
| PSC-006 | soft fusion | Hybrid RRF | 23 | formula or symbol extraction |
| PSC-007 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-007 | strict cascade | Hybrid RRF | > corpus | correct chapter missed during cascade |
| PSC-009 | strict cascade | BGE-small dense | 8 | visual dependency |
| PSC-009 | soft fusion | BGE-small dense | 8 | visual dependency |
| PSC-010 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-010 | strict cascade | BGE-small dense | 7 | visual dependency |
| PSC-010 | soft fusion | BGE-small dense | 7 | visual dependency |
| PSC-011 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-013 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-013 | soft fusion | BM25 | 21 | formula or symbol extraction |
| PSC-013 | strict cascade | BGE-small dense | 26 | formula or symbol extraction |
| PSC-013 | soft fusion | BGE-small dense | 40 | formula or symbol extraction |
| PSC-013 | strict cascade | Hybrid RRF | 20 | formula or symbol extraction |
| PSC-013 | soft fusion | Hybrid RRF | 27 | formula or symbol extraction |
| PSC-014 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-014 | strict cascade | Hybrid RRF | > corpus | correct chapter missed during cascade |
| PSC-015 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-015 | strict cascade | Hybrid RRF | > corpus | correct chapter missed during cascade |
| PSC-016 | strict cascade | BM25 | 8 | formula or symbol extraction |
| PSC-016 | soft fusion | BM25 | 8 | formula or symbol extraction |
| PSC-016 | strict cascade | BGE-small dense | 7 | formula or symbol extraction |
| PSC-016 | soft fusion | BGE-small dense | 7 | formula or symbol extraction |
| PSC-016 | strict cascade | Hybrid RRF | 9 | formula or symbol extraction |
| PSC-016 | soft fusion | Hybrid RRF | 9 | formula or symbol extraction |
| BIO-022 | strict cascade | BM25 | 11 | paragraph ranked poorly despite correct parents |
| BIO-022 | soft fusion | BM25 | 47 | paragraph ranked poorly despite correct parents |
| BIO-022 | strict cascade | BGE-small dense | 11 | paragraph ranked poorly despite correct parents |
| BIO-022 | soft fusion | BGE-small dense | 17 | paragraph ranked poorly despite correct parents |
| BIO-022 | strict cascade | Hybrid RRF | 8 | paragraph ranked poorly despite correct parents |
| BIO-022 | soft fusion | Hybrid RRF | 18 | paragraph ranked poorly despite correct parents |
| PSC-021 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-021 | soft fusion | BM25 | 101 | paragraph ranked poorly despite correct parents |
| PSC-021 | strict cascade | Hybrid RRF | 14 | paragraph ranked poorly despite correct parents |
| PSC-021 | soft fusion | Hybrid RRF | 19 | paragraph ranked poorly despite correct parents |
| PSC-023 | strict cascade | BM25 | 16 | paragraph ranked poorly despite correct parents |
| PSC-023 | soft fusion | BM25 | 27 | paragraph ranked poorly despite correct parents |
| PSC-023 | strict cascade | BGE-small dense | 22 | paragraph ranked poorly despite correct parents |
| PSC-023 | soft fusion | BGE-small dense | 24 | paragraph ranked poorly despite correct parents |
| PSC-023 | strict cascade | Hybrid RRF | > corpus | correct section missed during cascade |
| PSC-023 | soft fusion | Hybrid RRF | 21 | paragraph ranked poorly despite correct parents |
| PSC-024 | strict cascade | BM25 | > corpus | correct section missed during cascade |
| PSC-024 | soft fusion | BM25 | 295 | paragraph ranked poorly despite correct parents |
| PSC-024 | strict cascade | BGE-small dense | > corpus | correct chapter missed during cascade |
| PSC-024 | soft fusion | BGE-small dense | 18 | paragraph ranked poorly despite correct parents |
| PSC-024 | strict cascade | Hybrid RRF | > corpus | correct section missed during cascade |
| PSC-024 | soft fusion | Hybrid RRF | 60 | paragraph ranked poorly despite correct parents |
| BIO-023 | strict cascade | BGE-small dense | 13 | paragraph ranked poorly despite correct parents |
| BIO-023 | soft fusion | BGE-small dense | 19 | paragraph ranked poorly despite correct parents |
| BIO-023 | strict cascade | Hybrid RRF | 7 | paragraph ranked poorly despite correct parents |
| BIO-023 | soft fusion | Hybrid RRF | 7 | paragraph ranked poorly despite correct parents |
| BIO-024 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-026 | strict cascade | BM25 | 6 | evidence spread across multiple sections or pages |
| BIO-026 | soft fusion | BM25 | 6 | evidence spread across multiple sections or pages |
| BIO-027 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-027 | soft fusion | BM25 | 10 | evidence spread across multiple sections or pages |
| BIO-028 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-028 | soft fusion | BM25 | 16 | evidence spread across multiple sections or pages |
| BIO-028 | strict cascade | BGE-small dense | 7 | evidence spread across multiple sections or pages |
| BIO-028 | soft fusion | BGE-small dense | 6 | evidence spread across multiple sections or pages |
| BIO-028 | soft fusion | Hybrid RRF | 6 | evidence spread across multiple sections or pages |
| BIO-029 | strict cascade | BM25 | > corpus | correct section missed during cascade |
| BIO-029 | soft fusion | BM25 | 15 | paragraph ranked poorly despite correct parents |
| BIO-031 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-032 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| BIO-032 | soft fusion | BM25 | 318 | evidence spread across multiple sections or pages |
| BIO-032 | strict cascade | BGE-small dense | > corpus | correct section missed during cascade |
| BIO-032 | soft fusion | BGE-small dense | 19 | evidence spread across multiple sections or pages |
| BIO-032 | strict cascade | Hybrid RRF | > corpus | correct chapter missed during cascade |
| BIO-032 | soft fusion | Hybrid RRF | 51 | evidence spread across multiple sections or pages |
| PSC-025 | strict cascade | BM25 | > corpus | correct section missed during cascade |
| PSC-025 | soft fusion | BM25 | 42 | formula or symbol extraction |
| PSC-025 | strict cascade | BGE-small dense | > corpus | correct section missed during cascade |
| PSC-025 | soft fusion | BGE-small dense | 15 | formula or symbol extraction |
| PSC-025 | strict cascade | Hybrid RRF | 10 | formula or symbol extraction |
| PSC-025 | soft fusion | Hybrid RRF | 19 | formula or symbol extraction |
| PSC-026 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-026 | soft fusion | BM25 | 7 | paragraph ranked poorly despite correct parents |
| PSC-026 | strict cascade | BGE-small dense | > corpus | correct section missed during cascade |
| PSC-026 | soft fusion | BGE-small dense | 43 | paragraph ranked poorly despite correct parents |
| PSC-026 | strict cascade | Hybrid RRF | > corpus | correct section missed during cascade |
| PSC-026 | soft fusion | Hybrid RRF | 17 | paragraph ranked poorly despite correct parents |
| PSC-027 | strict cascade | BM25 | 22 | formula or symbol extraction |
| PSC-027 | soft fusion | BM25 | 32 | formula or symbol extraction |
| PSC-027 | strict cascade | BGE-small dense | 10 | formula or symbol extraction |
| PSC-027 | soft fusion | BGE-small dense | 11 | formula or symbol extraction |
| PSC-027 | strict cascade | Hybrid RRF | 18 | formula or symbol extraction |
| PSC-027 | soft fusion | Hybrid RRF | 19 | formula or symbol extraction |
| PSC-028 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-028 | soft fusion | BM25 | 388 | formula or symbol extraction |
| PSC-028 | strict cascade | BGE-small dense | > corpus | correct section missed during cascade |
| PSC-028 | soft fusion | BGE-small dense | 17 | formula or symbol extraction |
| PSC-028 | strict cascade | Hybrid RRF | > corpus | correct section missed during cascade |
| PSC-028 | soft fusion | Hybrid RRF | 58 | formula or symbol extraction |
| PSC-029 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-030 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-030 | strict cascade | Hybrid RRF | > corpus | correct chapter missed during cascade |
| PSC-031 | strict cascade | BGE-small dense | 16 | formula or symbol extraction |
| PSC-031 | soft fusion | BGE-small dense | 21 | formula or symbol extraction |
| PSC-031 | strict cascade | Hybrid RRF | 8 | formula or symbol extraction |
| PSC-031 | soft fusion | Hybrid RRF | 8 | formula or symbol extraction |
| PSC-032 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-032 | strict cascade | BGE-small dense | > corpus | correct chapter missed during cascade |
| PSC-032 | strict cascade | Hybrid RRF | > corpus | correct chapter missed during cascade |
| PSC-033 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-034 | strict cascade | BM25 | > corpus | correct chapter missed during cascade |
| PSC-034 | soft fusion | BGE-small dense | 6 | evidence spread across multiple sections or pages |

## Decision

Best hierarchical Hit@5 is 68.9% from **soft fusion / Hybrid RRF**. It does not exceed the current best chunk baseline of 68.9%.
Best hierarchical MRR is 0.523 from **soft fusion / Hybrid RRF**. It does not preserve the current best page MRR of 0.541.
Rows requiring manual gold review: none.
Section detection is reliable for explicit numbered headings, but the conservative detector intentionally leaves uncertain unnumbered headings as content. Two answer spans require manual chunk-mapping review.
Soft fusion performs better than strict cascade overall. Strict BM25 is especially weak because chapter filtering eliminates accepted evidence early.
Formula-heavy, visual, and evidence-spanning questions remain the dominant weak categories; their exact strategy/retriever results appear above.
Against page Hybrid, soft-fusion Hybrid slice changes are: formula dependent -12.5% Hit@5; visual dependent +16.7% Hit@5; table dependent +0.0% Hit@5; multi page -14.3% Hit@5; multi chunk -11.1% Hit@5. Different scored counts in a slice reflect explicitly excluded manual gold mappings.
The hierarchy should not become the default retrieval architecture because it does not improve the strongest baseline and introduces systematic parent-stage failures.
The recommended next experiment is neighbour expansion over soft-fusion Hybrid paragraph retrieval, compared with the fixed 400/80 BM25 baseline.

## Reproducibility

- Chapters selected: 3; sections selected: 8.
- Soft weights: section 0.5, chapter 0.25; rank constant 60.
- BM25, BGE-small, and BM25/dense RRF settings match prior baselines. Embeddings are cached independently by book and hierarchy level.
