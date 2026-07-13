# Chunk-Level Retrieval Baseline v1

Fixed-size and structure-aware chunks are compared with the unchanged page baseline. Rankings are book-scoped and never use gold evidence.

## Headline results

| Unit / strategy | Retriever | Scored N | Hit@1 | Hit@3 | Hit@5 | MRR | Avg ms | p95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Page | BM25 | 61 | 31.1% | 50.8% | 62.3% | 0.448 | 3.07 | 5.56 |
| Page | BGE-small dense | 61 | 37.7% | 65.6% | 70.5% | 0.541 | 32.37 | 37.68 |
| Page | Hybrid RRF | 61 | 37.7% | 59.0% | 70.5% | 0.524 | 35.87 | 42.13 |
| Fixed chunks | BM25 | 61 | 27.9% | 50.8% | 68.9% | 0.451 | 3.66 | 6.57 |
| Fixed chunks | BGE-small dense | 61 | 21.3% | 49.2% | 60.7% | 0.398 | 33.53 | 40.45 |
| Fixed chunks | Hybrid RRF | 61 | 24.6% | 57.4% | 68.9% | 0.444 | 37.62 | 45.25 |
| Structured chunks | BM25 | 61 | 18.0% | 45.9% | 60.7% | 0.364 | 3.26 | 5.18 |
| Structured chunks | BGE-small dense | 61 | 21.3% | 52.5% | 60.7% | 0.406 | 30.64 | 35.03 |
| Structured chunks | Hybrid RRF | 61 | 21.3% | 57.4% | 67.2% | 0.416 | 34.32 | 39.94 |

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
| biology | fixed | BM25 | 30 | 26.7% | 60.0% | 80.0% | 0.482 |
| biology | fixed | BGE-small dense | 30 | 20.0% | 56.7% | 70.0% | 0.422 |
| biology | fixed | Hybrid RRF | 30 | 30.0% | 63.3% | 83.3% | 0.495 |
| physical_sciences | fixed | BM25 | 31 | 29.0% | 41.9% | 58.1% | 0.420 |
| physical_sciences | fixed | BGE-small dense | 31 | 22.6% | 41.9% | 51.6% | 0.374 |
| physical_sciences | fixed | Hybrid RRF | 31 | 19.4% | 51.6% | 54.8% | 0.395 |
| biology | structured | BM25 | 30 | 23.3% | 56.7% | 70.0% | 0.434 |
| biology | structured | BGE-small dense | 30 | 30.0% | 63.3% | 66.7% | 0.497 |
| biology | structured | Hybrid RRF | 30 | 36.7% | 66.7% | 76.7% | 0.541 |
| physical_sciences | structured | BM25 | 31 | 12.9% | 35.5% | 51.6% | 0.296 |
| physical_sciences | structured | BGE-small dense | 31 | 12.9% | 41.9% | 54.8% | 0.318 |
| physical_sciences | structured | Hybrid RRF | 31 | 6.5% | 48.4% | 58.1% | 0.295 |
| easy | fixed | BM25 | 9 | 55.6% | 66.7% | 88.9% | 0.680 |
| easy | fixed | BGE-small dense | 9 | 22.2% | 55.6% | 66.7% | 0.442 |
| easy | fixed | Hybrid RRF | 9 | 55.6% | 66.7% | 77.8% | 0.655 |
| hard | fixed | BM25 | 19 | 21.1% | 52.6% | 68.4% | 0.402 |
| hard | fixed | BGE-small dense | 19 | 21.1% | 42.1% | 57.9% | 0.376 |
| hard | fixed | Hybrid RRF | 19 | 15.8% | 57.9% | 73.7% | 0.393 |
| medium | fixed | BM25 | 33 | 24.2% | 45.5% | 63.6% | 0.416 |
| medium | fixed | BGE-small dense | 33 | 21.2% | 51.5% | 60.6% | 0.398 |
| medium | fixed | Hybrid RRF | 33 | 21.2% | 54.5% | 63.6% | 0.416 |
| easy | structured | BM25 | 9 | 44.4% | 66.7% | 88.9% | 0.606 |
| easy | structured | BGE-small dense | 9 | 55.6% | 77.8% | 77.8% | 0.663 |
| easy | structured | Hybrid RRF | 9 | 77.8% | 77.8% | 77.8% | 0.806 |
| hard | structured | BM25 | 19 | 15.8% | 47.4% | 63.2% | 0.354 |
| hard | structured | BGE-small dense | 19 | 15.8% | 47.4% | 52.6% | 0.362 |
| hard | structured | Hybrid RRF | 19 | 10.5% | 57.9% | 68.4% | 0.341 |
| medium | structured | BM25 | 33 | 12.1% | 39.4% | 51.5% | 0.303 |
| medium | structured | BGE-small dense | 33 | 15.2% | 48.5% | 60.6% | 0.362 |
| medium | structured | Hybrid RRF | 33 | 12.1% | 51.5% | 63.6% | 0.353 |

