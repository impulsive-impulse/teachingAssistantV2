# Page-Level Retrieval Baseline v1

One cleaned textbook page is one retrieval unit. Front matter is excluded, each query searches only its labeled book, and no gold label participates in ranking.

## Headline results

| Retriever | Hit@1 | Hit@3 | Hit@5 | MRR | Avg latency (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 36.6% | 56.1% | 68.3% | 0.491 | 3.42 | 6.75 |
| BGE-small dense | 43.9% | 68.3% | 73.2% | 0.589 | 40.75 | 61.09 |
| Hybrid RRF | 46.3% | 63.4% | 73.2% | 0.585 | 44.60 | 65.73 |

## Comparison

BM25 ranks the accepted page higher on 10 questions; dense retrieval wins on 20; ties account for the remainder.
Hybrid Hit@5 changes by +0.000 versus dense retrieval. It does not improve Hit@5 on this benchmark.

BM25 wins: BIO-004 (4 vs 15), BIO-006 (1 vs 2), BIO-010 (1 vs 2), BIO-015 (1 vs 7), PSC-001 (1 vs 2), PSC-004 (4 vs 5), PSC-006 (12 vs 13), PSC-009 (10 vs 22), PSC-012 (1 vs 3), PSC-014 (3 vs 4).

Dense wins: BIO-001 (1 vs 2), BIO-002 (1 vs 3), BIO-003 (1 vs 3), BIO-005 (3 vs 7), BIO-007 (2 vs 3), BIO-009 (2 vs 4), BIO-014 (1 vs 2), BIO-017 (19 vs 53), BIO-021 (7 vs 14), BIO-022 (6 vs 17), PSC-002 (8 vs 27), PSC-003 (1 vs 13), PSC-005 (2 vs 20), PSC-008 (1 vs 4), PSC-010 (1 vs 3), PSC-013 (23 vs 26), PSC-018 (2 vs 4), PSC-021 (1 vs 167), PSC-023 (18 vs 22), PSC-024 (8 vs 195).

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

## Results by book

| Book | Retriever | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|
| biology | BM25 | 40.0% | 70.0% | 80.0% | 0.565 |
| biology | BGE-small dense | 45.0% | 75.0% | 75.0% | 0.620 |
| biology | Hybrid RRF | 60.0% | 70.0% | 85.0% | 0.693 |
| physical_sciences | BM25 | 33.3% | 42.9% | 57.1% | 0.422 |
| physical_sciences | BGE-small dense | 42.9% | 61.9% | 71.4% | 0.560 |
| physical_sciences | Hybrid RRF | 33.3% | 57.1% | 61.9% | 0.482 |

## Results by difficulty

| Difficulty | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|---:|
| easy | BM25 | 7 | 42.9% | 85.7% | 100.0% | 0.631 |
| easy | BGE-small dense | 7 | 57.1% | 85.7% | 85.7% | 0.724 |
| easy | Hybrid RRF | 7 | 85.7% | 85.7% | 85.7% | 0.878 |
| hard | BM25 | 11 | 27.3% | 45.5% | 63.6% | 0.409 |
| hard | BGE-small dense | 11 | 36.4% | 72.7% | 72.7% | 0.543 |
| hard | Hybrid RRF | 11 | 27.3% | 63.6% | 63.6% | 0.441 |
| medium | BM25 | 23 | 39.1% | 52.2% | 60.9% | 0.489 |
| medium | BGE-small dense | 23 | 43.5% | 60.9% | 69.6% | 0.570 |
| medium | Hybrid RRF | 23 | 43.5% | 56.5% | 73.9% | 0.564 |

## Dependency and evidence-span slices

Only questions with the named flag are included.

| Slice | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|---:|
| Formula-dependent | BM25 | 11 | 36.4% | 45.5% | 54.5% | 0.443 |
| Formula-dependent | BGE-small dense | 11 | 45.5% | 63.6% | 72.7% | 0.590 |
| Formula-dependent | Hybrid RRF | 11 | 45.5% | 63.6% | 63.6% | 0.581 |
| Visual-dependent | BM25 | 4 | 50.0% | 75.0% | 75.0% | 0.608 |
| Visual-dependent | BGE-small dense | 4 | 50.0% | 75.0% | 75.0% | 0.595 |
| Visual-dependent | Hybrid RRF | 4 | 25.0% | 75.0% | 75.0% | 0.516 |
| Table-dependent | BM25 | 2 | 100.0% | 100.0% | 100.0% | 1.000 |
| Table-dependent | BGE-small dense | 2 | 100.0% | 100.0% | 100.0% | 1.000 |
| Table-dependent | Hybrid RRF | 2 | 100.0% | 100.0% | 100.0% | 1.000 |
| Multi-page | BM25 | 12 | 50.0% | 66.7% | 83.3% | 0.631 |
| Multi-page | BGE-small dense | 12 | 58.3% | 91.7% | 91.7% | 0.740 |
| Multi-page | Hybrid RRF | 12 | 58.3% | 83.3% | 83.3% | 0.723 |
| Multi-chunk | BM25 | 15 | 40.0% | 60.0% | 80.0% | 0.553 |
| Multi-chunk | BGE-small dense | 15 | 46.7% | 93.3% | 93.3% | 0.681 |
| Multi-chunk | Hybrid RRF | 15 | 46.7% | 80.0% | 86.7% | 0.640 |

## Negative and not-answerable questions

5 reviewed negative/weak-evidence questions were retrieved for inspection but excluded from Hit@K and MRR. Their IDs and handling are recorded in `page_level_retrieval_metrics.json`.

## Decision

The result is strong enough as a diagnostic baseline, but 73.2% best Hit@5 is not strong enough to treat page retrieval as a finished retrieval solution. BGE-small is a sufficient lightweight baseline, not a sufficient final retriever; chunk-level experiments should retain BM25 and RRF controls and focus on the documented miss categories.

## Reproducibility

- Dense model: `BAAI/bge-small-en-v1.5` (`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`), 384 dimensions on `cpu`.
- BM25: Okapi BM25, k1=1.5, b=0.75, lowercase alphanumeric tokenization.
- Hybrid: reciprocal rank fusion over full BM25 and dense rankings, RRF k=60.
- Latency is per question/retriever and excludes startup, corpus loading, and cached page embedding creation.
