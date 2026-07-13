# Chunk-Level Retrieval Baseline v1

Fixed-size and structure-aware chunks are compared with the unchanged page baseline. Rankings are book-scoped and never use gold evidence.

## Headline results

| Unit / strategy | Retriever | Scored N | Hit@1 | Hit@3 | Hit@5 | MRR | Avg ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Page | BM25 | 41 | 36.6% | 56.1% | 68.3% | 0.491 | 3.42 | 6.75 |
| Page | BGE-small dense | 41 | 43.9% | 68.3% | 73.2% | 0.589 | 40.75 | 61.09 |
| Page | Hybrid RRF | 41 | 46.3% | 63.4% | 73.2% | 0.585 | 44.60 | 65.73 |
| Fixed chunks | BM25 | 41 | 34.1% | 58.5% | 75.6% | 0.507 | 3.50 | 6.93 |
| Fixed chunks | BGE-small dense | 41 | 24.4% | 51.2% | 63.4% | 0.425 | 36.80 | 42.53 |
| Fixed chunks | Hybrid RRF | 41 | 26.8% | 63.4% | 70.7% | 0.471 | 40.74 | 49.53 |
| Structured chunks | BM25 | 41 | 19.5% | 53.7% | 68.3% | 0.392 | 3.11 | 5.61 |
| Structured chunks | BGE-small dense | 41 | 24.4% | 58.5% | 65.9% | 0.447 | 32.65 | 37.59 |
| Structured chunks | Hybrid RRF | 41 | 26.8% | 61.0% | 73.2% | 0.467 | 36.18 | 42.16 |

## Chunk distributions

| Strategy | Book | Chunks | Min | Median | Mean | Max tokens |
|---|---|---:|---:|---:|---:|---:|
| fixed | biology | 253 | 149 | 404 | 398.0 | 416 |
| fixed | physical_sciences | 300 | 105 | 403 | 399.1 | 415 |
| structured | biology | 244 | 4 | 325 | 328.9 | 500 |
| structured | physical_sciences | 281 | 4 | 324 | 340.2 | 500 |

## Results by book and difficulty

| Group | Strategy | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---:|---:|---:|---:|---:|
| biology | fixed | BM25 | 20 | 35.0% | 75.0% | 90.0% | 0.574 |
| biology | fixed | BGE-small dense | 20 | 25.0% | 60.0% | 75.0% | 0.469 |
| biology | fixed | Hybrid RRF | 20 | 35.0% | 75.0% | 90.0% | 0.562 |
| physical_sciences | fixed | BM25 | 21 | 33.3% | 42.9% | 61.9% | 0.443 |
| physical_sciences | fixed | BGE-small dense | 21 | 23.8% | 42.9% | 52.4% | 0.383 |
| physical_sciences | fixed | Hybrid RRF | 21 | 19.0% | 52.4% | 52.4% | 0.384 |
| biology | structured | BM25 | 20 | 25.0% | 70.0% | 80.0% | 0.482 |
| biology | structured | BGE-small dense | 20 | 30.0% | 65.0% | 65.0% | 0.507 |
| biology | structured | Hybrid RRF | 20 | 45.0% | 70.0% | 85.0% | 0.609 |
| physical_sciences | structured | BM25 | 21 | 14.3% | 38.1% | 57.1% | 0.307 |
| physical_sciences | structured | BGE-small dense | 21 | 19.0% | 52.4% | 66.7% | 0.390 |
| physical_sciences | structured | Hybrid RRF | 21 | 9.5% | 52.4% | 61.9% | 0.331 |
| easy | fixed | BM25 | 7 | 57.1% | 71.4% | 100.0% | 0.707 |
| easy | fixed | BGE-small dense | 7 | 28.6% | 57.1% | 71.4% | 0.493 |
| easy | fixed | Hybrid RRF | 7 | 57.1% | 71.4% | 85.7% | 0.692 |
| hard | fixed | BM25 | 11 | 27.3% | 63.6% | 72.7% | 0.458 |
| hard | fixed | BGE-small dense | 11 | 18.2% | 45.5% | 72.7% | 0.379 |
| hard | fixed | Hybrid RRF | 11 | 9.1% | 63.6% | 72.7% | 0.358 |
| medium | fixed | BM25 | 23 | 30.4% | 52.2% | 69.6% | 0.469 |
| medium | fixed | BGE-small dense | 23 | 26.1% | 52.2% | 56.5% | 0.426 |
| medium | fixed | Hybrid RRF | 23 | 26.1% | 60.9% | 65.2% | 0.457 |
| easy | structured | BM25 | 7 | 42.9% | 71.4% | 100.0% | 0.619 |
| easy | structured | BGE-small dense | 7 | 57.1% | 85.7% | 85.7% | 0.700 |
| easy | structured | Hybrid RRF | 7 | 85.7% | 85.7% | 85.7% | 0.878 |
| hard | structured | BM25 | 11 | 9.1% | 54.5% | 63.6% | 0.312 |
| hard | structured | BGE-small dense | 11 | 18.2% | 54.5% | 54.5% | 0.403 |
| hard | structured | Hybrid RRF | 11 | 9.1% | 54.5% | 63.6% | 0.328 |
| medium | structured | BM25 | 23 | 17.4% | 47.8% | 60.9% | 0.362 |
| medium | structured | BGE-small dense | 23 | 17.4% | 52.2% | 65.2% | 0.391 |
| medium | structured | Hybrid RRF | 23 | 17.4% | 56.5% | 73.9% | 0.408 |