## Canonical versus natural-student queries

| Slice | Strategy | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---:|---:|---:|---:|---:|
| canonical | fixed | BM25 | 41 | 34.1% | 58.5% | 75.6% | 0.507 |
| canonical | fixed | BGE-small dense | 41 | 24.4% | 51.2% | 63.4% | 0.425 |
| canonical | fixed | Hybrid RRF | 41 | 26.8% | 63.4% | 70.7% | 0.471 |
| natural_student | fixed | BM25 | 20 | 15.0% | 35.0% | 55.0% | 0.335 |
| natural_student | fixed | BGE-small dense | 20 | 15.0% | 45.0% | 55.0% | 0.342 |
| natural_student | fixed | Hybrid RRF | 20 | 20.0% | 45.0% | 65.0% | 0.390 |
| canonical | structured | BM25 | 41 | 19.5% | 53.7% | 68.3% | 0.392 |
| canonical | structured | BGE-small dense | 41 | 24.4% | 58.5% | 65.9% | 0.447 |
| canonical | structured | Hybrid RRF | 41 | 26.8% | 61.0% | 73.2% | 0.467 |
| natural_student | structured | BM25 | 20 | 15.0% | 30.0% | 45.0% | 0.305 |
| natural_student | structured | BGE-small dense | 20 | 15.0% | 40.0% | 50.0% | 0.322 |
| natural_student | structured | Hybrid RRF | 20 | 10.0% | 50.0% | 55.0% | 0.312 |

Natural-student results are also broken down by `query_style` in `chunk_level_retrieval_metrics.json`.

## Dependency and evidence-span slices

