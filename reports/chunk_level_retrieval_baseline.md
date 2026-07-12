# Chunk-Level Retrieval Baseline v1

Fixed-size and structure-aware chunks are compared with the unchanged page baseline. Rankings are book-scoped and never use gold evidence.

## Headline results

| Unit / strategy | Retriever | Scored N | Hit@1 | Hit@3 | Hit@5 | MRR | Avg ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Page | BM25 | 36 | 38.9% | 63.9% | 77.8% | 0.536 | 3.93 | 7.10 |
| Page | BGE-small dense | 36 | 44.4% | 72.2% | 80.6% | 0.609 | 43.38 | 57.62 |
| Page | Hybrid RRF | 36 | 50.0% | 72.2% | 80.6% | 0.634 | 47.84 | 62.89 |
| Fixed chunks | BM25 | 36 | 36.1% | 61.1% | 83.3% | 0.541 | 3.69 | 6.71 |
| Fixed chunks | BGE-small dense | 36 | 22.2% | 52.8% | 66.7% | 0.423 | 36.37 | 40.90 |
| Fixed chunks | Hybrid RRF | 36 | 27.8% | 69.4% | 77.8% | 0.504 | 40.52 | 46.25 |
| Structured chunks | BM25 | 36 | 19.4% | 61.1% | 77.8% | 0.423 | 3.26 | 5.97 |
| Structured chunks | BGE-small dense | 36 | 22.2% | 61.1% | 72.2% | 0.447 | 31.05 | 37.51 |
| Structured chunks | Hybrid RRF | 36 | 27.8% | 69.4% | 80.6% | 0.500 | 34.74 | 41.56 |

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
| biology | fixed | BM25 | 18 | 33.3% | 72.2% | 94.4% | 0.567 |
| biology | fixed | BGE-small dense | 18 | 22.2% | 61.1% | 77.8% | 0.464 |
| biology | fixed | Hybrid RRF | 18 | 33.3% | 77.8% | 94.4% | 0.568 |
| physical_sciences | fixed | BM25 | 18 | 38.9% | 50.0% | 72.2% | 0.514 |
| physical_sciences | fixed | BGE-small dense | 18 | 22.2% | 44.4% | 55.6% | 0.381 |
| physical_sciences | fixed | Hybrid RRF | 18 | 22.2% | 61.1% | 61.1% | 0.440 |
| biology | structured | BM25 | 18 | 27.8% | 77.8% | 88.9% | 0.528 |
| biology | structured | BGE-small dense | 18 | 33.3% | 72.2% | 72.2% | 0.546 |
| biology | structured | Hybrid RRF | 18 | 50.0% | 77.8% | 88.9% | 0.657 |
| physical_sciences | structured | BM25 | 18 | 11.1% | 44.4% | 66.7% | 0.318 |
| physical_sciences | structured | BGE-small dense | 18 | 11.1% | 50.0% | 72.2% | 0.347 |
| physical_sciences | structured | Hybrid RRF | 18 | 5.6% | 61.1% | 72.2% | 0.342 |
| easy | fixed | BM25 | 7 | 57.1% | 57.1% | 100.0% | 0.671 |
| easy | fixed | BGE-small dense | 7 | 28.6% | 57.1% | 71.4% | 0.493 |
| easy | fixed | Hybrid RRF | 7 | 57.1% | 71.4% | 85.7% | 0.692 |
| hard | fixed | BM25 | 10 | 30.0% | 70.0% | 80.0% | 0.503 |
| hard | fixed | BGE-small dense | 10 | 10.0% | 40.0% | 70.0% | 0.317 |
| hard | fixed | Hybrid RRF | 10 | 10.0% | 70.0% | 80.0% | 0.389 |
| medium | fixed | BM25 | 19 | 31.6% | 57.9% | 78.9% | 0.512 |
| medium | fixed | BGE-small dense | 19 | 26.3% | 57.9% | 63.2% | 0.453 |
| medium | fixed | Hybrid RRF | 19 | 26.3% | 68.4% | 73.7% | 0.495 |
| easy | structured | BM25 | 7 | 42.9% | 71.4% | 100.0% | 0.619 |
| easy | structured | BGE-small dense | 7 | 57.1% | 85.7% | 85.7% | 0.700 |
| easy | structured | Hybrid RRF | 7 | 85.7% | 85.7% | 85.7% | 0.878 |
| hard | structured | BM25 | 10 | 10.0% | 60.0% | 70.0% | 0.343 |
| hard | structured | BGE-small dense | 10 | 10.0% | 50.0% | 50.0% | 0.343 |
| hard | structured | Hybrid RRF | 10 | 10.0% | 60.0% | 70.0% | 0.356 |
| medium | structured | BM25 | 19 | 15.8% | 57.9% | 73.7% | 0.394 |
| medium | structured | BGE-small dense | 19 | 15.8% | 57.9% | 78.9% | 0.408 |
| medium | structured | Hybrid RRF | 19 | 15.8% | 68.4% | 84.2% | 0.436 |