## Dependency and evidence-span slices

| Slice | Strategy | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---:|---:|---:|---:|---:|
| formula dependent | fixed | BM25 | 11 | 18.2% | 27.3% | 54.5% | 0.318 |
| formula dependent | fixed | BGE-small dense | 11 | 27.3% | 45.5% | 45.5% | 0.418 |
| formula dependent | fixed | Hybrid RRF | 11 | 18.2% | 45.5% | 45.5% | 0.367 |
| formula dependent | structured | BM25 | 11 | 18.2% | 45.5% | 54.5% | 0.321 |
| formula dependent | structured | BGE-small dense | 11 | 18.2% | 63.6% | 72.7% | 0.414 |
| formula dependent | structured | Hybrid RRF | 11 | 18.2% | 63.6% | 63.6% | 0.407 |
| visual dependent | fixed | BM25 | 4 | 75.0% | 100.0% | 100.0% | 0.875 |
| visual dependent | fixed | BGE-small dense | 4 | 0.0% | 25.0% | 75.0% | 0.225 |
| visual dependent | fixed | Hybrid RRF | 4 | 0.0% | 100.0% | 100.0% | 0.458 |
| visual dependent | structured | BM25 | 4 | 25.0% | 50.0% | 75.0% | 0.465 |
| visual dependent | structured | BGE-small dense | 4 | 25.0% | 25.0% | 50.0% | 0.354 |
| visual dependent | structured | Hybrid RRF | 4 | 0.0% | 50.0% | 75.0% | 0.328 |
| table dependent | fixed | BM25 | 2 | 0.0% | 100.0% | 100.0% | 0.500 |
| table dependent | fixed | BGE-small dense | 2 | 0.0% | 100.0% | 100.0% | 0.417 |
| table dependent | fixed | Hybrid RRF | 2 | 0.0% | 100.0% | 100.0% | 0.500 |
| table dependent | structured | BM25 | 2 | 0.0% | 100.0% | 100.0% | 0.417 |
| table dependent | structured | BGE-small dense | 2 | 0.0% | 100.0% | 100.0% | 0.500 |
| table dependent | structured | Hybrid RRF | 2 | 50.0% | 100.0% | 100.0% | 0.750 |
| multi page | fixed | BM25 | 12 | 25.0% | 58.3% | 83.3% | 0.477 |
| multi page | fixed | BGE-small dense | 12 | 25.0% | 58.3% | 75.0% | 0.458 |
| multi page | fixed | Hybrid RRF | 12 | 16.7% | 66.7% | 75.0% | 0.433 |
| multi page | structured | BM25 | 12 | 8.3% | 66.7% | 83.3% | 0.367 |
| multi page | structured | BGE-small dense | 12 | 8.3% | 58.3% | 66.7% | 0.374 |
| multi page | structured | Hybrid RRF | 12 | 8.3% | 66.7% | 83.3% | 0.403 |
| multi chunk | fixed | BM25 | 15 | 26.7% | 60.0% | 86.7% | 0.487 |
| multi chunk | fixed | BGE-small dense | 15 | 26.7% | 66.7% | 80.0% | 0.488 |
| multi chunk | fixed | Hybrid RRF | 15 | 20.0% | 73.3% | 80.0% | 0.469 |
| multi chunk | structured | BM25 | 15 | 6.7% | 60.0% | 80.0% | 0.343 |
| multi chunk | structured | BGE-small dense | 15 | 6.7% | 66.7% | 73.3% | 0.388 |
| multi chunk | structured | Hybrid RRF | 15 | 6.7% | 73.3% | 86.7% | 0.400 |

