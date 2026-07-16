# Phase D — Local reranker bake-off

All methods use the lossless 61/61 candidate pool and retained Phase B candidate text. MiniLM was loaded from a pinned offline cache revision.

| Method | Hit@1 | Hit@3 | Hit@5 | MRR | Natural Hit@1 | Natural Hit@3 | Natural Hit@5 | p95 latency | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Soft-fusion-ranked control | 26/61 | 37/61 | 47/61 | 0.557 | 7/20 | 10/20 | 14/20 | 0.2 ms | retain |
| BGE-base rank + RRF | 16/61 | 32/61 | 41/61 | 0.432 | 5/20 | 12/20 | 15/20 | 47023.7 ms | retain |
| MiniLM L6 (reranker_rank_plus_rrf_rank) | 14/61 | 33/61 | 43/61 | 0.421 | 6/20 | 13/20 | 16/20 | 8091.3 ms | retain |

## MiniLM resources

- Revision: `c5ee24cb16019beea0893ab7796b1df96625c6b8`
- Parameters: 22,713,601
- Runtime snapshot: 87.6 MiB
- Cold load: 9264.6 ms; warmup: 45.6 ms
- Peak process memory: 963.5 MiB

Raw model-score and rank+RRF results, all slices, query latencies, and every candidate score are stored in the immutable run directory.

## Successive-stopping screens

| Model | Screen | Natural Hit@5 | Avg latency | p95 latency | Peak memory | Decision |
|---|---:|---:|---:|---:|---:|---|
| BGE-reranker-v2-m3 | 8 balanced queries | 1/4 | 115.1 s | 154.4 s | 2,816.9 MiB | Reject full run |
| mxbai-rerank-base-v1 | planned 8 | unavailable | >300 s before first query | unavailable | 1,121.1 MiB observed | Stop and reject |

## Final Phase D decision

Retain MiniLM L6 with rank+RRF as the only cross-encoder on the Phase D Pareto frontier. It is both faster and stronger on natural/top-5 retrieval than cached BGE-base. Larger models are infeasible or unpromising on this CPU. The Soft-fusion-ranked deduplicated union remains the preferred balanced path when 5–8 seconds of reranking latency is unacceptable.
