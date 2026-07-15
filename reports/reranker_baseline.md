# Local Cross-Encoder Reranking Baseline v1

Four existing candidate sources are deduplicated, ordered by deterministic RRF, and capped before local cross-encoder scoring. Gold evidence is used only for evaluation.

## Headline results

| Budget | Ordering | N | Hit@1 | Hit@3 | Hit@5 | MRR | Avg ms | p50 ms | p95 ms | Max ms | Candidates/s |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | rank fusion control | 61 | 15/61 (24.6%) | 24/61 (39.3%) | 29/61 (47.5%) | 0.356 | 0.0 | 0.0 | 0.0 | 0.0 | 3350253.4 |
| 10 | bge reranker base | 61 | 14/61 (23.0%) | 28/61 (45.9%) | 36/61 (59.0%) | 0.378 | 6997.8 | 6998.5 | 12741.0 | 14111.2 | 1.4 |
| 20 | rank fusion control | 61 | 15/61 (24.6%) | 24/61 (39.3%) | 29/61 (47.5%) | 0.371 | 0.0 | 0.0 | 0.0 | 0.0 | 13566292.0 |
| 20 | bge reranker base | 61 | 13/61 (21.3%) | 25/61 (41.0%) | 35/61 (57.4%) | 0.385 | 14547.2 | 14715.2 | 21092.7 | 26640.1 | 1.4 |

Control latency measures deterministic list slicing only; reranker latency measures local batched pair scoring and excludes model/corpus loading.

## Existing candidate-source comparison

These evidence-normalized values use the same accepted-span matching as candidate construction, making them the fairest prior-baseline comparison.

| Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---:|---:|---:|---:|---:|
| page dense bge small | 61 | 16/61 (26.2%) | 33/61 (54.1%) | 38/61 (62.3%) | 0.441 |
| fixed 400 80 bm25 | 61 | 17/61 (27.9%) | 31/61 (50.8%) | 42/61 (68.9%) | 0.451 |
| fixed 400 80 dense bge small | 61 | 13/61 (21.3%) | 30/61 (49.2%) | 37/61 (60.7%) | 0.398 |
| soft fusion hybrid | 61 | 25/61 (41.0%) | 34/61 (55.7%) | 42/61 (68.9%) | 0.523 |

## Canonical and natural-student slices

| Budget | Slice | Ordering | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---:|---|---|---:|---:|---:|---:|---:|
| 10 | canonical | rank fusion control | 41 | 10/41 (24.4%) | 41.5% | 48.8% | 0.365 |
| 10 | canonical | bge reranker base | 41 | 9/41 (22.0%) | 39.0% | 53.7% | 0.347 |
| 10 | natural_student | rank fusion control | 20 | 5/20 (25.0%) | 35.0% | 45.0% | 0.339 |
| 10 | natural_student | bge reranker base | 20 | 5/20 (25.0%) | 60.0% | 70.0% | 0.442 |
| 20 | canonical | rank fusion control | 41 | 10/41 (24.4%) | 41.5% | 48.8% | 0.380 |
| 20 | canonical | bge reranker base | 41 | 10/41 (24.4%) | 36.6% | 51.2% | 0.376 |
| 20 | natural_student | rank fusion control | 20 | 5/20 (25.0%) | 35.0% | 45.0% | 0.353 |
| 20 | natural_student | bge reranker base | 20 | 3/20 (15.0%) | 50.0% | 70.0% | 0.405 |

## Book and dependency slices — reranker

| Budget | Slice | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---:|---|---:|---:|---:|---:|---:|
| 10 | biology | 30 | 36.7% | 60.0% | 66.7% | 0.514 |
| 10 | physical sciences | 31 | 9.7% | 32.3% | 51.6% | 0.246 |
| 10 | formula dependent | 16 | 12.5% | 37.5% | 50.0% | 0.270 |
| 10 | visual dependent | 6 | 16.7% | 33.3% | 66.7% | 0.317 |
| 10 | table dependent | 3 | 33.3% | 33.3% | 33.3% | 0.444 |
| 10 | multi page | 21 | 19.0% | 47.6% | 61.9% | 0.387 |
| 10 | multi chunk | 27 | 25.9% | 59.3% | 70.4% | 0.462 |
| 20 | biology | 30 | 33.3% | 60.0% | 73.3% | 0.518 |
| 20 | physical sciences | 31 | 9.7% | 22.6% | 41.9% | 0.257 |
| 20 | formula dependent | 16 | 6.2% | 25.0% | 43.8% | 0.246 |
| 20 | visual dependent | 6 | 16.7% | 16.7% | 33.3% | 0.278 |
| 20 | table dependent | 3 | 0.0% | 33.3% | 33.3% | 0.234 |
| 20 | multi page | 21 | 14.3% | 42.9% | 52.4% | 0.355 |
| 20 | multi chunk | 27 | 22.2% | 51.9% | 59.3% | 0.424 |

