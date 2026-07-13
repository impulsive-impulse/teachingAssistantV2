# Hierarchical Chunking and Retrieval v1

Final targets are paragraph groups; chapters and sections supply parent retrieval signals. Gold evidence is never used in hierarchy construction or ranking.

## Headline results

| Approach | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR | Avg ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| strict cascade | BM25 | 41 | 14.6% | 34.1% | 39.0% | 0.241 | 4.12 | 7.41 |
| strict cascade | BGE-small dense | 41 | 36.6% | 61.0% | 68.3% | 0.502 | 24.52 | 31.32 |
| strict cascade | Hybrid RRF | 41 | 41.5% | 48.8% | 61.0% | 0.486 | 29.16 | 36.73 |
| soft fusion | BM25 | 41 | 31.7% | 53.7% | 65.9% | 0.447 | 5.96 | 9.52 |
| soft fusion | BGE-small dense | 41 | 34.1% | 61.0% | 70.7% | 0.497 | 26.30 | 33.27 |
| soft fusion | Hybrid RRF | 41 | 43.9% | 58.5% | 73.2% | 0.552 | 30.95 | 38.64 |

## Stage-level recall

| Approach | Retriever | Chapter recall@K | Section recall@K | Independent paragraph Hit@5 | Chapter survival | Section survival |
|---|---|---:|---:|---:|---:|---:|
| strict cascade | BM25 | 48.8% | 80.5% | 65.9% | 48.8% | 46.3% |
| strict cascade | BGE-small dense | 95.1% | 87.8% | 68.3% | 95.1% | 87.8% |
| strict cascade | Hybrid RRF | 82.9% | 85.4% | 68.3% | 82.9% | 73.2% |
| soft fusion | BM25 | 48.8% | 80.5% | 65.9% | n/a | n/a |
| soft fusion | BGE-small dense | 95.1% | 87.8% | 68.3% | n/a | n/a |
| soft fusion | Hybrid RRF | 82.9% | 85.4% | 68.3% | n/a | n/a |

## Baseline comparison

| Baseline | Retriever | Hit@1 | Hit@5 | MRR |
|---|---|---:|---:|---:|
| Page | BM25 | 36.6% | 68.3% | 0.491 |
| Page | BGE-small dense | 43.9% | 73.2% | 0.589 |
| Page | Hybrid RRF | 46.3% | 73.2% | 0.585 |
| fixed chunks | BM25 | 34.1% | 75.6% | 0.507 |
| fixed chunks | BGE-small dense | 24.4% | 63.4% | 0.425 |
| fixed chunks | Hybrid RRF | 26.8% | 70.7% | 0.471 |
| structured chunks | BM25 | 19.5% | 68.3% | 0.392 |
| structured chunks | BGE-small dense | 24.4% | 65.9% | 0.447 |
| structured chunks | Hybrid RRF | 26.8% | 73.2% | 0.467 |

## Dependency and evidence-span slices

