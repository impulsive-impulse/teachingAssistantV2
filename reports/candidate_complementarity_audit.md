# Candidate Complementarity Audit v1

This audit reconstructs existing rankings only; it adds no retriever, reranker, query rewriting, LLM, or gold-aware ranking. BGE-small corpus embeddings were loaded from the existing validated caches.

A candidate is correct only when it maps to reviewed gold/alternative pages **and** satisfies the existing contiguous answer-span rule for its retrieval unit. Candidates sharing a PDF page and at least 80% five-token-shingle containment are deduplicated as substantially the same evidence.

## Primary individual retrievers

| Slice | Retriever | N | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Hit@20 | MRR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| all answerable | Page BGE-small | 61 | 16/61 (26.2%) | 33/61 (54.1%) | 38/61 (62.3%) | 49/61 (80.3%) | 56/61 (91.8%) | 0.441 |
| all answerable | Page BM25 | 61 | 14/61 (23.0%) | 26/61 (42.6%) | 37/61 (60.7%) | 45/61 (73.8%) | 51/61 (83.6%) | 0.380 |
| all answerable | Fixed 400/80 BM25 | 61 | 17/61 (27.9%) | 31/61 (50.8%) | 42/61 (68.9%) | 48/61 (78.7%) | 52/61 (85.2%) | 0.451 |
| all answerable | Soft-fusion Hybrid | 61 | 25/61 (41.0%) | 34/61 (55.7%) | 42/61 (68.9%) | 47/61 (77.0%) | 52/61 (85.2%) | 0.523 |
| canonical | Page BGE-small | 41 | 13/41 (31.7%) | 25/41 (61.0%) | 28/41 (68.3%) | 35/41 (85.4%) | 38/41 (92.7%) | 0.503 |
| canonical | Page BM25 | 41 | 10/41 (24.4%) | 21/41 (51.2%) | 28/41 (68.3%) | 30/41 (73.2%) | 35/41 (85.4%) | 0.414 |
| canonical | Fixed 400/80 BM25 | 41 | 14/41 (34.1%) | 24/41 (58.5%) | 31/41 (75.6%) | 32/41 (78.0%) | 34/41 (82.9%) | 0.507 |
| canonical | Soft-fusion Hybrid | 41 | 18/41 (43.9%) | 24/41 (58.5%) | 30/41 (73.2%) | 32/41 (78.0%) | 34/41 (82.9%) | 0.552 |
| natural student | Page BGE-small | 20 | 3/20 (15.0%) | 8/20 (40.0%) | 10/20 (50.0%) | 14/20 (70.0%) | 18/20 (90.0%) | 0.314 |
| natural student | Page BM25 | 20 | 4/20 (20.0%) | 5/20 (25.0%) | 9/20 (45.0%) | 15/20 (75.0%) | 16/20 (80.0%) | 0.311 |
| natural student | Fixed 400/80 BM25 | 20 | 3/20 (15.0%) | 7/20 (35.0%) | 11/20 (55.0%) | 16/20 (80.0%) | 18/20 (90.0%) | 0.335 |
| natural student | Soft-fusion Hybrid | 20 | 7/20 (35.0%) | 10/20 (50.0%) | 12/20 (60.0%) | 15/20 (75.0%) | 18/20 (90.0%) | 0.463 |

## Candidate unions

Oracle Hit@K gives every member its own top-K budget before cross-method deduplication. Thus a four-method Oracle Hit@10 pool has at most 40 raw candidates; actual average pool sizes are recorded below and in JSON.

