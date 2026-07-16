# Experiment decisions

## Measurement clarification — Phase A1/A2/A3 selector runs

- The recorded A1/A2 selector latency measures selection over precomputed evidence clusters; it excludes corpus loading and full-text deduplication. The original run-record label said clustering was included, which was too broad.
- The retained fallback run measures full per-query clustering separately. Historical JSONL records remain append-only and were not rewritten.

## 2026-07-15T18:54:48+00:00 — phase_a_a1_unique_source_preservation_t080

- Decision: **investigate** — A1 finalist: 59/61 recall at budget 20; confirm deduplication sensitivity.
- Evidence: candidate recall 59/61; Hit@1 7/61; Hit@5 26/61; MRR 0.251.
- Next: Run the next Phase A1 selector.

## 2026-07-15T18:54:49+00:00 — phase_a_a1_weighted_rrf_t080

- Decision: **investigate** — A1 finalist: 57/61 recall at budget 20; confirm deduplication sensitivity.
- Evidence: candidate recall 57/61; Hit@1 16/61; Hit@5 29/61; MRR 0.376.
- Next: Run the next Phase A1 selector.

## 2026-07-15T18:54:49+00:00 — phase_a_a1_plain_rrf_t080

- Decision: **investigate** — A1 finalist: 57/61 recall at budget 20; confirm deduplication sensitivity.
- Evidence: candidate recall 57/61; Hit@1 15/61; Hit@5 29/61; MRR 0.371.
- Next: Run the next Phase A1 selector.

## 2026-07-15T18:54:50+00:00 — phase_a_a1_fixed_source_quotas_t080

- Decision: **reject** — Dominated in the controlled A1 shortlist; best evaluated recall is 56/61 at the selected budget.
- Evidence: candidate recall 56/61; Hit@1 18/61; Hit@5 41/61; MRR 0.474.
- Next: Run the next Phase A1 selector.

## 2026-07-15T18:54:50+00:00 — phase_a_a1_quotas_then_rrf_t080

- Decision: **reject** — Dominated in the controlled A1 shortlist; best evaluated recall is 56/61 at the selected budget.
- Evidence: candidate recall 56/61; Hit@1 15/61; Hit@5 29/61; MRR 0.376.
- Next: Run the next Phase A1 selector.

## 2026-07-15T18:57:31+00:00 — phase_a_a1_diversity_mmr_t080

- Decision: **reject** — Dominated in the controlled A1 shortlist; best evaluated recall is 56/61 at the selected budget.
- Evidence: candidate recall 56/61; Hit@1 15/61; Hit@5 28/61; MRR 0.370.
- Next: Run deduplication-threshold confirmation for the three A1 finalists.

## 2026-07-15T18:58:30+00:00 — phase_a_a2_unique_source_preservation_t080

- Decision: **reject** — Not the Phase A Pareto winner; recall 59/61 at budget 20.
- Evidence: candidate recall 59/61; Hit@1 7/61; Hit@5 26/61; MRR 0.251.
- Next: Run the next Phase A2 confirmation.

## 2026-07-15T18:58:31+00:00 — phase_a_a2_plain_rrf_t070

- Decision: **reject** — Not the Phase A Pareto winner; recall 58/61 at budget 20.
- Evidence: candidate recall 58/61; Hit@1 19/61; Hit@5 47/61; MRR 0.504.
- Next: Run the next Phase A2 confirmation.

## 2026-07-15T18:58:31+00:00 — phase_a_a2_unique_source_preservation_t090

- Decision: **reject** — Not the Phase A Pareto winner; recall 58/61 at budget 20.
- Evidence: candidate recall 58/61; Hit@1 9/61; Hit@5 35/61; MRR 0.313.
- Next: Run the next Phase A2 confirmation.

## 2026-07-15T18:58:32+00:00 — phase_a_a2_unique_source_preservation_t070

- Decision: **reject** — Not the Phase A Pareto winner; recall 58/61 at budget 20.
- Evidence: candidate recall 58/61; Hit@1 2/61; Hit@5 27/61; MRR 0.196.
- Next: Run the next Phase A2 confirmation.

## 2026-07-15T18:58:32+00:00 — phase_a_a2_weighted_rrf_t070

- Decision: **reject** — Not the Phase A Pareto winner; recall 57/61 at budget 20.
- Evidence: candidate recall 57/61; Hit@1 18/61; Hit@5 47/61; MRR 0.495.
- Next: Run the next Phase A2 confirmation.

## 2026-07-15T18:58:32+00:00 — phase_a_a2_weighted_rrf_t080

- Decision: **reject** — Not the Phase A Pareto winner; recall 57/61 at budget 20.
- Evidence: candidate recall 57/61; Hit@1 16/61; Hit@5 29/61; MRR 0.376.
- Next: Run the next Phase A2 confirmation.

## 2026-07-15T18:58:33+00:00 — phase_a_a2_plain_rrf_t080

- Decision: **reject** — Not the Phase A Pareto winner; recall 57/61 at budget 20.
- Evidence: candidate recall 57/61; Hit@1 15/61; Hit@5 29/61; MRR 0.371.
- Next: Run the next Phase A2 confirmation.

## 2026-07-15T18:58:33+00:00 — phase_a_a2_plain_rrf_t090

- Decision: **reject** — Not the Phase A Pareto winner; recall 55/61 at budget 20.
- Evidence: candidate recall 55/61; Hit@1 17/61; Hit@5 35/61; MRR 0.421.
- Next: Run the next Phase A2 confirmation.

## 2026-07-15T18:58:34+00:00 — phase_a_a2_weighted_rrf_t090

- Decision: **reject** — Not the Phase A Pareto winner; recall 55/61 at budget 20.
- Evidence: candidate recall 55/61; Hit@1 18/61; Hit@5 34/61; MRR 0.422.
- Next: Investigate an uncompressed fallback because no budget <=20 was lossless.

## 2026-07-15T19:06:25+00:00 — phase_a_a3_query_relevance_mmr_t070

