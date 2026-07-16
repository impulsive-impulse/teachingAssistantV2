# Phase A — Candidate preservation and compression

Phase A compared gold-blind compression of the audited depth-20 rankings from
Page BGE-small, Fixed 400/80 BM25, Fixed 400/80 BGE-small, and Soft-fusion
Hybrid. Gold evidence was consulted only after candidate selection.

## Result

No fixed budget of 8, 10, 15, or 20 preserved all source-available evidence.
The retained handoff is therefore the complete union after deterministic 0.80
same-page, five-token-shingle deduplication.

| Retained configuration | Candidate recall | Pool size | Hit@1 | Hit@3 | Hit@5 | MRR | Natural Hit@5 | Canonical Hit@5 | Avg latency | p95 latency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Uncompressed deduplicated union | 61/61 (100%) | 31–57; mean 40.8 | 15/61 | 24/61 | 29/61 | 0.373 | 9/20 | 20/41 | 12.2 ms | 21.8 ms |

Latency for the retained run measures full per-query clustering and RRF
ordering after corpus loading. It created no new embedding index and used about
198 MB peak process working memory.

## Eliminated directions

| Configuration | Best candidate recall at budget 20 | Hit@5 | Reason rejected |
|---|---:|---:|---|
| Plain RRF, threshold 0.80 | 57/61 | 29/61 | Four evidence cases discarded |
| Weighted RRF, threshold 0.80 | 57/61 | 29/61 | Four evidence cases discarded |
| Fixed source quotas | 56/61 | 41/61 | Strong top-five ranking but five evidence cases discarded |
| Quotas then RRF | 56/61 | 29/61 | Five evidence cases discarded |
| Unique-source preservation | 59/61 | 26/61 | Still lost PSC-023 and PSC-025 |
| Lexical MMR | 56/61 | 28/61 | Lower recall and far higher selector latency |
| Plain RRF, threshold 0.70 | 58/61 | 47/61 | Aggressive equivalence inflated top-five quality while discarding three cases |
| Query-aware BGE/BM25 MMR, threshold 0.70 | 59/61 | 48/61 | Still lost PSC-023 and PSC-025; p95 280.6 ms |

The high Hit@5 values from aggressive deduplication are invalid as a handoff:
reranking cannot recover accepted evidence removed before scoring.

## Remaining preservation failures at budget 20

- `PSC-023`: accepted evidence first appears at rank 18 in Page BGE-small and
  Fixed 400/80 BGE-small.
- `PSC-025`: accepted evidence first appears at rank 19 in Soft-fusion Hybrid;
  the other source rankings do not contain it inside their audited top 20.

These are deep, source-unique candidates. Rank fusion, quotas, diversity, and
query-aware local BGE/BM25 scoring could not guarantee both within a 20-item
pool without using gold labels.

## Decision

Retain `phase_a_a4_uncompressed_union_t080` as the Phase B input. Candidate
representation and later reranking experiments must begin with all retained
clusters. Any later pruning configuration is invalid when its candidate recall
is below 61/61.