| Slice | Union | N | Oracle Hit@5 | Oracle Hit@10 | Oracle Hit@20 |
|---|---|---:|---:|---:|---:|
| all answerable | page bge plus page bm25 | 61 | 44/61 (72.1%) | 54/61 (88.5%) | 58/61 (95.1%) |
| all answerable | page bge plus fixed bm25 | 61 | 46/61 (75.4%) | 54/61 (88.5%) | 59/61 (96.7%) |
| all answerable | page bge plus soft fusion hybrid | 61 | 47/61 (77.0%) | 53/61 (86.9%) | 59/61 (96.7%) |
| all answerable | page bge plus fixed bm25 plus soft fusion hybrid | 61 | 47/61 (77.0%) | 54/61 (88.5%) | 60/61 (98.4%) |
| all answerable | all primary retrievers | 61 | 47/61 (77.0%) | 54/61 (88.5%) | 60/61 (98.4%) |
| canonical | page bge plus page bm25 | 41 | 32/41 (78.0%) | 37/41 (90.2%) | 39/41 (95.1%) |
| canonical | page bge plus fixed bm25 | 41 | 34/41 (82.9%) | 37/41 (90.2%) | 40/41 (97.6%) |
| canonical | page bge plus soft fusion hybrid | 41 | 34/41 (82.9%) | 37/41 (90.2%) | 39/41 (95.1%) |
| canonical | page bge plus fixed bm25 plus soft fusion hybrid | 41 | 34/41 (82.9%) | 37/41 (90.2%) | 40/41 (97.6%) |
| canonical | all primary retrievers | 41 | 34/41 (82.9%) | 37/41 (90.2%) | 40/41 (97.6%) |
| natural student | page bge plus page bm25 | 20 | 12/20 (60.0%) | 17/20 (85.0%) | 19/20 (95.0%) |
| natural student | page bge plus fixed bm25 | 20 | 12/20 (60.0%) | 17/20 (85.0%) | 19/20 (95.0%) |
| natural student | page bge plus soft fusion hybrid | 20 | 13/20 (65.0%) | 16/20 (80.0%) | 20/20 (100.0%) |
| natural student | page bge plus fixed bm25 plus soft fusion hybrid | 20 | 13/20 (65.0%) | 17/20 (85.0%) | 20/20 (100.0%) |
| natural student | all primary retrievers | 20 | 13/20 (65.0%) | 17/20 (85.0%) | 20/20 (100.0%) |

### All-primary candidate budgets

| Per-method depth | Max raw | Avg raw | Avg after deduplication |
|---:|---:|---:|---:|
| 5 | 20 | 20.0 | 11.5 |
| 10 | 40 | 40.0 | 21.7 |
| 20 | 80 | 80.0 | 40.8 |

## Primary complementarity at depth 20

| Pair | Both correct | Only left | Only right | Both miss | Evidence Jaccard | Unique useful left/right |
|---|---:|---:|---:|---:|---:|---:|
| Page BGE-small vs Page BM25 | 49 | 7 | 2 | 3 | 38.5% | 7/2 |
| Page BGE-small vs Fixed 400/80 BM25 | 49 | 7 | 3 | 2 | 22.8% | 32/26 |
| Page BGE-small vs Soft-fusion Hybrid | 49 | 7 | 3 | 2 | 30.5% | 22/22 |
| Page BM25 vs Fixed 400/80 BM25 | 49 | 2 | 3 | 7 | 36.0% | 27/30 |
| Page BM25 vs Soft-fusion Hybrid | 49 | 2 | 3 | 7 | 31.5% | 16/22 |
| Fixed 400/80 BM25 vs Soft-fusion Hybrid | 48 | 4 | 4 | 5 | 41.8% | 13/12 |

## Unique primary wins

A unique win means that method alone retrieves accepted evidence at the stated depth among the four primary methods.

### Depth 5

- Page BGE-small: 3 — PSC-003, PSC-005, PSC-021
- Page BM25: 0 — none
- Fixed 400/80 BM25: 0 — none
- Soft-fusion Hybrid: 1 — BIO-027

### Depth 10

- Page BGE-small: 4 — PSC-002, BIO-022, PSC-021, PSC-024
- Page BM25: 0 — none
- Fixed 400/80 BM25: 0 — none
- Soft-fusion Hybrid: 0 — none

### Depth 20

- Page BGE-small: 4 — PSC-002, PSC-023, PSC-024, BIO-032
- Page BM25: 0 — none
- Fixed 400/80 BM25: 1 — PSC-013
- Soft-fusion Hybrid: 1 — PSC-025

## Page dense versus keyword-only wins at depth 20

- Page BGE-small succeeds while Page BM25 misses: PSC-002, PSC-021, PSC-023, PSC-024, BIO-027, BIO-032, PSC-028.
- Page BM25 succeeds while Page BGE-small misses: PSC-009, PSC-026.

## Best-union slices