- Decision: **reject** — Not a lossless Phase A winner; recall 59/61 at budget 20.
- Evidence: candidate recall 59/61; Hit@1 18/61; Hit@5 48/61; MRR 0.515.
- Next: Run the next query-aware Phase A configuration.

## 2026-07-15T19:06:52+00:00 — phase_a_a3_query_relevance_mmr_t080

- Decision: **reject** — Not a lossless Phase A winner; recall 58/61 at budget 20.
- Evidence: candidate recall 58/61; Hit@1 18/61; Hit@5 44/61; MRR 0.473.
- Next: Run the next query-aware Phase A configuration.

## 2026-07-15T19:07:00+00:00 — phase_a_a3_query_relevance_fusion_t080

- Decision: **reject** — Not a lossless Phase A winner; recall 58/61 at budget 20.
- Evidence: candidate recall 58/61; Hit@1 18/61; Hit@5 44/61; MRR 0.473.
- Next: Run the next query-aware Phase A configuration.

## 2026-07-15T19:07:35+00:00 — phase_a_a3_query_relevance_mmr_t090

- Decision: **reject** — Not a lossless Phase A winner; recall 57/61 at budget 20.
- Evidence: candidate recall 57/61; Hit@1 24/61; Hit@5 46/61; MRR 0.534.
- Next: Retain the uncompressed deduplicated union and report that budget 20 cannot satisfy the invariant.
## 2026-07-15T19:09:15+00:00 — phase_a_a4_uncompressed_union_t080

- Decision: **retain** — Only the full deduplicated union preserves every source-available accepted evidence case.
- Evidence: candidate recall 61/61; Hit@1 15/61; Hit@5 29/61; MRR 0.373.
- Next: Begin Phase B representation experiments over the lossless full union.

## 2026-07-15T19:15:25+00:00 — phase_b_b0_chunk_neighbor_expansion

- Decision: **investigate** — B0 finalist: accepted evidence remains visible for 52/61 questions with 1837 average characters.
- Evidence: candidate recall 61/61; Hit@1 10/61; Hit@5 19/61; MRR 0.259.
- Next: Run the next Phase B0 representation pre-screen.

## 2026-07-15T19:15:26+00:00 — phase_b_b0_chunk_raw_chunk

- Decision: **investigate** — B0 finalist: accepted evidence remains visible for 49/61 questions with 1660 average characters.
- Evidence: candidate recall 61/61; Hit@1 7/61; Hit@5 14/61; MRR 0.200.
- Next: Run the next Phase B0 representation pre-screen.

## 2026-07-15T19:15:26+00:00 — phase_b_b0_chunk_chapter_chunk

- Decision: **reject** — Dominated in deterministic B0 visibility/length screening: 49/61 visible.
- Evidence: candidate recall 61/61; Hit@1 7/61; Hit@5 14/61; MRR 0.200.
- Next: Run the next Phase B0 representation pre-screen.

## 2026-07-15T19:15:26+00:00 — phase_b_b0_chunk_chapter_section_chunk

- Decision: **investigate** — B0 finalist: accepted evidence remains visible for 49/61 questions with 1709 average characters.
- Evidence: candidate recall 61/61; Hit@1 7/61; Hit@5 14/61; MRR 0.200.
- Next: Run the next Phase B0 representation pre-screen.

## 2026-07-15T19:15:27+00:00 — phase_b_b0_page_two_relevant_windows

- Decision: **investigate** — B0 finalist: accepted evidence remains visible for 49/61 questions with 1671 average characters.
- Evidence: candidate recall 61/61; Hit@1 7/61; Hit@5 14/61; MRR 0.200.
- Next: Run the next Phase B0 representation pre-screen.

## 2026-07-15T19:15:27+00:00 — phase_b_b0_page_leading_text

- Decision: **investigate** — B0 finalist: accepted evidence remains visible for 49/61 questions with 1709 average characters.
- Evidence: candidate recall 61/61; Hit@1 7/61; Hit@5 14/61; MRR 0.200.
- Next: Run the next Phase B0 representation pre-screen.

## 2026-07-15T19:15:28+00:00 — phase_b_b0_page_relevant_window

- Decision: **investigate** — B0 finalist: accepted evidence remains visible for 48/61 questions with 1576 average characters.
- Evidence: candidate recall 61/61; Hit@1 7/61; Hit@5 14/61; MRR 0.198.
- Next: Run the next Phase B0 representation pre-screen.

## 2026-07-15T19:15:29+00:00 — phase_b_b0_page_heading_relevant_window

- Decision: **reject** — Dominated in deterministic B0 visibility/length screening: 48/61 visible.
- Evidence: candidate recall 61/61; Hit@1 7/61; Hit@5 14/61; MRR 0.198.
- Next: Run the next Phase B0 representation pre-screen.

## 2026-07-15T19:15:29+00:00 — phase_b_b0_page_full_page_when_fits

- Decision: **reject** — Dominated in deterministic B0 visibility/length screening: 48/61 visible.
- Evidence: candidate recall 61/61; Hit@1 7/61; Hit@5 14/61; MRR 0.199.
- Next: Run the next Phase B0 representation pre-screen.

## 2026-07-15T19:15:30+00:00 — phase_b_b0_page_relevant_paragraph

- Decision: **reject** — Dominated in deterministic B0 visibility/length screening: 47/61 visible.
- Evidence: candidate recall 61/61; Hit@1 7/61; Hit@5 16/61; MRR 0.210.
- Next: Rerank the retained page representations, then the retained chunk representations.

## 2026-07-15T19:19:15+00:00 — phase_b_b1_member_dense_best_member

- Decision: **investigate** — B1 finalist: accepted evidence visible for 58/61 with 1831 average characters.
- Evidence: candidate recall 61/61; Hit@1 13/61; Hit@5 25/61; MRR 0.331.
- Next: Run the next Phase B1 member policy.

## 2026-07-15T19:19:17+00:00 — phase_b_b1_member_lexical_dense_fused_member

- Decision: **investigate** — B1 finalist: accepted evidence visible for 57/61 with 1854 average characters.
- Evidence: candidate recall 61/61; Hit@1 14/61; Hit@5 24/61; MRR 0.338.
- Next: Run the next Phase B1 member policy.

