# Phase C — Fusion and reranking logic

All full-pool methods preserve 61/61 accepted-evidence candidates. Reranker methods reuse the exact cached Phase B BGE scores; no model inference or gold-dependent ranking occurs in this phase.

| Method | Decision | Hit@1 | Hit@3 | Hit@5 | MRR | Natural Hit@1 | Natural Hit@3 | Natural Hit@5 | p95 latency |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `soft_fusion_no_reranker` | retain | 26/61 | 37/61 | 47/61 | 0.557 | 7/20 | 10/20 | 14/20 | 0.2 ms |
| `plain_rrf` | reject | 15/61 | 24/61 | 29/61 | 0.373 | 5/20 | 7/20 | 9/20 | 0.2 ms |
| `weighted_rrf` | reject | 16/61 | 23/61 | 29/61 | 0.379 | 5/20 | 6/20 | 9/20 | 0.2 ms |
| `bge_reranker_score` | reject | 16/61 | 31/61 | 40/61 | 0.422 | 4/20 | 10/20 | 15/20 | 47023.7 ms |
| `bge_rank_plus_rrf_rank` | retain | 16/61 | 32/61 | 41/61 | 0.432 | 5/20 | 12/20 | 15/20 | 47023.7 ms |
| `bge_score_plus_normalized_rrf` | reject | 14/61 | 21/61 | 28/61 | 0.366 | 5/20 | 7/20 | 10/20 | 47023.7 ms |
| `bge_rank_plus_soft_fusion_rank` | reject | 20/61 | 36/61 | 44/61 | 0.484 | 5/20 | 12/20 | 15/20 | 47023.8 ms |

## Candidate-budget gate

The stronger reranker is not executed when a gold-blind preselector has already dropped accepted evidence.

| Preselector | Budget | Candidate recall before reranking | Decision |
|---|---:|---:|---|
| `rrf_preselector` | 8 | 38/61 (62.3%) | reject |
| `rrf_preselector` | 10 | 45/61 (73.8%) | reject |
| `rrf_preselector` | 15 | 54/61 (88.5%) | reject |
| `bm25_fast_reranker` | 8 | 42/61 (68.9%) | reject |
| `bm25_fast_reranker` | 10 | 46/61 (75.4%) | reject |
| `bm25_fast_reranker` | 15 | 50/61 (82.0%) | reject |

## Decision

Retain the full-pool quality and lightweight Pareto configurations shown above. Reject every capped path that violates the 61/61 pre-rerank invariant; do not spend cross-encoder time on an invalid pool.
