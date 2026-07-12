# Page-Level Retrieval Baseline v1

One cleaned textbook page is one retrieval unit. Front matter is excluded, each query searches only its labeled book, and no gold label participates in ranking.

## Headline results

| Retriever | Hit@1 | Hit@3 | Hit@5 | MRR | Avg latency (ms) | p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 38.9% | 63.9% | 77.8% | 0.536 | 3.93 | 7.10 |
| BGE-small dense | 44.4% | 72.2% | 80.6% | 0.609 | 43.38 | 57.62 |
| Hybrid RRF | 50.0% | 72.2% | 80.6% | 0.634 | 47.84 | 62.89 |

## Comparison

BM25 ranks the accepted page higher on 11 questions; dense retrieval wins on 15; ties account for the remainder.
Hybrid Hit@5 changes by +0.000 versus dense retrieval. It does not improve Hit@5 on this benchmark.

BM25 wins: BIO-004 (4 vs 15), BIO-006 (1 vs 2), BIO-010 (1 vs 2), BIO-015 (1 vs 7), PSC-001 (1 vs 2), PSC-004 (4 vs 5), PSC-006 (12 vs 13), PSC-007 (3 vs 4), PSC-009 (10 vs 22), PSC-012 (1 vs 3), PSC-014 (3 vs 4).

Dense wins: BIO-001 (1 vs 2), BIO-002 (1 vs 3), BIO-003 (1 vs 3), BIO-005 (3 vs 7), BIO-007 (2 vs 3), BIO-009 (2 vs 4), BIO-014 (1 vs 2), BIO-017 (19 vs 53), PSC-002 (8 vs 27), PSC-003 (1 vs 13), PSC-005 (2 vs 20), PSC-008 (1 vs 4), PSC-010 (1 vs 3), PSC-013 (23 vs 26), PSC-018 (2 vs 4).

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

## Results by book

| Book | Retriever | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|
| biology | BM25 | 44.4% | 77.8% | 88.9% | 0.620 |
| biology | BGE-small dense | 50.0% | 83.3% | 83.3% | 0.672 |
| biology | Hybrid RRF | 66.7% | 77.8% | 88.9% | 0.751 |
| physical_sciences | BM25 | 33.3% | 50.0% | 66.7% | 0.452 |
| physical_sciences | BGE-small dense | 38.9% | 61.1% | 77.8% | 0.546 |
| physical_sciences | Hybrid RRF | 33.3% | 66.7% | 72.2% | 0.518 |

## Results by difficulty

| Difficulty | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|---:|
| easy | BM25 | 7 | 42.9% | 85.7% | 100.0% | 0.631 |
| easy | BGE-small dense | 7 | 57.1% | 85.7% | 85.7% | 0.724 |
| easy | Hybrid RRF | 7 | 85.7% | 85.7% | 85.7% | 0.878 |
| hard | BM25 | 10 | 30.0% | 50.0% | 70.0% | 0.449 |
| hard | BGE-small dense | 10 | 30.0% | 70.0% | 70.0% | 0.497 |
| hard | Hybrid RRF | 10 | 30.0% | 70.0% | 70.0% | 0.481 |
| medium | BM25 | 19 | 42.1% | 63.2% | 73.7% | 0.547 |
| medium | BGE-small dense | 19 | 47.4% | 68.4% | 84.2% | 0.625 |
| medium | Hybrid RRF | 19 | 47.4% | 68.4% | 84.2% | 0.625 |

## Dependency and evidence-span slices

Only questions with the named flag are included.

| Slice | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|---:|
| Formula-dependent | BM25 | 11 | 27.3% | 45.5% | 54.5% | 0.382 |
| Formula-dependent | BGE-small dense | 11 | 36.4% | 54.5% | 72.7% | 0.522 |
| Formula-dependent | Hybrid RRF | 11 | 36.4% | 63.6% | 63.6% | 0.520 |
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

4 reviewed negative/weak-evidence questions were retrieved for inspection but excluded from Hit@K and MRR. Their IDs and handling are recorded in `page_level_retrieval_metrics.json`.

## Decision

The result is strong enough as a diagnostic baseline to proceed to chunk-level experiments, but 80.6% best Hit@5 is not strong enough to treat page retrieval as a finished retrieval solution. BGE-small is a sufficient lightweight baseline, not a sufficient final retriever; chunk-level experiments should retain BM25 and RRF controls and focus on the documented miss categories.

## Reproducibility

- Dense model: `BAAI/bge-small-en-v1.5` (`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`), 384 dimensions on `cpu`.
- BM25: Okapi BM25, k1=1.5, b=0.75, lowercase alphanumeric tokenization.
- Hybrid: reciprocal rank fusion over full BM25 and dense rankings, RRF k=60.
- Latency is per question/retriever and excludes startup, corpus loading, and cached page embedding creation.