## 2026-07-15T19:19:19+00:00 — phase_b_b1_member_lexical_best_member

- Decision: **reject** — Dominated member-selection pre-screen: 56/61 visible.
- Evidence: candidate recall 61/61; Hit@1 12/61; Hit@5 24/61; MRR 0.316.
- Next: Run the next Phase B1 member policy.

## 2026-07-15T19:19:22+00:00 — phase_b_b1_member_all_fused_member_windows

- Decision: **reject** — Dominated member-selection pre-screen: 52/61 visible.
- Evidence: candidate recall 61/61; Hit@1 10/61; Hit@5 18/61; MRR 0.259.
- Next: Run the next Phase B1 member policy.

## 2026-07-15T19:19:24+00:00 — phase_b_b1_member_top_two_fused_members

- Decision: **reject** — Dominated member-selection pre-screen: 51/61 visible.
- Evidence: candidate recall 61/61; Hit@1 10/61; Hit@5 18/61; MRR 0.257.
- Next: Run the next Phase B1 member policy.

## 2026-07-15T19:19:25+00:00 — phase_b_b1_member_shortest_member

- Decision: **investigate** — B1 finalist: accepted evidence visible for 49/61 with 1709 average characters.
- Evidence: candidate recall 61/61; Hit@1 7/61; Hit@5 14/61; MRR 0.200.
- Next: Resolve any remaining representation-evidence losses before cross-encoder scoring.

## 2026-07-15T19:20:46+00:00 — phase_b_b2_combination_dense_best_member_two_relevant_windows_neighbor_expansion

- Decision: **investigate** — B2 finalist: 60/61 accepted evidence visibility at 1839 average characters.
- Evidence: candidate recall 61/61; Hit@1 14/61; Hit@5 27/61; MRR 0.351.
- Next: Run the next Phase B2 combination.

## 2026-07-15T19:20:47+00:00 — phase_b_b2_combination_dense_best_member_leading_text_neighbor_expansion

- Decision: **investigate** — B2 finalist: 60/61 accepted evidence visibility at 1887 average characters.
- Evidence: candidate recall 61/61; Hit@1 14/61; Hit@5 27/61; MRR 0.351.
- Next: Run the next Phase B2 combination.

## 2026-07-15T19:20:48+00:00 — phase_b_b2_combination_dense_best_member_relevant_window_neighbor_expansion

- Decision: **investigate** — B2 finalist: 58/61 accepted evidence visibility at 1736 average characters.
- Evidence: candidate recall 61/61; Hit@1 14/61; Hit@5 26/61; MRR 0.341.
- Next: Run the next Phase B2 combination.

## 2026-07-15T19:20:49+00:00 — phase_b_b2_combination_dense_best_member_full_page_when_fits_neighbor_expansion

- Decision: **reject** — Dominated retained-policy combination: 58/61 visible.
- Evidence: candidate recall 61/61; Hit@1 14/61; Hit@5 26/61; MRR 0.341.
- Next: Run the next Phase B2 combination.

## 2026-07-15T19:20:51+00:00 — phase_b_b2_combination_lexical_dense_fused_member_two_relevant_windows_neighbor_expansion

- Decision: **reject** — Dominated retained-policy combination: 57/61 visible.
- Evidence: candidate recall 61/61; Hit@1 14/61; Hit@5 24/61; MRR 0.338.
- Next: Use a lossless representation for cross-encoder scoring only if visibility reaches 61/61.

## 2026-07-15T19:22:52+00:00 — phase_b_b3_combination_dense_best_member_two_relevant_windows_balanced_neighbor_expansion

- Decision: **investigate** — B3 finalist: 54/61 accepted evidence visibility at 1520 average characters.
- Evidence: candidate recall 61/61; Hit@1 10/61; Hit@5 21/61; MRR 0.277.
- Next: Run the next Phase B3 combination.

## 2026-07-15T19:22:55+00:00 — phase_b_b3_combination_dense_best_member_leading_text_balanced_neighbor_expansion

- Decision: **investigate** — B3 finalist: 54/61 accepted evidence visibility at 1567 average characters.
- Evidence: candidate recall 61/61; Hit@1 10/61; Hit@5 21/61; MRR 0.278.
- Next: Run the next Phase B3 combination.

## 2026-07-15T19:22:59+00:00 — phase_b_b3_combination_lexical_dense_fused_member_two_relevant_windows_balanced_neighbor_expansion

- Decision: **investigate** — B3 finalist: 52/61 accepted evidence visibility at 1523 average characters.
- Evidence: candidate recall 61/61; Hit@1 9/61; Hit@5 20/61; MRR 0.259.
- Next: Use a lossless representation for cross-encoder scoring only if visibility reaches 61/61.

## 2026-07-15T19:52:19+00:00 — phase_b_b4_rerank_combination_shortest_member_leading_text_chapter_section_chunk

- Decision: **investigate** — Historical shortest-member representation control over the lossless Phase A pool.
- Evidence: candidate recall 61/61; Hit@1 13/61; Hit@5 31/61; MRR 0.372.
- Next: Run the next retained Phase B representation through the cached cross-encoder.

## 2026-07-15T20:22:57+00:00 — phase_b_b4_rerank_combination_dense_best_member_leading_text_chapter_section_chunk

- Decision: **investigate** — Representation challenger; final retain/reject decision follows measured full-set metrics.
- Evidence: candidate recall 61/61; Hit@1 17/61; Hit@5 35/61; MRR 0.409.
- Next: Run the next retained Phase B representation through the cached cross-encoder.

## 2026-07-15T20:52:34+00:00 — phase_b_b4_rerank_combination_dense_best_member_leading_text_neighbor_expansion

- Decision: **investigate** — Representation challenger; final retain/reject decision follows measured full-set metrics.
- Evidence: candidate recall 61/61; Hit@1 16/61; Hit@5 37/61; MRR 0.408.
- Next: Run the next retained Phase B representation through the cached cross-encoder.

