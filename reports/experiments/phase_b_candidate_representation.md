# Phase B — Candidate text representation

All cross-encoder runs begin with the retained 61/61 Phase A candidate union. Gold labels do not affect member selection, passage construction, model scoring, or sorting.

| Run | Representation | Hit@1 | Hit@3 | Hit@5 | MRR | Natural Hit@1 | Natural Hit@5 | Avg latency | p95 latency |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `phase_b_b4_rerank_combination_shortest_member_leading_text_chapter_section_chunk` | combination_shortest_member_leading_text_chapter_section_chunk | 13/61 | 28/61 | 31/61 | 0.372 | 3/20 | 11/20 | 23569.2 ms | 33782.7 ms |
| `phase_b_b4_rerank_combination_dense_best_member_leading_text_chapter_section_chunk` | combination_dense_best_member_leading_text_chapter_section_chunk | 17/61 | 29/61 | 35/61 | 0.409 | 4/20 | 13/20 | 27864.5 ms | 36255.6 ms |
| `phase_b_b4_rerank_combination_dense_best_member_leading_text_neighbor_expansion` | combination_dense_best_member_leading_text_neighbor_expansion | 16/61 | 27/61 | 37/61 | 0.408 | 3/20 | 14/20 | 26935.4 ms | 40695.3 ms |
| `phase_b_b4_rerank_combination_dense_best_member_two_relevant_windows_neighbor_expansion` | combination_dense_best_member_two_relevant_windows_neighbor_expansion **(retained)** | 16/61 | 31/61 | 40/61 | 0.422 | 4/20 | 15/20 | 36689.3 ms | 48287.1 ms |

## Decision

Retain `combination_dense_best_member_two_relevant_windows_neighbor_expansion` for Phase C. Its structural candidate recall is 61/61; the conservative contiguous-span visibility diagnostic is 60/61.

The visibility diagnostic is stricter than semantic sufficiency for some multi-page natural queries. For example, BIO-032 receives text explicitly stating that retained rainwater recharges dried wells even when it does not cover 50% of the longer inherited canonical answer span.

Every top-five miss and every scored candidate remains inspectable in the immutable per-run JSONL artifacts.