## Gold mapping and top-five failures

Rows whose answer span could not be mapped with at least the configured contiguous-token coverage are excluded from effectiveness metrics and listed for manual review.

| Question | Strategy | Retriever | Gold rank | Likely cause |
|---|---|---|---:|---|
| BIO-002 | fixed | BGE-small dense | 7 | relevant chunk ranked below top 5 |
| BIO-015 | fixed | BGE-small dense | 7 | relevant chunk ranked below top 5 |
| BIO-017 | fixed | BM25 | 22 | multi page evidence dilution |
| BIO-017 | fixed | BGE-small dense | 12 | multi page evidence dilution |
| BIO-017 | fixed | Hybrid RRF | 15 | multi page evidence dilution |
| BIO-018 | fixed | BGE-small dense | 8 | multi page evidence dilution |
| PSC-001 | fixed | BGE-small dense | 17 | formula or symbol extraction mismatch |
| PSC-001 | fixed | Hybrid RRF | 7 | formula or symbol extraction mismatch |
| PSC-002 | fixed | BM25 | 33 | formula or symbol extraction mismatch |
| PSC-002 | fixed | BGE-small dense | 7 | formula or symbol extraction mismatch |
| PSC-002 | fixed | Hybrid RRF | 10 | formula or symbol extraction mismatch |
| PSC-003 | fixed | BM25 | 24 | formula or symbol extraction mismatch |
| PSC-004 | fixed | BGE-small dense | 38 | relevant chunk ranked below top 5 |
| PSC-004 | fixed | Hybrid RRF | 16 | relevant chunk ranked below top 5 |
| PSC-005 | fixed | BM25 | 7 | formula or symbol extraction mismatch |
| PSC-005 | fixed | Hybrid RRF | 8 | formula or symbol extraction mismatch |
| PSC-006 | fixed | BM25 | 16 | formula or symbol extraction mismatch |
| PSC-006 | fixed | BGE-small dense | 11 | formula or symbol extraction mismatch |
| PSC-006 | fixed | Hybrid RRF | 16 | formula or symbol extraction mismatch |
| PSC-007 | fixed | BGE-small dense | 6 | formula or symbol extraction mismatch |
| PSC-010 | fixed | BGE-small dense | 6 | visual evidence not represented in text |
| PSC-013 | fixed | BM25 | 14 | formula or symbol extraction mismatch |
| PSC-013 | fixed | BGE-small dense | 7 | formula or symbol extraction mismatch |
| PSC-013 | fixed | Hybrid RRF | 8 | formula or symbol extraction mismatch |
| PSC-016 | fixed | BGE-small dense | 6 | formula or symbol extraction mismatch |
| PSC-016 | fixed | Hybrid RRF | 7 | formula or symbol extraction mismatch |
| BIO-022 | fixed | BM25 | 41 | relevant chunk ranked below top 5 |
| BIO-022 | fixed | BGE-small dense | 80 | relevant chunk ranked below top 5 |
| BIO-022 | fixed | Hybrid RRF | 53 | relevant chunk ranked below top 5 |
| PSC-021 | fixed | BM25 | 150 | relevant chunk ranked below top 5 |
| PSC-021 | fixed | Hybrid RRF | 20 | relevant chunk ranked below top 5 |
| PSC-023 | fixed | BM25 | 29 | relevant chunk ranked below top 5 |
| PSC-023 | fixed | BGE-small dense | 18 | relevant chunk ranked below top 5 |
| PSC-023 | fixed | Hybrid RRF | 19 | relevant chunk ranked below top 5 |
| PSC-024 | fixed | BM25 | 212 | relevant chunk ranked below top 5 |
| PSC-024 | fixed | BGE-small dense | 8 | relevant chunk ranked below top 5 |
| PSC-024 | fixed | Hybrid RRF | 40 | relevant chunk ranked below top 5 |
| BIO-004 | structured | BGE-small dense | 15 | relevant chunk ranked below top 5 |
| BIO-004 | structured | Hybrid RRF | 7 | relevant chunk ranked below top 5 |
| BIO-005 | structured | BM25 | 6 | multi page evidence dilution |
| BIO-008 | structured | BGE-small dense | 8 | multi page evidence dilution |
| BIO-015 | structured | BGE-small dense | 7 | relevant chunk ranked below top 5 |
| BIO-017 | structured | BM25 | 98 | multi page evidence dilution |
| BIO-017 | structured | BGE-small dense | 28 | multi page evidence dilution |
| BIO-017 | structured | Hybrid RRF | 43 | multi page evidence dilution |
| BIO-018 | structured | BGE-small dense | 8 | multi page evidence dilution |
| PSC-002 | structured | BM25 | 34 | formula or symbol extraction mismatch |
| PSC-002 | structured | BGE-small dense | 153 | formula or symbol extraction mismatch |
| PSC-002 | structured | Hybrid RRF | 70 | formula or symbol extraction mismatch |
| PSC-003 | structured | BM25 | 17 | formula or symbol extraction mismatch |
| PSC-005 | structured | BM25 | 17 | formula or symbol extraction mismatch |
| PSC-005 | structured | Hybrid RRF | 7 | formula or symbol extraction mismatch |
| PSC-006 | structured | BM25 | 12 | formula or symbol extraction mismatch |
| PSC-006 | structured | BGE-small dense | 14 | formula or symbol extraction mismatch |
| PSC-006 | structured | Hybrid RRF | 11 | formula or symbol extraction mismatch |
| PSC-009 | structured | BM25 | 9 | visual evidence not represented in text |
| PSC-009 | structured | BGE-small dense | 21 | visual evidence not represented in text |
| PSC-009 | structured | Hybrid RRF | 16 | visual evidence not represented in text |
| PSC-012 | structured | BGE-small dense | 6 | visual evidence not represented in text |
| PSC-013 | structured | BM25 | 18 | formula or symbol extraction mismatch |
| PSC-013 | structured | BGE-small dense | 17 | formula or symbol extraction mismatch |
| PSC-013 | structured | Hybrid RRF | 17 | formula or symbol extraction mismatch |
| BIO-021 | structured | BM25 | 16 | relevant chunk ranked below top 5 |
| BIO-021 | structured | BGE-small dense | 7 | relevant chunk ranked below top 5 |
| BIO-021 | structured | Hybrid RRF | 7 | relevant chunk ranked below top 5 |
| BIO-022 | structured | BM25 | 17 | relevant chunk ranked below top 5 |
| BIO-022 | structured | BGE-small dense | 6 | relevant chunk ranked below top 5 |
| PSC-021 | structured | BM25 | 152 | relevant chunk ranked below top 5 |
| PSC-021 | structured | Hybrid RRF | 23 | relevant chunk ranked below top 5 |
| PSC-023 | structured | BM25 | 22 | relevant chunk ranked below top 5 |
| PSC-023 | structured | BGE-small dense | 16 | relevant chunk ranked below top 5 |
| PSC-023 | structured | Hybrid RRF | 15 | relevant chunk ranked below top 5 |
| PSC-024 | structured | BM25 | 178 | relevant chunk ranked below top 5 |
| PSC-024 | structured | BGE-small dense | 8 | relevant chunk ranked below top 5 |
| PSC-024 | structured | Hybrid RRF | 37 | relevant chunk ranked below top 5 |