## 2026-07-15T21:32:54+00:00 — phase_b_b4_rerank_combination_dense_best_member_two_relevant_windows_neighbor_expansion

- Decision: **investigate** — Representation challenger; final retain/reject decision follows measured full-set metrics.
- Evidence: candidate recall 61/61; Hit@1 16/61; Hit@5 40/61; MRR 0.422.
- Next: Select the Phase B quality/latency winner and begin Phase C fusion logic.

## 2026-07-15T21:46:47+00:00 — phase_c_c1_soft_fusion_no_reranker_full_pool

- Decision: **retain** — Full-pool quality/latency Pareto configuration.
- Evidence: candidate recall 61/61; Hit@1 26/61; Hit@5 47/61; MRR 0.557.
- Next: Run remaining Phase C fusion and candidate-budget gates.

## 2026-07-15T21:46:47+00:00 — phase_c_c1_plain_rrf_full_pool

- Decision: **reject** — Dominated or not selected under natural-first quality and CPU latency priorities.
- Evidence: candidate recall 61/61; Hit@1 15/61; Hit@5 29/61; MRR 0.373.
- Next: Run remaining Phase C fusion and candidate-budget gates.

## 2026-07-15T21:46:47+00:00 — phase_c_c1_weighted_rrf_full_pool

- Decision: **reject** — Dominated or not selected under natural-first quality and CPU latency priorities.
- Evidence: candidate recall 61/61; Hit@1 16/61; Hit@5 29/61; MRR 0.379.
- Next: Run remaining Phase C fusion and candidate-budget gates.

## 2026-07-15T21:46:47+00:00 — phase_c_c1_bge_reranker_score_full_pool

- Decision: **reject** — Dominated or not selected under natural-first quality and CPU latency priorities.
- Evidence: candidate recall 61/61; Hit@1 16/61; Hit@5 40/61; MRR 0.422.
- Next: Run remaining Phase C fusion and candidate-budget gates.

## 2026-07-15T21:46:48+00:00 — phase_c_c1_bge_rank_plus_rrf_rank_full_pool

- Decision: **retain** — Full-pool quality/latency Pareto configuration.
- Evidence: candidate recall 61/61; Hit@1 16/61; Hit@5 41/61; MRR 0.432.
- Next: Run remaining Phase C fusion and candidate-budget gates.

## 2026-07-15T21:46:48+00:00 — phase_c_c1_bge_score_plus_normalized_rrf_full_pool

- Decision: **reject** — Dominated or not selected under natural-first quality and CPU latency priorities.
- Evidence: candidate recall 61/61; Hit@1 14/61; Hit@5 28/61; MRR 0.366.
- Next: Run remaining Phase C fusion and candidate-budget gates.

## 2026-07-15T21:46:48+00:00 — phase_c_c1_bge_rank_plus_soft_fusion_rank_full_pool

- Decision: **reject** — Dominated or not selected under natural-first quality and CPU latency priorities.
- Evidence: candidate recall 61/61; Hit@1 20/61; Hit@5 44/61; MRR 0.484.
- Next: Run remaining Phase C fusion and candidate-budget gates.

## 2026-07-15T21:46:48+00:00 — phase_c_c2_rrf_preselector_budget_8

- Decision: **reject** — Invalid before reranking: capped gold-blind pool loses accepted evidence.
- Evidence: candidate recall 38/61; Hit@1 15/61; Hit@5 29/61; MRR 0.344.
- Next: Finish Phase C budget gates; do not rerank any pool that loses evidence.

## 2026-07-15T21:46:48+00:00 — phase_c_c2_rrf_preselector_budget_10

- Decision: **reject** — Invalid before reranking: capped gold-blind pool loses accepted evidence.
- Evidence: candidate recall 45/61; Hit@1 15/61; Hit@5 29/61; MRR 0.356.
- Next: Finish Phase C budget gates; do not rerank any pool that loses evidence.

## 2026-07-15T21:46:48+00:00 — phase_c_c2_rrf_preselector_budget_15

- Decision: **reject** — Invalid before reranking: capped gold-blind pool loses accepted evidence.
- Evidence: candidate recall 54/61; Hit@1 15/61; Hit@5 29/61; MRR 0.368.
- Next: Finish Phase C budget gates; do not rerank any pool that loses evidence.

## 2026-07-15T21:46:49+00:00 — phase_c_c2_bm25_fast_reranker_budget_8

- Decision: **reject** — Invalid before reranking: capped gold-blind pool loses accepted evidence.
- Evidence: candidate recall 42/61; Hit@1 8/61; Hit@5 36/61; MRR 0.301.
- Next: Finish Phase C budget gates; do not rerank any pool that loses evidence.

## 2026-07-15T21:46:50+00:00 — phase_c_c2_bm25_fast_reranker_budget_10

- Decision: **reject** — Invalid before reranking: capped gold-blind pool loses accepted evidence.
- Evidence: candidate recall 46/61; Hit@1 8/61; Hit@5 36/61; MRR 0.308.
- Next: Finish Phase C budget gates; do not rerank any pool that loses evidence.

## 2026-07-15T21:46:50+00:00 — phase_c_c2_bm25_fast_reranker_budget_15

- Decision: **reject** — Invalid before reranking: capped gold-blind pool loses accepted evidence.
- Evidence: candidate recall 50/61; Hit@1 8/61; Hit@5 36/61; MRR 0.313.
- Next: Finish Phase C budget gates; do not rerank any pool that loses evidence.

## 2026-07-15T22:02:40+00:00 — phase_d_d1_minilm_l6_full_pool

- Decision: **retain** — Speed-oriented Pareto candidate versus cached BGE-base quality control.
- Evidence: candidate recall 61/61; Hit@1 14/61; Hit@5 43/61; MRR 0.421.
- Next: Compare MiniLM with cached BGE-base and apply the Phase D successive-stopping rule.

## 2026-07-15T22:29:40+00:00 — phase_d_d3_bge_v2_m3_full_pool_screen_8

