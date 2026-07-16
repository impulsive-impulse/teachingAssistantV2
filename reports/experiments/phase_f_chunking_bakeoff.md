# Phase F — chunking and multi-granularity retrieval

## BM25 base-corpus screen

| Strategy | Chunks | H@1 | H@3 | H@5 | MRR | Natural H@1/3/5 | Mapping |
|---|---:|---:|---:|---:|---:|---:|---:|
| fixed_300_50 | 700 | 14/61 | 26/61 | 38/61 | 0.382 | 2/6/9 | 61/61 |
| fixed_400_80 | 544 | 17/61 | 31/61 | 41/61 | 0.450 | 3/7/11 | 61/61 |
| fixed_600_100 | 352 | 20/61 | 38/61 | 45/61 | 0.509 | 5/9/12 | 61/61 |
| fixed_400_80_headings | 544 | 17/61 | 32/61 | 42/61 | 0.455 | 3/7/11 | 61/61 |
| paragraph_groups | 855 | 13/61 | 26/61 | 37/61 | 0.366 | 4/4/10 | 61/61 |
| section_aware | 519 | 11/61 | 27/61 | 37/61 | 0.362 | 3/6/9 | 61/61 |

Finalists advancing to E5: `fixed_600_100`, `paragraph_groups`, `fixed_400_80`.

## E5 finalist comparison

| Strategy | Selected | H@1 | H@3 | H@5 | MRR | Natural H@1/3/5 | p95 |
|---|---|---:|---:|---:|---:|---:|---:|
| fixed_600_100 | hybrid_rrf | 19/61 | 36/61 | 43/61 | 0.490 | 5/10/13 | 561.9 ms |
| paragraph_groups | hybrid_rrf | 17/61 | 33/61 | 41/61 | 0.445 | 4/8/12 | 744.1 ms |
| fixed_400_80 | dense | 22/61 | 35/61 | 46/61 | 0.524 | 5/8/12 | 511.7 ms |

## Multi-granularity comparison

| Method | H@1 | H@3 | H@5 | MRR | Natural H@1/3/5 | Candidate recall | p95 | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| parent_page_child | 19/61 | 36/61 | 43/61 | 0.490 | 5/10/13 | 60/61 | 203.3 ms | reject |
| page_prior_rrf | 18/61 | 42/61 | 48/61 | 0.518 | 5/13/14 | 61/61 | 203.6 ms | retain |
| neighbor_expansion | 19/61 | 33/61 | 49/61 | 0.490 | 5/12/16 | 61/61 | 203.2 ms | retain |
| query_relevant_windows | 14/61 | 31/61 | 42/61 | 0.409 | 3/8/14 | 56/61 | 210.2 ms | reject |

## BGE-small confirmation

| Method | H@1 | H@3 | H@5 | MRR | Natural H@1/3/5 | p95 | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| hybrid_rrf | 20/61 | 39/61 | 45/61 | 0.514 | 8/11/14 | 29.0 ms | retain |
| page_prior_rrf | 24/61 | 39/61 | 48/61 | 0.558 | 7/11/16 | 30.8 ms | reject |