| Slice | N | Oracle Hit@5 | Oracle Hit@10 | Oracle Hit@20 |
|---|---:|---:|---:|---:|
| book:biology | 30 | 26/30 (86.7%) | 28/30 (93.3%) | 29/30 (96.7%) |
| book:physical sciences | 31 | 21/31 (67.7%) | 26/31 (83.9%) | 31/31 (100.0%) |
| formula dependent | 16 | 9/16 (56.2%) | 12/16 (75.0%) | 16/16 (100.0%) |
| visual dependent | 6 | 6/6 (100.0%) | 6/6 (100.0%) | 6/6 (100.0%) |
| table dependent | 3 | 3/3 (100.0%) | 3/3 (100.0%) | 3/3 (100.0%) |
| multi page | 21 | 18/21 (85.7%) | 19/21 (90.5%) | 20/21 (95.2%) |
| multi chunk | 27 | 24/27 (88.9%) | 25/27 (92.6%) | 26/27 (96.3%) |
| query style:cause effect | 3 | 1/3 (33.3%) | 1/3 (33.3%) | 3/3 (100.0%) |
| query style:colloquial | 4 | 3/4 (75.0%) | 4/4 (100.0%) | 4/4 (100.0%) |
| query style:different vocabulary | 3 | 2/3 (66.7%) | 3/3 (100.0%) | 3/3 (100.0%) |
| query style:imperfect grammar | 3 | 2/3 (66.7%) | 3/3 (100.0%) | 3/3 (100.0%) |
| query style:misconception | 4 | 3/4 (75.0%) | 4/4 (100.0%) | 4/4 (100.0%) |
| query style:short underspecified | 3 | 2/3 (66.7%) | 2/3 (66.7%) | 3/3 (100.0%) |

## Additional existing methods

These variants are diagnostic only; they are not silently added to the primary architecture decision.

| Retriever | Hit@5 | Hit@10 | Hit@20 | MRR |
|---|---:|---:|---:|---:|
| Page Hybrid RRF | 40/61 (65.6%) | 49/61 (80.3%) | 54/61 (88.5%) | 0.452 |
| Fixed 400/80 BGE-small | 37/61 (60.7%) | 51/61 (83.6%) | 56/61 (91.8%) | 0.398 |
| Fixed 400/80 Hybrid | 42/61 (68.9%) | 50/61 (82.0%) | 58/61 (95.1%) | 0.444 |
| Structured BM25 | 37/61 (60.7%) | 45/61 (73.8%) | 53/61 (86.9%) | 0.364 |
| Structured BGE-small | 37/61 (60.7%) | 47/61 (77.0%) | 56/61 (91.8%) | 0.406 |
| Structured Hybrid | 41/61 (67.2%) | 48/61 (78.7%) | 55/61 (90.2%) | 0.416 |
| Strict-cascade BM25 | 20/61 (32.8%) | 22/61 (36.1%) | 24/61 (39.3%) | 0.208 |
| Strict-cascade BGE-small | 39/61 (63.9%) | 46/61 (75.4%) | 49/61 (80.3%) | 0.447 |
| Strict-cascade Hybrid | 36/61 (59.0%) | 41/61 (67.2%) | 45/61 (73.8%) | 0.446 |
| Soft-fusion BM25 | 38/61 (62.3%) | 44/61 (72.1%) | 47/61 (77.0%) | 0.423 |
| Soft-fusion BGE-small | 40/61 (65.6%) | 46/61 (75.4%) | 54/61 (88.5%) | 0.451 |

## Questions missed by every required candidate union at depth 20

| Question | Slice | Likely cause | Additional method that rescues it |
|---|---|---|---|
| BIO-017: How do nervous control and hormonal control coordinate responses in the human body? | canonical | multi page evidence | Fixed 400/80 BGE-small, Fixed 400/80 Hybrid |

## Questions missed by every audited method at depth 20

None. Every answerable question has accepted evidence in at least one audited top-20 list.

## Decision

1. Canonical threshold: **yes** (37/41 at Hit@10; 40/41 at Hit@20).
2. Natural-student threshold: **yes** (17/20 at Hit@10; 20/20 at Hit@20).
3. Does every primary retriever contribute uniquely? **no — Page BGE-small, Fixed 400/80 BM25, Soft-fusion Hybrid contribute unique wins, but Page BM25 does not**.
4. Reranker candidate sufficiency: **yes**.
5. Retain: Page BGE-small, Fixed 400/80 BM25, Soft-fusion Hybrid, Fixed 400/80 BGE-small.
6. Separate candidate sources not recommended because their recall is redundant: Page BM25.
7. Remaining-miss focus: candidate fusion and reranking; candidate generation already covers every answerable row at depth 20.

Full pairwise tables for all 15 existing methods, exact question IDs, and every slice are in `candidate_complementarity_metrics.json`.