- Decision: **investigate** — Stratified latency/quality screen; full-set decision is intentionally deferred.
- Evidence: candidate recall 8/8; Hit@1 2/8; Hit@5 5/8; MRR 0.397.
- Next: Review the BGE-v2-m3 stratified screen and run the full set only if quality justifies its CPU cost.

## 2026-07-15T22:30:16+00:00 — BGE-v2-m3 stopping decision

- Decision: **reject full run** — The stratified quality signal does not justify the measured CPU cost.
- Evidence: natural-student Hit@1/3/5 was 1/4 on the balanced screen; average latency was 115.1 s/query, p95 was 154.4 s, and peak memory was 2,816.9 MiB.
- Next: Inspect `mixedbread-ai/mxbai-rerank-base-v1` and screen it only if its local size/runtime are feasible.
## 2026-07-15T22:42:05+00:00 — phase_d_d4_mxbai_base_v1_full_pool_screen_8

- Decision: **reject** — Runtime infeasible: no full-pool query completed after more than five minutes.
- Evidence: candidate recall 0/0; Hit@1 0/0; Hit@5 0/0; MRR 0.000.
- Next: Finalize Phase D with MiniLM as the retained speed reranker and no larger full run.

## Phase D final selection — MiniLM L6

- Decision: **retain MiniLM L6** as both speed- and practical quality-oriented reranker; keep Soft-fusion-ranked retrieval as the balanced no-reranker path.
- Evidence: MiniLM natural Hit@1/3/5 is 6/13/16 of 20 at 8.1 s p95; BGE-base is 5/12/15 at 47.0 s p95. BGE-v2 natural Hit@5 was 1/4 at 154.4 s screen p95; mxbai completed no query after >300 s.
- Next: Begin Phase E with BGE-M3 dense retrieval, then narrow before sparse/multi-vector variants.

## 2026-07-15T23:03:18+00:00 — phase_e_e0_bge_small_fixed_400_80_control

- Decision: **retain** — Refreshed normalized BGE-small control on the corrected corpus.
- Evidence: candidate recall 61/61; Hit@1 15/61; Hit@5 42/61; MRR 0.442.
- Next: Run BGE-M3 dense on the identical fixed corpus.

## 2026-07-15T23:45:04+00:00 — phase_e_e1_bge_m3_dense_fixed_400_80

- Decision: **investigate** — BGE-M3 dense completed; compare quality and runtime with the refreshed control.
- Evidence: candidate recall 61/61; Hit@1 16/61; Hit@5 42/61; MRR 0.447.
- Next: Apply the Phase E successive-stopping gate before testing sparse or larger embeddings.

## 2026-07-16T00:14:29+00:00 — phase_e_e2_bge_m3_sparse_and_fusion_fixed_400_80

- Decision: **investigate** — Sparse and fusion modes completed; apply the natural-quality/runtime gate.
- Evidence: candidate recall 61/61; Hit@1 17/61; Hit@5 42/61; MRR 0.464.
- Next: Apply the BGE-M3 specialty stopping gate, then acquire the approved Nomic revision if justified.

## Phase E BGE-M3 successive-stopping gate

- Retain BGE-small hybrid as the balanced control.
- Retain BGE-M3 dense+sparse+BM25 only on the overall-quality frontier: 15/39/44 overall and 3/10/13 natural at p95 719 ms.
- Reject BGE-M3 dense/sparse as balanced choices and stop multi-vector: natural quality does not improve and latency rises materially.
- Next: acquire and test the approved Nomic embedding.

## 2026-07-16T00:38:19+00:00 — phase_e_e3_nomic_embed_v1_5_full_fixed_400_80

- Decision: **investigate** — nomic-ai/nomic-embed-text-v1.5 completed; compare quality and runtime with retained controls.
- Evidence: candidate recall 61/61; Hit@1 16/61; Hit@5 43/61; MRR 0.460.
- Next: Run Nomic at 512 dimensions by deriving and renormalizing the cached full vectors.

## 2026-07-16T00:40:02+00:00 — phase_e_e4_nomic_embed_v1_5_512_fixed_400_80

- Decision: **investigate** — nomic-ai/nomic-embed-text-v1.5 completed; compare quality and runtime with retained controls.
- Evidence: candidate recall 61/61; Hit@1 16/61; Hit@5 42/61; MRR 0.458.
- Next: Apply the Nomic stopping gate, then acquire the approved e5-large-v2 revision if justified.

## 2026-07-16T01:07:48+00:00 — phase_e_e5_e5_large_v2_fixed_400_80

- Decision: **investigate** — intfloat/e5-large-v2 completed; compare quality and runtime with retained controls.
- Evidence: candidate recall 61/61; Hit@1 22/61; Hit@5 46/61; MRR 0.524.
- Next: Finalize the Phase E Pareto gate and advance only the best two embeddings to Phase F.

## Phase E final embedding selection

- Retain BGE-small hybrid as lightweight/balanced: 15/34/42 overall, 4/9/13 natural, p95 53 ms.
- Retain E5-large-v2 as quality embedding: dense 22/35/46 with MRR 0.524; hybrid 21/37/49 and 3/10/16 natural, p95 about 461 ms.
- Reject Nomic full/512 and BGE-M3 from Phase F; neither earns one of the two embedding slots on quality, natural performance, and runtime together.
- Next: Phase F chunking search with E5 first, then BGE-small confirmation.

## 2026-07-16T01:11:10+00:00 — phase_f_f0_bm25_fixed_300_50

- Decision: **investigate** — BM25 screen completed; select finalists only after all corpus rankings exist.
- Evidence: candidate recall 61/61; Hit@1 14/61; Hit@5 38/61; MRR 0.382.
- Next: Complete all Phase F BM25 corpus screens.

## 2026-07-16T01:11:11+00:00 — phase_f_f0_bm25_fixed_400_80

- Decision: **investigate** — BM25 screen completed; select finalists only after all corpus rankings exist.
- Evidence: candidate recall 61/61; Hit@1 17/61; Hit@5 41/61; MRR 0.450.
- Next: Complete all Phase F BM25 corpus screens.