## Per-question improvements and regressions

- **Fixed / BM25:** improves BIO-001, BIO-003, BIO-004, BIO-005, BIO-014, BIO-021, PSC-009, PSC-010, PSC-011, PSC-014, PSC-015, PSC-018; regresses BIO-002, BIO-013, BIO-015, PSC-001, PSC-016.
- **Fixed / BGE-small dense:** improves BIO-004, BIO-005, BIO-008, BIO-021, PSC-008, PSC-009, PSC-011, PSC-014, PSC-015, PSC-018; regresses BIO-002, BIO-003, BIO-007, BIO-010, BIO-013, BIO-014, BIO-016, BIO-018, PSC-001, PSC-004, PSC-007, PSC-010, PSC-012, PSC-016, PSC-017.
- **Fixed / Hybrid RRF:** improves BIO-004, BIO-005, BIO-008, BIO-021, PSC-008, PSC-009, PSC-011, PSC-014, PSC-015, PSC-018; regresses BIO-002, BIO-003, BIO-009, BIO-010, BIO-013, BIO-018, BIO-022, PSC-001, PSC-003, PSC-004, PSC-007, PSC-010, PSC-016.
- **Structured / BM25:** improves BIO-009, BIO-014, PSC-010, PSC-016; regresses BIO-003, BIO-013, BIO-016, PSC-017.
- **Structured / BGE-small dense:** improves BIO-014; regresses BIO-008, BIO-013, BIO-018, PSC-001, PSC-012, PSC-017.
- **Structured / Hybrid RRF:** improves BIO-005, BIO-008, BIO-014, PSC-008; regresses PSC-003, PSC-014, PSC-017.