## Dependency and evidence-span slices

| Slice | Strategy | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---:|---:|---:|---:|---:|
| formula dependent | fixed | BM25 | 11 | 18.2% | 27.3% | 54.5% | 0.318 |
| formula dependent | fixed | BGE-small dense | 11 | 27.3% | 45.5% | 45.5% | 0.418 |
| formula dependent | fixed | Hybrid RRF | 11 | 18.2% | 45.5% | 45.5% | 0.367 |
| formula dependent | structured | BM25 | 11 | 9.1% | 45.5% | 54.5% | 0.261 |
| formula dependent | structured | BGE-small dense | 11 | 9.1% | 54.5% | 72.7% | 0.346 |
| formula dependent | structured | Hybrid RRF | 11 | 9.1% | 63.6% | 63.6% | 0.346 |
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

## Per-question improvements and regressions

- **Fixed / BM25:** improves BIO-001, BIO-004, BIO-005, BIO-014, PSC-007, PSC-009, PSC-010, PSC-011, PSC-014, PSC-015, PSC-018; regresses BIO-002, BIO-003, BIO-013, BIO-015, PSC-001, PSC-016.
- **Fixed / BGE-small dense:** improves BIO-004, BIO-005, BIO-008, PSC-008, PSC-009, PSC-011, PSC-014, PSC-015, PSC-018; regresses BIO-002, BIO-003, BIO-007, BIO-010, BIO-013, BIO-014, BIO-016, BIO-018, PSC-001, PSC-004, PSC-007, PSC-010, PSC-012, PSC-016, PSC-017.
- **Fixed / Hybrid RRF:** improves BIO-004, BIO-005, BIO-008, PSC-007, PSC-008, PSC-009, PSC-011, PSC-014, PSC-015, PSC-018; regresses BIO-002, BIO-003, BIO-009, BIO-010, BIO-013, BIO-018, PSC-001, PSC-003, PSC-004, PSC-010, PSC-016.
- **Structured / BM25:** improves BIO-009, BIO-014, PSC-010, PSC-016; regresses BIO-003, BIO-013, BIO-016, PSC-017.
- **Structured / BGE-small dense:** improves BIO-014; regresses BIO-008, BIO-013, BIO-018, PSC-001, PSC-012, PSC-017.
- **Structured / Hybrid RRF:** improves BIO-005, BIO-008, BIO-014, PSC-008; regresses PSC-003, PSC-014, PSC-017.

## Conclusions

Best chunk result is **fixed / BM25** at 83.3% Hit@5 and 0.541 MRR.
Chunk-level retrieval does **not** improve uniformly over page retrieval: fixed BM25 improves Hit@5, while both chunk-level dense variants regress versus page-level dense.
Structure-aware chunking outperforms fixed chunks for dense Hit@3/Hit@5/MRR and hybrid Hit@5. Fixed chunks are stronger for BM25 and retain a slightly higher hybrid MRR.
By retriever, the preferred chunk strategy is fixed for BM25 (83.3%) and dense (66.7%), and structured for hybrid (80.6% with higher MRR).
Automatic chunk scoring is unsuitable without review for: none.
Formula, visual, table, multi-page, and multi-chunk slices are preserved in the JSON metrics; small slice counts should be interpreted descriptively.
Use fixed 400-token chunks with 80-token overlap as the default lexical baseline. Retain structure-aware chunks as the hybrid comparison; they do not justify replacing the fixed default across all retrievers.
Neighbour expansion is the recommended next controlled experiment because it can restore context split at chunk boundaries without changing the first-stage retriever.

## Reproducibility

- Dense: `BAAI/bge-small-en-v1.5` revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, normalized 384-dimensional embeddings on `cpu`.
- BM25: Okapi BM25 k1=1.5, b=0.75. Hybrid: full-ranking RRF k=60.
- Latency excludes startup, corpus construction, and cached embedding creation.