## 2026-07-16T01:11:12+00:00 — phase_f_f0_bm25_fixed_600_100

- Decision: **investigate** — BM25 screen completed; select finalists only after all corpus rankings exist.
- Evidence: candidate recall 61/61; Hit@1 20/61; Hit@5 45/61; MRR 0.509.
- Next: Complete all Phase F BM25 corpus screens.

## 2026-07-16T01:11:13+00:00 — phase_f_f0_bm25_fixed_400_80_headings

- Decision: **investigate** — BM25 screen completed; select finalists only after all corpus rankings exist.
- Evidence: candidate recall 61/61; Hit@1 17/61; Hit@5 42/61; MRR 0.455.
- Next: Complete all Phase F BM25 corpus screens.

## 2026-07-16T01:11:14+00:00 — phase_f_f0_bm25_paragraph_groups

- Decision: **investigate** — BM25 screen completed; select finalists only after all corpus rankings exist.
- Evidence: candidate recall 61/61; Hit@1 13/61; Hit@5 37/61; MRR 0.366.
- Next: Complete all Phase F BM25 corpus screens.

## 2026-07-16T01:11:15+00:00 — phase_f_f0_bm25_section_aware

- Decision: **investigate** — BM25 screen completed; select finalists only after all corpus rankings exist.
- Evidence: candidate recall 61/61; Hit@1 11/61; Hit@5 37/61; MRR 0.362.
- Next: Complete all Phase F BM25 corpus screens.

## 2026-07-16T01:23:30+00:00 — phase_f_f1_e5_fixed_600_100

- Decision: **investigate** — E5 finalist completed; select the chunk winner after every finalist run.
- Evidence: candidate recall 61/61; Hit@1 19/61; Hit@5 43/61; MRR 0.490.
- Next: Complete all retained E5 chunking finalists.

## 2026-07-16T01:48:10+00:00 — phase_f_f1_e5_paragraph_groups

- Decision: **investigate** — E5 finalist completed; select the chunk winner after every finalist run.
- Evidence: candidate recall 61/61; Hit@1 17/61; Hit@5 41/61; MRR 0.445.
- Next: Complete all retained E5 chunking finalists.

## 2026-07-16T01:48:32+00:00 — phase_f_f1_e5_fixed_400_80

- Decision: **investigate** — E5 finalist completed; select the chunk winner after every finalist run.
- Evidence: candidate recall 61/61; Hit@1 22/61; Hit@5 46/61; MRR 0.524.
- Next: Complete all retained E5 chunking finalists.

## 2026-07-16T02:46:02+00:00 — phase_f_f2_parent_page_child

- Decision: **reject** — Candidate recall fell to 60/61; the method violates the evidence-preservation invariant.
- Evidence: candidate recall 60/61; Hit@1 19/61; Hit@5 43/61; MRR 0.490.
- Next: Complete all approved Phase F multi-granularity methods.

## 2026-07-16T02:46:02+00:00 — phase_f_f2_page_prior_rrf

- Decision: **retain** — Improved the preregistered natural-student-first quality ordering without losing evidence.
- Evidence: candidate recall 61/61; Hit@1 18/61; Hit@5 48/61; MRR 0.518.
- Next: Complete all approved Phase F multi-granularity methods.

## 2026-07-16T02:46:02+00:00 — phase_f_f2_neighbor_expansion

- Decision: **retain** — Improved the preregistered natural-student-first quality ordering without losing evidence.
- Evidence: candidate recall 61/61; Hit@1 19/61; Hit@5 49/61; MRR 0.490.
- Next: Complete all approved Phase F multi-granularity methods.

## 2026-07-16T02:46:02+00:00 — phase_f_f2_query_relevant_windows

- Decision: **reject** — Candidate recall fell to 56/61; the method violates the evidence-preservation invariant.
- Evidence: candidate recall 56/61; Hit@1 14/61; Hit@5 42/61; MRR 0.409.
- Next: Complete all approved Phase F multi-granularity methods.

## 2026-07-16T02:54:36+00:00 — phase_f_f3_bge_small_fixed_600_100

- Decision: **retain** — Fixed 600/100 transfers the natural-student-first gain to BGE-small.
- Evidence: candidate recall 61/61; Hit@1 20/61; Hit@5 45/61; MRR 0.514.
- Next: Complete the BGE-small Phase F confirmation.

## 2026-07-16T02:54:36+00:00 — phase_f_f4_bge_small_page_prior_rrf

- Decision: **reject** — The page prior does not transfer a quality gain to BGE-small.
- Evidence: candidate recall 61/61; Hit@1 24/61; Hit@5 48/61; MRR 0.558.
- Next: Complete the BGE-small Phase F confirmation.

## 2026-07-16T03:02:22+00:00 — phase_g_g0_raw

- Decision: **retain** — Reproduces the retained Phase F balanced control.
- Evidence: candidate recall 61/61; Hit@1 20/61; Hit@5 45/61; MRR 0.514.
- Next: Continue the approved deterministic Phase G screen.

## 2026-07-16T03:02:27+00:00 — phase_g_g0_spelling_normalization

- Decision: **reject** — No benchmark query activated this conservative processor.
- Evidence: candidate recall 61/61; Hit@1 20/61; Hit@5 45/61; MRR 0.514.
- Next: Continue the approved deterministic Phase G screen.

## 2026-07-16T03:02:31+00:00 — phase_g_g0_grammar_cleanup

- Decision: **retain** — Improved the natural-student-first ordering without material canonical regression.
- Evidence: candidate recall 61/61; Hit@1 20/61; Hit@5 45/61; MRR 0.514.
- Next: Continue the approved deterministic Phase G screen.

## 2026-07-16T03:02:36+00:00 — phase_g_g0_textbook_synonym_expansion

- Decision: **retain** — Improved the natural-student-first ordering without material canonical regression.
- Evidence: candidate recall 61/61; Hit@1 21/61; Hit@5 50/61; MRR 0.551.
- Next: Continue the approved deterministic Phase G screen.