| Slice | Strategy | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---|---:|---:|---:|---:|---:|
| formula dependent | fixed | BM25 | 16 | 12.5% | 25.0% | 43.8% | 0.272 |
| formula dependent | fixed | BGE-small dense | 16 | 18.8% | 37.5% | 43.8% | 0.342 |
| formula dependent | fixed | Hybrid RRF | 16 | 12.5% | 37.5% | 43.8% | 0.321 |
| formula dependent | structured | BM25 | 16 | 12.5% | 37.5% | 43.8% | 0.275 |
| formula dependent | structured | BGE-small dense | 16 | 12.5% | 50.0% | 56.2% | 0.338 |
| formula dependent | structured | Hybrid RRF | 16 | 12.5% | 50.0% | 56.2% | 0.340 |
| visual dependent | fixed | BM25 | 6 | 83.3% | 100.0% | 100.0% | 0.917 |
| visual dependent | fixed | BGE-small dense | 6 | 16.7% | 33.3% | 66.7% | 0.344 |
| visual dependent | fixed | Hybrid RRF | 6 | 16.7% | 100.0% | 100.0% | 0.556 |
| visual dependent | structured | BM25 | 6 | 33.3% | 50.0% | 66.7% | 0.505 |
| visual dependent | structured | BGE-small dense | 6 | 16.7% | 33.3% | 50.0% | 0.302 |
| visual dependent | structured | Hybrid RRF | 6 | 0.0% | 50.0% | 66.7% | 0.302 |
| table dependent | fixed | BM25 | 3 | 0.0% | 100.0% | 100.0% | 0.500 |
| table dependent | fixed | BGE-small dense | 3 | 0.0% | 66.7% | 66.7% | 0.325 |
| table dependent | fixed | Hybrid RRF | 3 | 0.0% | 66.7% | 100.0% | 0.417 |
| table dependent | structured | BM25 | 3 | 0.0% | 100.0% | 100.0% | 0.444 |
| table dependent | structured | BGE-small dense | 3 | 0.0% | 100.0% | 100.0% | 0.444 |
| table dependent | structured | Hybrid RRF | 3 | 33.3% | 100.0% | 100.0% | 0.667 |
| multi page | fixed | BM25 | 21 | 23.8% | 57.1% | 76.2% | 0.453 |
| multi page | fixed | BGE-small dense | 21 | 19.0% | 47.6% | 66.7% | 0.386 |
| multi page | fixed | Hybrid RRF | 21 | 19.0% | 57.1% | 71.4% | 0.430 |
| multi page | structured | BM25 | 21 | 14.3% | 57.1% | 71.4% | 0.382 |
| multi page | structured | BGE-small dense | 21 | 9.5% | 52.4% | 61.9% | 0.345 |
| multi page | structured | Hybrid RRF | 21 | 9.5% | 61.9% | 71.4% | 0.378 |
| multi chunk | fixed | BM25 | 27 | 22.2% | 51.9% | 77.8% | 0.433 |
| multi chunk | fixed | BGE-small dense | 27 | 25.9% | 59.3% | 74.1% | 0.455 |
| multi chunk | fixed | Hybrid RRF | 27 | 22.2% | 63.0% | 77.8% | 0.461 |
| multi chunk | structured | BM25 | 27 | 11.1% | 48.1% | 70.4% | 0.346 |
| multi chunk | structured | BGE-small dense | 27 | 11.1% | 59.3% | 66.7% | 0.378 |
| multi chunk | structured | Hybrid RRF | 27 | 7.4% | 70.4% | 77.8% | 0.380 |

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
| BIO-023 | fixed | BM25 | 6 | relevant chunk ranked below top 5 |
| BIO-023 | fixed | BGE-small dense | 45 | relevant chunk ranked below top 5 |
| BIO-023 | fixed | Hybrid RRF | 18 | relevant chunk ranked below top 5 |
| BIO-026 | fixed | BM25 | 7 | multi page evidence dilution |
| BIO-027 | fixed | BM25 | 15 | multi page evidence dilution |
| BIO-027 | fixed | Hybrid RRF | 8 | multi page evidence dilution |
| BIO-030 | fixed | BGE-small dense | 7 | multi page evidence dilution |
| BIO-031 | fixed | BGE-small dense | 7 | table structure lost in extraction |
| BIO-032 | fixed | BM25 | 38 | multi page evidence dilution |
| BIO-032 | fixed | BGE-small dense | 19 | multi page evidence dilution |
| BIO-032 | fixed | Hybrid RRF | 13 | multi page evidence dilution |
| PSC-025 | fixed | BM25 | 37 | formula or symbol extraction mismatch |
| PSC-025 | fixed | BGE-small dense | 42 | formula or symbol extraction mismatch |
| PSC-025 | fixed | Hybrid RRF | 40 | formula or symbol extraction mismatch |
| PSC-026 | fixed | BM25 | 6 | relevant chunk ranked below top 5 |
| PSC-026 | fixed | BGE-small dense | 30 | relevant chunk ranked below top 5 |
| PSC-026 | fixed | Hybrid RRF | 14 | relevant chunk ranked below top 5 |
| PSC-027 | fixed | BM25 | 9 | formula or symbol extraction mismatch |
| PSC-027 | fixed | Hybrid RRF | 6 | formula or symbol extraction mismatch |
| PSC-028 | fixed | BM25 | 15 | formula or symbol extraction mismatch |
| PSC-028 | fixed | BGE-small dense | 6 | formula or symbol extraction mismatch |
| PSC-030 | fixed | BGE-small dense | 6 | visual evidence not represented in text |
| PSC-031 | fixed | BM25 | 7 | formula or symbol extraction mismatch |
| PSC-031 | fixed | BGE-small dense | 7 | formula or symbol extraction mismatch |
| PSC-031 | fixed | Hybrid RRF | 6 | formula or symbol extraction mismatch |
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
| BIO-023 | structured | BM25 | 8 | relevant chunk ranked below top 5 |
| BIO-023 | structured | BGE-small dense | 16 | relevant chunk ranked below top 5 |
| BIO-023 | structured | Hybrid RRF | 9 | relevant chunk ranked below top 5 |
| BIO-026 | structured | BM25 | 6 | multi page evidence dilution |
| BIO-027 | structured | BM25 | 17 | multi page evidence dilution |
| BIO-027 | structured | BGE-small dense | 12 | multi page evidence dilution |
| BIO-027 | structured | Hybrid RRF | 12 | multi page evidence dilution |
| BIO-029 | structured | BM25 | 13 | relevant chunk ranked below top 5 |
| BIO-029 | structured | Hybrid RRF | 6 | relevant chunk ranked below top 5 |
| BIO-032 | structured | BM25 | 236 | multi page evidence dilution |
| BIO-032 | structured | BGE-small dense | 19 | multi page evidence dilution |
| BIO-032 | structured | Hybrid RRF | 59 | multi page evidence dilution |
| PSC-025 | structured | BM25 | 45 | formula or symbol extraction mismatch |
| PSC-025 | structured | BGE-small dense | 41 | formula or symbol extraction mismatch |
| PSC-025 | structured | Hybrid RRF | 40 | formula or symbol extraction mismatch |
| PSC-026 | structured | BM25 | 7 | relevant chunk ranked below top 5 |
| PSC-026 | structured | BGE-small dense | 30 | relevant chunk ranked below top 5 |
| PSC-026 | structured | Hybrid RRF | 15 | relevant chunk ranked below top 5 |
| PSC-027 | structured | BM25 | 7 | formula or symbol extraction mismatch |
| PSC-027 | structured | BGE-small dense | 7 | formula or symbol extraction mismatch |
| PSC-027 | structured | Hybrid RRF | 6 | formula or symbol extraction mismatch |
| PSC-028 | structured | BM25 | 27 | formula or symbol extraction mismatch |
| PSC-028 | structured | BGE-small dense | 13 | formula or symbol extraction mismatch |
| PSC-028 | structured | Hybrid RRF | 13 | formula or symbol extraction mismatch |
| PSC-029 | structured | BM25 | 6 | visual evidence not represented in text |
| PSC-030 | structured | BGE-small dense | 15 | visual evidence not represented in text |
| PSC-030 | structured | Hybrid RRF | 6 | visual evidence not represented in text |
| PSC-031 | structured | BM25 | 6 | formula or symbol extraction mismatch |
| PSC-031 | structured | BGE-small dense | 9 | formula or symbol extraction mismatch |
| PSC-034 | structured | BGE-small dense | 8 | multi page evidence dilution |

