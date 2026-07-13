# Page-Level Retrieval Baseline v1

One cleaned textbook page is one retrieval unit. Front matter is excluded, each query searches only its labeled book, and no gold label participates in ranking.

## Headline results

| Retriever | Hit@1 | Hit@3 | Hit@5 | MRR | Avg latency (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 31.1% | 50.8% | 62.3% | 0.448 | 3.07 | 5.56 |
| BGE-small dense | 37.7% | 65.6% | 70.5% | 0.541 | 32.37 | 37.68 |
| Hybrid RRF | 37.7% | 59.0% | 70.5% | 0.524 | 35.87 | 42.13 |

## Comparison

BM25 ranks the accepted page higher on 16 questions; dense retrieval wins on 29; ties account for the remainder.
Hybrid Hit@5 changes by +0.000 versus dense retrieval. It does not improve Hit@5 on this benchmark.

BM25 wins: BIO-004 (4 vs 15), BIO-006 (1 vs 2), BIO-010 (1 vs 2), BIO-015 (1 vs 7), BIO-023 (7 vs 16), BIO-031 (1 vs 3), PSC-001 (1 vs 2), PSC-004 (4 vs 5), PSC-006 (12 vs 13), PSC-009 (10 vs 22), PSC-012 (1 vs 3), PSC-014 (3 vs 4), PSC-026 (7 vs 30), PSC-030 (1 vs 3), PSC-033 (4 vs 5), PSC-034 (5 vs 7).

Dense wins: BIO-001 (1 vs 2), BIO-002 (1 vs 3), BIO-003 (1 vs 3), BIO-005 (3 vs 7), BIO-007 (2 vs 3), BIO-009 (2 vs 4), BIO-014 (1 vs 2), BIO-017 (19 vs 53), BIO-021 (7 vs 14), BIO-022 (6 vs 17), BIO-025 (1 vs 3), BIO-026 (2 vs 6), BIO-027 (2 vs 10), BIO-029 (2 vs 13), BIO-032 (1 vs 6), PSC-002 (8 vs 27), PSC-003 (1 vs 13), PSC-005 (2 vs 20), PSC-008 (1 vs 4), PSC-010 (1 vs 3), PSC-013 (23 vs 26), PSC-018 (2 vs 4), PSC-021 (1 vs 167), PSC-023 (18 vs 22), PSC-024 (8 vs 195), PSC-025 (43 vs 47), PSC-027 (6 vs 9), PSC-028 (14 vs 25), PSC-029 (1 vs 2).

## Top-5 failures

| Question | Retriever | Likely cause | Best accepted rank |
|---|---|---|---:|
| BIO-004 | BGE-small dense | relevant page ranked below top 5 | 15 |
| BIO-004 | Hybrid RRF | relevant page ranked below top 5 | 7 |
| BIO-005 | BM25 | multi page evidence dilution | 7 |
| BIO-015 | BGE-small dense | relevant page ranked below top 5 | 7 |
| BIO-017 | BM25 | multi page evidence dilution | 53 |
| BIO-017 | BGE-small dense | multi page evidence dilution | 19 |
| BIO-017 | Hybrid RRF | multi page evidence dilution | 28 |
| PSC-002 | BM25 | formula or symbol extraction mismatch | 27 |
| PSC-002 | BGE-small dense | formula or symbol extraction mismatch | 8 |
| PSC-002 | Hybrid RRF | formula or symbol extraction mismatch | 9 |
| PSC-003 | BM25 | formula or symbol extraction mismatch | 13 |
| PSC-005 | BM25 | formula or symbol extraction mismatch | 20 |
| PSC-005 | Hybrid RRF | formula or symbol extraction mismatch | 7 |
| PSC-006 | BM25 | formula or symbol extraction mismatch | 12 |
| PSC-006 | BGE-small dense | formula or symbol extraction mismatch | 13 |
| PSC-006 | Hybrid RRF | formula or symbol extraction mismatch | 11 |
| PSC-009 | BM25 | visual evidence not represented in text | 10 |
| PSC-009 | BGE-small dense | visual evidence not represented in text | 22 |
| PSC-009 | Hybrid RRF | visual evidence not represented in text | 16 |
| PSC-013 | BM25 | formula or symbol extraction mismatch | 26 |
| PSC-013 | BGE-small dense | formula or symbol extraction mismatch | 23 |
| PSC-013 | Hybrid RRF | formula or symbol extraction mismatch | 24 |
| BIO-021 | BM25 | relevant page ranked below top 5 | 14 |
| BIO-021 | BGE-small dense | relevant page ranked below top 5 | 7 |
| BIO-021 | Hybrid RRF | relevant page ranked below top 5 | 7 |
| BIO-022 | BM25 | relevant page ranked below top 5 | 17 |
| BIO-022 | BGE-small dense | relevant page ranked below top 5 | 6 |
| PSC-021 | BM25 | relevant page ranked below top 5 | 167 |
| PSC-021 | Hybrid RRF | relevant page ranked below top 5 | 23 |
| PSC-023 | BM25 | relevant page ranked below top 5 | 22 |
| PSC-023 | BGE-small dense | relevant page ranked below top 5 | 18 |
| PSC-023 | Hybrid RRF | relevant page ranked below top 5 | 16 |
| PSC-024 | BM25 | relevant page ranked below top 5 | 195 |
| PSC-024 | BGE-small dense | relevant page ranked below top 5 | 8 |
| PSC-024 | Hybrid RRF | relevant page ranked below top 5 | 38 |
| BIO-023 | BM25 | relevant page ranked below top 5 | 7 |
| BIO-023 | BGE-small dense | relevant page ranked below top 5 | 16 |
| BIO-023 | Hybrid RRF | relevant page ranked below top 5 | 9 |
| BIO-026 | BM25 | multi page evidence dilution | 6 |
| BIO-027 | BM25 | multi page evidence dilution | 10 |
| BIO-029 | BM25 | relevant page ranked below top 5 | 13 |
| BIO-029 | Hybrid RRF | relevant page ranked below top 5 | 6 |
| BIO-032 | BM25 | multi page evidence dilution | 6 |
| PSC-025 | BM25 | formula or symbol extraction mismatch | 47 |
| PSC-025 | BGE-small dense | formula or symbol extraction mismatch | 43 |
| PSC-025 | Hybrid RRF | formula or symbol extraction mismatch | 42 |
| PSC-026 | BM25 | relevant page ranked below top 5 | 7 |
| PSC-026 | BGE-small dense | relevant page ranked below top 5 | 30 |
| PSC-026 | Hybrid RRF | relevant page ranked below top 5 | 14 |
| PSC-027 | BM25 | formula or symbol extraction mismatch | 9 |
| PSC-027 | BGE-small dense | formula or symbol extraction mismatch | 6 |
| PSC-027 | Hybrid RRF | formula or symbol extraction mismatch | 6 |
| PSC-028 | BM25 | formula or symbol extraction mismatch | 25 |
| PSC-028 | BGE-small dense | formula or symbol extraction mismatch | 14 |
| PSC-028 | Hybrid RRF | formula or symbol extraction mismatch | 14 |
| PSC-031 | BM25 | formula or symbol extraction mismatch | 9 |
| PSC-031 | BGE-small dense | formula or symbol extraction mismatch | 9 |
| PSC-031 | Hybrid RRF | formula or symbol extraction mismatch | 6 |
| PSC-034 | BGE-small dense | multi page evidence dilution | 7 |

## Results by book

| Book | Retriever | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|
| biology | BM25 | 36.7% | 63.3% | 70.0% | 0.526 |
| biology | BGE-small dense | 43.3% | 80.0% | 80.0% | 0.627 |
| biology | Hybrid RRF | 50.0% | 70.0% | 83.3% | 0.639 |
| physical_sciences | BM25 | 25.8% | 38.7% | 54.8% | 0.373 |
| physical_sciences | BGE-small dense | 32.3% | 51.6% | 61.3% | 0.457 |
| physical_sciences | Hybrid RRF | 25.8% | 48.4% | 58.1% | 0.412 |

## Results by difficulty

| Difficulty | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|---:|
| easy | BM25 | 9 | 44.4% | 77.8% | 88.9% | 0.618 |
| easy | BGE-small dense | 9 | 55.6% | 77.8% | 77.8% | 0.681 |
| easy | Hybrid RRF | 9 | 77.8% | 77.8% | 77.8% | 0.806 |
| hard | BM25 | 19 | 31.6% | 47.4% | 63.2% | 0.455 |
| hard | BGE-small dense | 19 | 31.6% | 73.7% | 73.7% | 0.521 |
| hard | Hybrid RRF | 19 | 21.1% | 68.4% | 73.7% | 0.444 |
| medium | BM25 | 33 | 27.3% | 45.5% | 54.5% | 0.398 |
| medium | BGE-small dense | 33 | 36.4% | 57.6% | 66.7% | 0.514 |
| medium | Hybrid RRF | 33 | 36.4% | 48.5% | 66.7% | 0.493 |

## Canonical versus natural-student queries

Natural-student rows reuse canonical gold evidence but are scored as a separate query slice.

| Benchmark slice | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|---:|
| canonical | BM25 | 41 | 36.6% | 56.1% | 68.3% | 0.491 |
| canonical | BGE-small dense | 41 | 43.9% | 68.3% | 73.2% | 0.589 |
| canonical | Hybrid RRF | 41 | 46.3% | 63.4% | 73.2% | 0.585 |
| natural_student | BM25 | 20 | 20.0% | 40.0% | 50.0% | 0.360 |
| natural_student | BGE-small dense | 20 | 25.0% | 60.0% | 65.0% | 0.441 |
| natural_student | Hybrid RRF | 20 | 20.0% | 50.0% | 65.0% | 0.399 |

### Natural-student results by query style

| Query style | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|---:|
| cause_effect | BM25 | 3 | 0.0% | 33.3% | 33.3% | 0.229 |
| cause_effect | BGE-small dense | 3 | 66.7% | 66.7% | 66.7% | 0.674 |
| cause_effect | Hybrid RRF | 3 | 33.3% | 66.7% | 66.7% | 0.508 |
| colloquial | BM25 | 4 | 25.0% | 25.0% | 50.0% | 0.373 |
| colloquial | BGE-small dense | 4 | 25.0% | 50.0% | 75.0% | 0.433 |
| colloquial | Hybrid RRF | 4 | 25.0% | 25.0% | 75.0% | 0.380 |
| different_vocabulary | BM25 | 3 | 33.3% | 33.3% | 33.3% | 0.407 |
| different_vocabulary | BGE-small dense | 3 | 33.3% | 66.7% | 66.7% | 0.521 |
| different_vocabulary | Hybrid RRF | 3 | 33.3% | 33.3% | 33.3% | 0.426 |
| imperfect_grammar | BM25 | 3 | 0.0% | 66.7% | 66.7% | 0.259 |
| imperfect_grammar | BGE-small dense | 3 | 33.3% | 66.7% | 66.7% | 0.500 |
| imperfect_grammar | Hybrid RRF | 3 | 33.3% | 66.7% | 66.7% | 0.500 |
| misconception | BM25 | 4 | 25.0% | 50.0% | 75.0% | 0.453 |
| misconception | BGE-small dense | 4 | 0.0% | 50.0% | 50.0% | 0.272 |
| misconception | Hybrid RRF | 4 | 0.0% | 75.0% | 75.0% | 0.375 |
| short_underspecified | BM25 | 3 | 33.3% | 33.3% | 33.3% | 0.402 |
| short_underspecified | BGE-small dense | 3 | 0.0% | 66.7% | 66.7% | 0.302 |
| short_underspecified | Hybrid RRF | 3 | 0.0% | 33.3% | 66.7% | 0.218 |

## Dependency and evidence-span slices

Only questions with the named flag are included.

| Slice | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|---:|
| Formula-dependent | BM25 | 16 | 25.0% | 37.5% | 43.8% | 0.343 |
| Formula-dependent | BGE-small dense | 16 | 31.2% | 50.0% | 56.2% | 0.450 |
| Formula-dependent | Hybrid RRF | 16 | 31.2% | 50.0% | 50.0% | 0.447 |
| Visual-dependent | BM25 | 6 | 50.0% | 83.3% | 83.3% | 0.656 |
| Visual-dependent | BGE-small dense | 6 | 50.0% | 83.3% | 83.3% | 0.619 |
| Visual-dependent | Hybrid RRF | 6 | 33.3% | 66.7% | 83.3% | 0.552 |
| Table-dependent | BM25 | 3 | 100.0% | 100.0% | 100.0% | 1.000 |
| Table-dependent | BGE-small dense | 3 | 66.7% | 100.0% | 100.0% | 0.778 |
| Table-dependent | Hybrid RRF | 3 | 66.7% | 100.0% | 100.0% | 0.833 |
| Multi-page | BM25 | 21 | 42.9% | 66.7% | 76.2% | 0.585 |
| Multi-page | BGE-small dense | 21 | 47.6% | 90.5% | 90.5% | 0.669 |
| Multi-page | Hybrid RRF | 21 | 42.9% | 76.2% | 85.7% | 0.625 |
| Multi-chunk | BM25 | 27 | 33.3% | 59.3% | 74.1% | 0.508 |
| Multi-chunk | BGE-small dense | 27 | 40.7% | 88.9% | 88.9% | 0.631 |
| Multi-chunk | Hybrid RRF | 27 | 37.0% | 77.8% | 88.9% | 0.582 |

## Negative and not-answerable questions

5 reviewed negative/weak-evidence questions were retrieved for inspection but excluded from Hit@K and MRR. Their IDs and handling are recorded in `page_level_retrieval_metrics.json`.

## Decision

The result is strong enough as a diagnostic baseline, but 70.5% best Hit@5 is not strong enough to treat page retrieval as a finished retrieval solution. BGE-small is a sufficient lightweight baseline, not a sufficient final retriever; chunk-level experiments should retain BM25 and RRF controls and focus on the documented miss categories.

## Reproducibility

- Dense model: `BAAI/bge-small-en-v1.5` (`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`), 384 dimensions on `cpu`.
- BM25: Okapi BM25, k1=1.5, b=0.75, lowercase alphanumeric tokenization.
- Hybrid: reciprocal rank fusion over full BM25 and dense rankings, RRF k=60.
- Latency is per question/retriever and excludes startup, corpus loading, and cached page embedding creation.