| Slice | Approach | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---:|---:|---:|---:|---:|
| formula dependent | strict cascade | BM25 | 11 | 0.0% | 18.2% | 18.2% | 0.072 |
| formula dependent | strict cascade | BGE-small dense | 11 | 18.2% | 36.4% | 54.5% | 0.340 |
| formula dependent | strict cascade | Hybrid RRF | 11 | 18.2% | 18.2% | 18.2% | 0.203 |
| formula dependent | soft fusion | BM25 | 11 | 18.2% | 36.4% | 45.5% | 0.302 |
| formula dependent | soft fusion | BGE-small dense | 11 | 18.2% | 45.5% | 54.5% | 0.353 |
| formula dependent | soft fusion | Hybrid RRF | 11 | 27.3% | 45.5% | 45.5% | 0.401 |
| visual dependent | strict cascade | BM25 | 4 | 0.0% | 50.0% | 50.0% | 0.208 |
| visual dependent | strict cascade | BGE-small dense | 4 | 25.0% | 50.0% | 50.0% | 0.400 |
| visual dependent | strict cascade | Hybrid RRF | 4 | 25.0% | 50.0% | 100.0% | 0.446 |
| visual dependent | soft fusion | BM25 | 4 | 0.0% | 75.0% | 100.0% | 0.354 |
| visual dependent | soft fusion | BGE-small dense | 4 | 25.0% | 50.0% | 50.0% | 0.400 |
| visual dependent | soft fusion | Hybrid RRF | 4 | 25.0% | 75.0% | 100.0% | 0.479 |
| table dependent | strict cascade | BM25 | 2 | 0.0% | 0.0% | 0.0% | 0.000 |
| table dependent | strict cascade | BGE-small dense | 2 | 50.0% | 100.0% | 100.0% | 0.750 |
| table dependent | strict cascade | Hybrid RRF | 2 | 100.0% | 100.0% | 100.0% | 1.000 |
| table dependent | soft fusion | BM25 | 2 | 100.0% | 100.0% | 100.0% | 1.000 |
| table dependent | soft fusion | BGE-small dense | 2 | 50.0% | 100.0% | 100.0% | 0.750 |
| table dependent | soft fusion | Hybrid RRF | 2 | 100.0% | 100.0% | 100.0% | 1.000 |
| multi page | strict cascade | BM25 | 12 | 0.0% | 25.0% | 25.0% | 0.108 |
| multi page | strict cascade | BGE-small dense | 12 | 41.7% | 75.0% | 75.0% | 0.563 |
| multi page | strict cascade | Hybrid RRF | 12 | 33.3% | 50.0% | 58.3% | 0.438 |
| multi page | soft fusion | BM25 | 12 | 25.0% | 58.3% | 66.7% | 0.426 |
| multi page | soft fusion | BGE-small dense | 12 | 41.7% | 75.0% | 75.0% | 0.580 |
| multi page | soft fusion | Hybrid RRF | 12 | 41.7% | 66.7% | 75.0% | 0.559 |
| multi chunk | strict cascade | BM25 | 15 | 6.7% | 40.0% | 40.0% | 0.219 |
| multi chunk | strict cascade | BGE-small dense | 15 | 46.7% | 80.0% | 80.0% | 0.606 |
| multi chunk | strict cascade | Hybrid RRF | 15 | 46.7% | 60.0% | 66.7% | 0.551 |
| multi chunk | soft fusion | BM25 | 15 | 26.7% | 60.0% | 66.7% | 0.450 |
| multi chunk | soft fusion | BGE-small dense | 15 | 46.7% | 73.3% | 80.0% | 0.610 |
| multi chunk | soft fusion | Hybrid RRF | 15 | 46.7% | 66.7% | 80.0% | 0.597 |

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

## Decision

Best hierarchical Hit@5 is 73.2% from **soft fusion / Hybrid RRF**. It does not exceed the current best chunk baseline of 75.6%.
Best hierarchical MRR is 0.552 from **soft fusion / Hybrid RRF**. It does not preserve the current best page MRR of 0.589.
Rows requiring manual gold review: none.
Section detection is reliable for explicit numbered headings, but the conservative detector intentionally leaves uncertain unnumbered headings as content. Two answer spans require manual chunk-mapping review.
Soft fusion performs better than strict cascade overall. Strict BM25 is especially weak because chapter filtering eliminates accepted evidence early.
Formula-heavy, visual, and evidence-spanning questions remain the dominant weak categories; their exact strategy/retriever results appear above.
Against page Hybrid, soft-fusion Hybrid slice changes are: formula dependent -18.2% Hit@5; visual dependent +25.0% Hit@5; table dependent +0.0% Hit@5; multi page -8.3% Hit@5; multi chunk -6.7% Hit@5. Different scored counts in a slice reflect explicitly excluded manual gold mappings.
The hierarchy should not become the default retrieval architecture because it does not improve the strongest baseline and introduces systematic parent-stage failures.
The recommended next experiment is neighbour expansion over soft-fusion Hybrid paragraph retrieval, compared with the fixed 400/80 BM25 baseline.

## Reproducibility

- Chapters selected: 3; sections selected: 8.
- Soft weights: section 0.5, chapter 0.25; rank constant 60.
- BM25, BGE-small, and BM25/dense RRF settings match prior baselines. Embeddings are cached independently by book and hierarchy level.