## Natural-query style slices — reranker

| Budget | Query style | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---:|---|---:|---:|---:|---:|---:|
| 10 | cause effect | 3 | 33.3% | 66.7% | 66.7% | 0.500 |
| 10 | colloquial | 4 | 0.0% | 50.0% | 75.0% | 0.312 |
| 10 | different vocabulary | 3 | 33.3% | 33.3% | 66.7% | 0.417 |
| 10 | imperfect grammar | 3 | 100.0% | 100.0% | 100.0% | 1.000 |
| 10 | misconception | 4 | 0.0% | 75.0% | 75.0% | 0.333 |
| 10 | short underspecified | 3 | 0.0% | 33.3% | 33.3% | 0.167 |
| 20 | cause effect | 3 | 0.0% | 0.0% | 33.3% | 0.131 |
| 20 | colloquial | 4 | 0.0% | 25.0% | 50.0% | 0.242 |
| 20 | different vocabulary | 3 | 33.3% | 66.7% | 100.0% | 0.583 |
| 20 | imperfect grammar | 3 | 33.3% | 100.0% | 100.0% | 0.667 |
| 20 | misconception | 4 | 0.0% | 25.0% | 50.0% | 0.248 |
| 20 | short underspecified | 3 | 33.3% | 100.0% | 100.0% | 0.667 |

## Difficulty slices — budget-20 reranker

| Difficulty | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---:|---:|---:|---:|---:|
| easy | 9 | 44.4% | 44.4% | 77.8% | 0.541 |
| hard | 19 | 26.3% | 47.4% | 52.6% | 0.420 |
| medium | 33 | 12.1% | 36.4% | 54.5% | 0.323 |

## Candidate budget and pool recall

| Budget | Gold present in fused pool | Added reranking latency vs 10 |
|---:|---:|---:|
| 10 | 45/61 (73.8%) | +0.0 ms |
| 20 | 57/61 (93.4%) | +7549.4 ms |

## Diagnostics

- Improved from outside top 5 to top 5: BIO-001, BIO-002, BIO-005, BIO-007, BIO-011, BIO-012, BIO-014, BIO-015, PSC-004, PSC-007, PSC-014, PSC-023, BIO-023, BIO-025, BIO-026, BIO-028, BIO-029, BIO-030, PSC-028, PSC-030.
- Improved to rank 1: BIO-002, BIO-005, BIO-006, BIO-007, BIO-011, BIO-012, BIO-014, PSC-007, PSC-021, BIO-025, BIO-030, PSC-030.
- Regressions: BIO-004, BIO-008, BIO-009, BIO-010, BIO-013, BIO-016, PSC-001, PSC-003, PSC-005, PSC-008, PSC-009, PSC-010, PSC-011, PSC-012, PSC-013, PSC-015, PSC-016, PSC-017, PSC-018, BIO-021, BIO-024, BIO-031, PSC-029, PSC-031, PSC-033, PSC-034.
- Gold present but still below 5: BIO-004, BIO-009, BIO-010, BIO-016, PSC-001, PSC-003, PSC-005, PSC-006, PSC-009, PSC-010, PSC-011, PSC-012, PSC-013, PSC-015, PSC-016, PSC-017, PSC-024, BIO-031, BIO-032, PSC-026, PSC-033, PSC-034.

Every regression and top-five miss, including candidate text and all accepted candidate scores, is stored under `diagnostic_cases` in the metrics JSON.