## Conclusions

Best chunk result is **fixed / BM25** at 75.6% Hit@5 and 0.507 MRR.
Chunk-level retrieval does **not** improve uniformly over page retrieval: fixed BM25 improves Hit@5, while both chunk-level dense variants regress versus page-level dense.
Structure-aware chunking outperforms fixed chunks for dense Hit@3/Hit@5/MRR and hybrid Hit@5. Fixed chunks are stronger for BM25 and retain a slightly higher hybrid MRR.
By retriever, the preferred chunk strategy is fixed for BM25 (75.6%) and dense (63.4%), and structured for hybrid (73.2% with higher MRR).
Automatic chunk scoring is unsuitable without review for: none.
Formula, visual, table, multi-page, and multi-chunk slices are preserved in the JSON metrics; small slice counts should be interpreted descriptively.
Use fixed 400-token chunks with 80-token overlap as the default lexical baseline. Retain structure-aware chunks as the hybrid comparison; they do not justify replacing the fixed default across all retrievers.
Neighbour expansion is the recommended next controlled experiment because it can restore context split at chunk boundaries without changing the first-stage retriever.

## Reproducibility

- Dense: `BAAI/bge-small-en-v1.5` revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, normalized 384-dimensional embeddings on `cpu`.
- BM25: Okapi BM25 k1=1.5, b=0.75. Hybrid: full-ranking RRF k=60.
- Latency excludes startup, corpus construction, and cached embedding creation.