## 2026-07-16T03:02:40+00:00 — phase_g_g0_acronym_expansion

- Decision: **retain** — Improved the natural-student-first ordering without material canonical regression.
- Evidence: candidate recall 61/61; Hit@1 21/61; Hit@5 45/61; MRR 0.522.
- Next: Continue the approved deterministic Phase G screen.

## 2026-07-16T03:02:44+00:00 — phase_g_g0_formula_symbol_normalization

- Decision: **retain** — Improved the natural-student-first ordering without material canonical regression.
- Evidence: candidate recall 61/61; Hit@1 22/61; Hit@5 47/61; MRR 0.530.
- Next: Continue the approved deterministic Phase G screen.

## 2026-07-16T03:04:26+00:00 — phase_g_g1_original_plus_textbook_synonym_expansion

- Decision: **retain** — Original-plus-expanded fusion improved natural-first quality.
- Evidence: candidate recall 61/61; Hit@1 20/61; Hit@5 48/61; MRR 0.528.
- Next: Continue the approved deterministic Phase G screen.

## 2026-07-16T03:04:33+00:00 — phase_g_g1_original_plus_formula_symbol_normalization

- Decision: **retain** — Original-plus-expanded fusion improved natural-first quality.
- Evidence: candidate recall 61/61; Hit@1 22/61; Hit@5 45/61; MRR 0.524.
- Next: Continue the approved deterministic Phase G screen.

## 2026-07-16T03:24:10+00:00 — phase_h_h0_formula_equation_lines

- Decision: **reject** — Did not win and improve the formula target slice safely.
- Evidence: candidate recall 61/61; Hit@1 21/61; Hit@5 47/61; MRR 0.536.
- Next: Complete the deterministic Phase H specialist screen.

## 2026-07-16T03:24:11+00:00 — phase_h_h0_formula_equation_context

- Decision: **retain** — Best formula representation improved its target slice without material global regression.
- Evidence: candidate recall 61/61; Hit@1 24/61; Hit@5 49/61; MRR 0.569.
- Next: Complete the deterministic Phase H specialist screen.

## 2026-07-16T03:24:11+00:00 — phase_h_h0_table_flattened

- Decision: **reject** — Did not win and improve the table target slice safely.
- Evidence: candidate recall 61/61; Hit@1 23/61; Hit@5 50/61; MRR 0.563.
- Next: Complete the deterministic Phase H specialist screen.

## 2026-07-16T03:24:11+00:00 — phase_h_h0_table_rows_with_headers

- Decision: **retain** — Best table representation improved its target slice without material global regression.
- Evidence: candidate recall 61/61; Hit@1 23/61; Hit@5 50/61; MRR 0.567.
- Next: Complete the deterministic Phase H specialist screen.

## 2026-07-16T03:24:11+00:00 — phase_h_h0_table_key_value

- Decision: **reject** — Did not win and improve the table target slice safely.
- Evidence: candidate recall 61/61; Hit@1 23/61; Hit@5 50/61; MRR 0.565.
- Next: Complete the deterministic Phase H specialist screen.

## 2026-07-16T03:24:11+00:00 — phase_h_h0_visual_caption_context

- Decision: **retain** — Best visual representation improved its target slice without material global regression.
- Evidence: candidate recall 61/61; Hit@1 23/61; Hit@5 50/61; MRR 0.572.
- Next: Complete the deterministic Phase H specialist screen.

## 2026-07-16T03:29:39+00:00 — phase_h_h1_formula_context_activation_v2

- Decision: **retain** — V2 formula activation preserved a target gain with fewer false activations.
- Evidence: candidate recall 61/61; Hit@1 23/61; Hit@5 50/61; MRR 0.572.
- Next: Complete the deterministic Phase H specialist screen.

## 2026-07-16T03:29:45+00:00 — phase_h_h1_table_rows_activation_v2

- Decision: **retain** — V2 table activation preserved a target gain with fewer false activations.
- Evidence: candidate recall 61/61; Hit@1 22/61; Hit@5 50/61; MRR 0.559.
- Next: Complete the deterministic Phase H specialist screen.

## 2026-07-16T03:31:39+00:00 — phase_h_h2_formula_context_activation_v3

- Decision: **reject** — Plural-law support did not improve target quality despite activation coverage.
- Evidence: candidate recall 61/61; Hit@1 22/61; Hit@5 50/61; MRR 0.563.
- Next: Complete the deterministic Phase H specialist screen.

## 2026-07-16T03:37:40+00:00 — phase_h_h3_combined_specialist_priors

- Decision: **retain** — Combined retained priors improved natural-first quality without material canonical regression.
- Evidence: candidate recall 61/61; Hit@1 26/61; Hit@5 50/61; MRR 0.601.
- Next: Evaluate distributed evidence-set construction.

## 2026-07-16T03:41:07+00:00 — phase_h_h4_base_top5

- Decision: **retain** — Control evidence set retained for latency and completeness comparison.
- Evidence: candidate recall 61/61; Hit@1 26/61; Hit@5 50/61; MRR 0.584.
- Next: Select the distributed evidence winner and advance to Phase I.

## 2026-07-16T03:41:07+00:00 — phase_h_h4_neighbor_expansion

- Decision: **reject** — Did not enter the top-two distributed evidence frontier over base top-5.
- Evidence: candidate recall 61/61; Hit@1 26/61; Hit@5 48/61; MRR 0.534.
- Next: Select the distributed evidence winner and advance to Phase I.

## 2026-07-16T03:41:07+00:00 — phase_h_h4_same_page_expansion

- Decision: **reject** — Did not enter the top-two distributed evidence frontier over base top-5.
- Evidence: candidate recall 61/61; Hit@1 26/61; Hit@5 47/61; MRR 0.536.
- Next: Select the distributed evidence winner and advance to Phase I.

## 2026-07-16T03:41:07+00:00 — phase_h_h4_same_section_expansion

- Decision: **reject** — Did not enter the top-two distributed evidence frontier over base top-5.
- Evidence: candidate recall 61/61; Hit@1 26/61; Hit@5 47/61; MRR 0.564.
- Next: Select the distributed evidence winner and advance to Phase I.