| Question | Slice | Control rank | Reranked rank | Likely cause |
|---|---|---:|---:|---|
| BIO-004 | canonical | 3 | 12 | cross encoder regression |
| BIO-008 | canonical | 1 | 2 | distributed evidence scored independently |
| BIO-009 | canonical | 4 | 7 | distributed evidence scored independently |
| BIO-010 | canonical | 8 | 14 | broad topical context over direct evidence |
| BIO-013 | canonical | 1 | 2 | table structure not expressed in text |
| BIO-016 | canonical | 1 | 8 | table structure not expressed in text |
| BIO-017 | canonical | >20 | >20 | accepted evidence lost during candidate fusion |
| PSC-001 | canonical | 2 | 12 | formula or symbol relevance failure |
| PSC-002 | canonical | >20 | >20 | accepted evidence lost during candidate fusion |
| PSC-003 | canonical | 2 | 8 | formula or symbol relevance failure |
| PSC-005 | canonical | 10 | 16 | formula or symbol relevance failure |
| PSC-006 | canonical | 12 | 11 | formula or symbol relevance failure |
| PSC-008 | canonical | 1 | 4 | formula or symbol relevance failure |
| PSC-009 | canonical | 3 | 14 | visual evidence not expressed in text |
| PSC-010 | canonical | 2 | 6 | visual evidence not expressed in text |
| PSC-011 | canonical | 1 | 10 | visual evidence not expressed in text |
| PSC-012 | canonical | 9 | 13 | visual evidence not expressed in text |
| PSC-013 | canonical | 5 | 10 | formula or symbol relevance failure |
| PSC-015 | canonical | 1 | 8 | formula or symbol relevance failure |
| PSC-016 | canonical | 8 | 10 | formula or symbol relevance failure |
| PSC-017 | canonical | 1 | 13 | cross encoder regression |
| PSC-018 | canonical | 1 | 3 | distributed evidence scored independently |
| BIO-021 | canonical | 1 | 5 | cross encoder regression |
| BIO-022 | canonical | >20 | >20 | accepted evidence lost during candidate fusion |
| PSC-024 | canonical | 12 | 8 | direct evidence scored below topical context |
| BIO-024 | natural_student | 1 | 5 | informal query semantic mismatch |
| BIO-031 | natural_student | 1 | 13 | table structure not expressed in text |
| BIO-032 | natural_student | 10 | 7 | distributed evidence scored independently |
| PSC-025 | natural_student | >20 | >20 | accepted evidence lost during candidate fusion |
| PSC-026 | natural_student | 16 | 7 | informal query semantic mismatch |
| PSC-029 | natural_student | 1 | 4 | visual evidence not expressed in text |
| PSC-031 | natural_student | 3 | 4 | broad topical context over direct evidence |
| PSC-033 | natural_student | 1 | 8 | informal query semantic mismatch |
| PSC-034 | natural_student | 1 | 6 | distributed evidence scored independently |

## Negative/weak-evidence behavior

Top reranker scores average 0.998 for the five excluded queries versus 0.999 for answerable queries. The mean difference is +0.000; this exploratory overlap does not define an abstention threshold.

## Runtime and text policy

- Model: `BAAI/bge-reranker-base`; revision `2cfc18c9415c912f9d8155881c133215df768a70`; device `cpu`.
- Passage content is whitespace-normalized and capped at 1800 characters at a word boundary; the cross-encoder tokenizer additionally caps the complete pair at 512 tokens.
- Query/passage inputs contain source chapter/section titles and content only—never gold, benchmark, difficulty, or dependency metadata.

## Decision

1. At budget 20, reranking changes Hit@1 from 15/61 to 13/61, Hit@3 from 24/61 to 25/61, Hit@5 from 29/61 to 35/61, and MRR from 0.371 to 0.385.
2. Natural-student Hit@5 changes from 9/20 to 14/20 and MRR from 0.353 to 0.405.
3. The fused top-20 pool preserves accepted evidence for 57/61 answerable questions; reranking cannot recover evidence omitted before scoring.
4. Budget 20 changes Hit@5 by -1.6% and average latency by +7549.4 ms versus budget 10.
5. Local reranking adds 14547.2 ms/query on cpu at batch size 32.
6. 22 questions retain gold in the pool but remain below top 5; exact types and scores are in the diagnostics.
7. Do not promote bge-reranker-base yet: it improves the compressed RRF control at Hit@3/5 but remains below the strongest existing individual retriever and regresses Hit@1.