## Per-question improvements and regressions

- **Fixed / BM25:** improves BIO-001, BIO-003, BIO-004, BIO-005, BIO-014, BIO-021, BIO-029, BIO-030, PSC-009, PSC-010, PSC-011, PSC-014, PSC-015, PSC-018, PSC-029, PSC-032, PSC-033; regresses BIO-002, BIO-013, BIO-015, BIO-025, BIO-031, PSC-001, PSC-016.
- **Fixed / BGE-small dense:** improves BIO-004, BIO-005, BIO-008, BIO-021, BIO-026, BIO-028, PSC-008, PSC-009, PSC-011, PSC-014, PSC-015, PSC-018, PSC-027, PSC-029, PSC-032, PSC-033, PSC-034; regresses BIO-002, BIO-003, BIO-007, BIO-010, BIO-013, BIO-014, BIO-016, BIO-018, BIO-024, BIO-025, BIO-027, BIO-030, BIO-031, BIO-032, PSC-001, PSC-004, PSC-007, PSC-010, PSC-012, PSC-016, PSC-017, PSC-030.
- **Fixed / Hybrid RRF:** improves BIO-004, BIO-005, BIO-008, BIO-021, BIO-028, BIO-029, PSC-008, PSC-009, PSC-011, PSC-014, PSC-015, PSC-018, PSC-028, PSC-029, PSC-030, PSC-032, PSC-033, PSC-034; regresses BIO-002, BIO-003, BIO-009, BIO-010, BIO-013, BIO-018, BIO-022, BIO-025, BIO-027, BIO-030, BIO-031, BIO-032, PSC-001, PSC-003, PSC-004, PSC-007, PSC-010, PSC-016.
- **Structured / BM25:** improves BIO-009, BIO-014, BIO-030, PSC-010, PSC-016, PSC-032, PSC-033; regresses BIO-003, BIO-013, BIO-016, BIO-025, BIO-031, PSC-017, PSC-029.
- **Structured / BGE-small dense:** improves BIO-014, BIO-030, PSC-032, PSC-033; regresses BIO-008, BIO-013, BIO-018, BIO-027, BIO-032, PSC-001, PSC-012, PSC-017, PSC-030.
- **Structured / Hybrid RRF:** improves BIO-005, BIO-008, BIO-014, BIO-030, PSC-008, PSC-031, PSC-032, PSC-033; regresses BIO-025, BIO-027, BIO-032, PSC-003, PSC-014, PSC-017, PSC-030.

## Conclusions

Best chunk result is **fixed / BM25** at 68.9% Hit@5 and 0.451 MRR.
Chunk-level retrieval does **not** improve uniformly over page retrieval: fixed BM25 improves Hit@5, while both chunk-level dense variants regress versus page-level dense.
Structure-aware chunking outperforms fixed chunks for dense Hit@3/Hit@5/MRR and hybrid Hit@5. Fixed chunks are stronger for BM25 and retain a slightly higher hybrid MRR.
By retriever, the preferred chunk strategy is fixed for BM25 (68.9%) and dense (60.7%), and structured for hybrid (67.2% with higher MRR).
Automatic chunk scoring is unsuitable without review for: none.
Formula, visual, table, multi-page, and multi-chunk slices are preserved in the JSON metrics; small slice counts should be interpreted descriptively.
Use fixed 400-token chunks with 80-token overlap as the default lexical baseline. Retain structure-aware chunks as the hybrid comparison; they do not justify replacing the fixed default across all retrievers.
Neighbour expansion is the recommended next controlled experiment because it can restore context split at chunk boundaries without changing the first-stage retriever.

## Reproducibility

- Dense: `BAAI/bge-small-en-v1.5` revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, normalized 384-dimensional embeddings on `cpu`.
- BM25: Okapi BM25 k1=1.5, b=0.75. Hybrid: full-ranking RRF k=60.
- Latency excludes startup, corpus construction, and cached embedding creation.