## 2026-07-16T03:41:08+00:00 — phase_h_h4_coverage_diversity

- Decision: **retain** — Top-two distributed selector improved multi-page completeness/coverage over base top-5.
- Evidence: candidate recall 61/61; Hit@1 26/61; Hit@5 46/61; MRR 0.570.
- Next: Select the distributed evidence winner and advance to Phase I.

## 2026-07-16T03:41:08+00:00 — phase_h_h4_multi_stage_distinct_pages

- Decision: **reject** — Did not enter the top-two distributed evidence frontier over base top-5.
- Evidence: candidate recall 61/61; Hit@1 26/61; Hit@5 50/61; MRR 0.584.
- Next: Select the distributed evidence winner and advance to Phase I.

## 2026-07-16T03:49:09+00:00 — phase_i_i0_top5_relevance

- Decision: **reject** — Did not beat the evidence-preservation and context-size frontier.
- Evidence: inherited candidate recall 50/61; direct evidence 50/61; exact span 50/61; average context 3000 tokens.
- Next: Apply the Phase J generation-benchmark gate.

## 2026-07-16T03:49:09+00:00 — phase_i_i0_token_budget_1200

- Decision: **reject** — Did not beat the evidence-preservation and context-size frontier.
- Evidence: inherited candidate recall 50/61; direct evidence 40/61; exact span 40/61; average context 1200 tokens.
- Next: Apply the Phase J generation-benchmark gate.

## 2026-07-16T03:49:10+00:00 — phase_i_i0_token_budget_1800

- Decision: **reject** — Did not beat the evidence-preservation and context-size frontier.
- Evidence: inherited candidate recall 50/61; direct evidence 44/61; exact span 44/61; average context 1800 tokens.
- Next: Apply the Phase J generation-benchmark gate.

## 2026-07-16T03:49:10+00:00 — phase_i_i0_token_budget_2400

- Decision: **reject** — Did not beat the evidence-preservation and context-size frontier.
- Evidence: inherited candidate recall 50/61; direct evidence 49/61; exact span 49/61; average context 2400 tokens.
- Next: Apply the Phase J generation-benchmark gate.

## 2026-07-16T03:49:10+00:00 — phase_i_i0_overlap_merge

- Decision: **retain** — Best evidence-preserving context under the ordered Phase I gate.
- Evidence: inherited candidate recall 50/61; direct evidence 50/61; exact span 50/61; average context 2965 tokens.
- Next: Apply the Phase J generation-benchmark gate.

## 2026-07-16T03:49:10+00:00 — phase_i_i0_same_page_merge

- Decision: **reject** — Did not beat the evidence-preservation and context-size frontier.
- Evidence: inherited candidate recall 50/61; direct evidence 50/61; exact span 50/61; average context 2965 tokens.
- Next: Apply the Phase J generation-benchmark gate.

## 2026-07-16T03:49:10+00:00 — phase_i_i0_redundancy_removal

- Decision: **reject** — Did not beat the evidence-preservation and context-size frontier.
- Evidence: inherited candidate recall 50/61; direct evidence 50/61; exact span 50/61; average context 3000 tokens.
- Next: Apply the Phase J generation-benchmark gate.

## 2026-07-16T03:49:11+00:00 — phase_i_i0_diversity_selection

- Decision: **reject** — Did not beat the evidence-preservation and context-size frontier.
- Evidence: inherited candidate recall 50/61; direct evidence 44/61; exact span 44/61; average context 1813 tokens.
- Next: Apply the Phase J generation-benchmark gate.

## 2026-07-16T03:49:11+00:00 — phase_i_i0_textbook_order

- Decision: **reject** — Did not beat the evidence-preservation and context-size frontier.
- Evidence: inherited candidate recall 50/61; direct evidence 50/61; exact span 50/61; average context 3000 tokens.
- Next: Apply the Phase J generation-benchmark gate.

## 2026-07-16T03:49:11+00:00 — phase_i_i0_direct_support_grouping

- Decision: **reject** — Did not beat the evidence-preservation and context-size frontier.
- Evidence: inherited candidate recall 50/61; direct evidence 50/61; exact span 50/61; average context 3000 tokens.
- Next: Apply the Phase J generation-benchmark gate.

## 2026-07-16 — Phase H final preservation gate

- Decision: **retain `phase_h_h4_base_top5` only** — the provisional coverage-diversity retain is superseded for production selection.
- Evidence: base top-5 preserves 50/61 direct hits versus 46/61 for coverage diversity; the latter adds one multi-page-complete case but loses four direct hits.
- Next: Use base top-5 as the fixed Phase I candidate pool.

## 2026-07-16T03:47:57+00:00 — phase_i_i0_top3_relevance (journal recovery)

- Decision: **reject** — Did not beat the evidence-preservation and context-size frontier.
- Evidence: inherited candidate recall 50/61; direct evidence 44/61; exact span 44/61; average context 1813 tokens.
- Next: Apply the Phase J generation-benchmark gate. The run record and artifacts were checkpointed before the original journal append exposed the now-fixed context-metric schema branch.

## 2026-07-16 — Final architecture selection

- Decision: **retain combined specialists for best quality and balanced production; retain fixed-600/100 BM25 for lightweight CPU**.
- Evidence: combined specialists reach 26/44/50 H@1/3/5, 0.601 MRR, and 16/20 natural Hit@5 at 71.2 ms p95/688 MB; BM25 reaches 20/38/45 and 12/20 natural Hit@5 at 1.8 ms p95/132 MB.
- Next: keep Phase J gated until a reviewed answer-correctness, faithfulness, citation, and abstention benchmark is approved.

## 2026-07-16T04:11:30+00:00 — phase_i_i0_overlap_merge_metadata_preserving

- Decision: **retain** — Best evidence-preserving context under the ordered Phase I gate.
- Evidence: inherited candidate recall 50/61; direct evidence 50/61; exact span 50/61; average context 2965 tokens.
- Next: Apply the Phase J generation-benchmark gate.
