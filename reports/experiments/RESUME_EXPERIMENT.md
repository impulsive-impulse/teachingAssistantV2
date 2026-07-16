# Resume local RAG experiments

## Project objective

Discover the strongest practical, reproducible local textbook RAG pipeline.

## Fixed benchmark rules

- Use `data/benchmarks/retrieval_benchmark_v1.jsonl`: 66 rows, 61 answerable and 5 excluded negatives.
- Gold evidence is evaluation-only and historical baseline artifacts are immutable.
- Candidate compression must not discard accepted evidence available in source rankings.

## Current phase

Phase J — gated; approved retrieval loop complete

## Current best pipeline

{"phase_a": {"run_id": "phase_a_a4_uncompressed_union_t080", "pipeline_name": "uncompressed_union_t080", "candidate_budget": "all", "candidate_recall": "61/61", "pool_statistics": {"minimum": 31, "average": 40.833333333333336, "p50": 40.0, "p95": 51.75, "maximum": 57}}, "phase_b_prescreen_finalists": {"page": ["page_leading_text", "page_relevant_window", "page_two_relevant_windows"], "chunk": ["chunk_chapter_section_chunk", "chunk_neighbor_expansion", "chunk_raw_chunk"]}, "phase_b_member_finalists": ["member_dense_best_member", "member_lexical_dense_fused_member", "member_shortest_member"], "phase_b_combination_finalists": ["combination_dense_best_member_leading_text_neighbor_expansion", "combination_dense_best_member_relevant_window_neighbor_expansion", "combination_dense_best_member_two_relevant_windows_neighbor_expansion"], "phase_b_boundary_finalists": ["combination_dense_best_member_leading_text_balanced_neighbor_expansion", "combination_dense_best_member_two_relevant_windows_balanced_neighbor_expansion", "combination_lexical_dense_fused_member_two_relevant_windows_balanced_neighbor_expansion"], "phase_b": {"run_id": "phase_b_b4_rerank_combination_dense_best_member_two_relevant_windows_neighbor_expansion", "pipeline_name": "combination_dense_best_member_two_relevant_windows_neighbor_expansion", "metrics": {"overall": {"answerable_questions": 61, "hit_at_1_count": 16, "hit_at_1": 0.26229508196721313, "hit_at_3_count": 31, "hit_at_3": 0.5081967213114754, "hit_at_5_count": 40, "hit_at_5": 0.6557377049180327, "mrr": 0.4217621418217719, "average_latency_ms": 36689.31700909113, "p50_latency_ms": 36506.644100000354, "p95_latency_ms": 48287.10422499989, "maximum_latency_ms": 54816.637800000535}, "canonical": {"answerable_questions": 41, "hit_at_1_count": 12, "hit_at_1": 0.2926829268292683, "hit_at_3_count": 21, "hit_at_3": 0.5121951219512195, "hit_at_5_count": 25, "hit_at_5": 0.6097560975609756, "mrr": 0.4281488518961064, "average_latency_ms": 35580.27760000026, "p50_latency_ms": 34071.65619999887, "p95_latency_ms": 48492.73540000013, "maximum_latency_ms": 54816.637800000535}, "natural_student": {"answerable_questions": 20, "hit_at_1_count": 4, "hit_at_1": 0.2, "hit_at_3_count": 10, "hit_at_3": 0.5, "hit_at_5_count": 15, "hit_at_5": 0.75, "mrr": 0.40866938616938614, "average_latency_ms": 37770.96212000015, "p50_latency_ms": 38621.27500000088, "p95_latency_ms": 42287.04739499972, "maximum_latency_ms": 43195.98070000029}, "representation_evidence_recall": {"answerable_questions": 61, "count": 60, "recall": 0.9836065573770492, "missing_question_ids": ["BIO-032"]}}, "candidate_recall": "61/61"}, "phase_c": {"retained_run_ids": ["phase_c_c1_soft_fusion_no_reranker_full_pool", "phase_c_c1_bge_rank_plus_rrf_rank_full_pool"], "candidate_pool": "61/61 full Phase A union", "representation": "phase_b_b4_rerank_combination_dense_best_member_two_relevant_windows_neighbor_expansion"}, "phase_d": {"minilm_l6": {"run_id": "phase_d_d1_minilm_l6_full_pool", "decision": "retain", "selected_logic": "reranker_rank_plus_rrf_rank", "metrics": {"overall": {"answerable_questions": 61, "hit_at_1_count": 14, "hit_at_1": 0.22950819672131148, "hit_at_3_count": 33, "hit_at_3": 0.5409836065573771, "hit_at_5_count": 43, "hit_at_5": 0.7049180327868853, "mrr": 0.42054824461527707, "average_latency_ms": 5626.545395081878, "p50_latency_ms": 5453.341000000364, "p95_latency_ms": 8091.2974999992, "maximum_latency_ms": 9297.26589999882}, "canonical": {"answerable_questions": 41, "hit_at_1_count": 8, "hit_at_1": 0.1951219512195122, "hit_at_3_count": 20, "hit_at_3": 0.4878048780487805, "hit_at_5_count": 27, "hit_at_5": 0.6585365853658537, "mrr": 0.38971375684525206, "average_latency_ms": 5820.646163414539, "p50_latency_ms": 5548.841899999388, "p95_latency_ms": 8526.630000000296, "maximum_latency_ms": 9297.26589999882}, "natural_student": {"answerable_questions": 20, "hit_at_1_count": 6, "hit_at_1": 0.3, "hit_at_3_count": 13, "hit_at_3": 0.65, "hit_at_5_count": 16, "hit_at_5": 0.8, "mrr": 0.48375894454382823, "average_latency_ms": 5228.638819999924, "p50_latency_ms": 5305.6246499991175, "p95_latency_ms": 6103.362179999841, "maximum_latency_ms": 6786.035600000105}}}, "bge_v2_m3_screen_8": {"run_id": "phase_d_d3_bge_v2_m3_full_pool_screen_8", "decision": "reject", "selected_logic": "reranker_score", "metrics": {"overall": {"answerable_questions": 8, "hit_at_1_count": 2, "hit_at_1": 0.25, "hit_at_3_count": 4, "hit_at_3": 0.5, "hit_at_5_count": 5, "hit_at_5": 0.625, "mrr": 0.3970508658008658, "average_latency_ms": 115103.07672499993, "p50_latency_ms": 131597.9973000003, "p95_latency_ms": 154427.00411499955, "maximum_latency_ms": 157908.90109999964}, "canonical": {"answerable_questions": 4, "hit_at_1_count": 1, "hit_at_1": 0.25, "hit_at_3_count": 3, "hit_at_3": 0.75, "hit_at_5_count": 4, "hit_at_5": 1.0, "mrr": 0.47916666666666663, "average_latency_ms": 90675.01459999994, "p50_latency_ms": 72076.69344999976, "p95_latency_ms": 145673.58799999964, "maximum_latency_ms": 157908.90109999964}, "natural_student": {"answerable_questions": 4, "hit_at_1_count": 1, "hit_at_1": 0.25, "hit_at_3_count": 1, "hit_at_3": 0.25, "hit_at_5_count": 1, "hit_at_5": 0.25, "mrr": 0.31493506493506496, "average_latency_ms": 139531.13884999993, "p50_latency_ms": 146271.60660000026, "p95_latency_ms": 147811.7209199994, "maximum_latency_ms": 147960.62399999937}}}, "mxbai_base_v1_screen_8": {"run_id": "phase_d_d4_mxbai_base_v1_full_pool_screen_8", "decision": "reject", "status": "stopped_runtime_infeasible", "minimum_elapsed_before_stop_ms": 300000.0}, "selection": {"speed_oriented_reranker": "phase_d_d1_minilm_l6_full_pool", "quality_oriented_reranker": "phase_d_d1_minilm_l6_full_pool", "selected_logic": "reranker_rank_plus_rrf_rank", "reason": "MiniLM improves natural/top-5 quality over BGE-base at about one-sixth the p95 latency; larger models failed successive screens."}}, "phase_e_bge_gate": {"balanced_control": "phase_e_e0_bge_small_fixed_400_80_control", "quality_frontier": "phase_e_e2 dense_sparse_bm25_rrf variant", "rejected_balanced": ["phase_e_e1_bge_m3_dense_fixed_400_80", "phase_e_e2 sparse selected variant"], "stopped": ["BGE-M3 multi-vector/ColBERT escalation"], "reason": "Three-way BGE-M3 improves overall Hit@3/5 but loses one natural Hit@1 and is about 13x slower; dense and sparse-alone reduce natural Hit@5."}, "phase_e": {"retained_embeddings": [{"role": "lightweight_and_balanced", "model_key": "bge_small", "run_id": "phase_e_e0_bge_small_fixed_400_80_control", "retriever": "hybrid_rrf", "dimensions": 384}, {"role": "quality", "model_key": "e5_large_v2", "run_id": "phase_e_e5_e5_large_v2_fixed_400_80", "retrievers": ["dense", "hybrid_rrf"], "dimensions": 1024}], "rejected_embeddings": ["bge_m3_dense", "bge_m3_sparse", "nomic_full", "nomic_512"], "selection_reason": "BGE-small preserves the best latency-balanced natural quality. E5 supplies the strongest overall Hit@1/MRR and hybrid Hit@5; Nomic's natural Hit@3 niche is insufficient to retain a third model."}, "phase_f_bm25_finalists": ["fixed_600_100", "paragraph_groups", "fixed_400_80"], "phase_f_e5_base_chunk_winner": "fixed_600_100", "phase_f_e5_retrieval_winner": {"run_id": "phase_f_f2_page_prior_rrf", "method": "page_prior_rrf", "strategy": "fixed_600_100"}, "phase_f_lightweight_winner": {"run_id": "phase_f_f3_bge_small_fixed_600_100", "strategy": "fixed_600_100", "method": "hybrid_rrf"}, "phase_g_fusion_finalists": ["textbook_synonym_expansion", "formula_symbol_normalization"], "phase_g_deterministic_winner": {"run_id": "phase_g_g0_textbook_synonym_expansion", "query_method": "textbook_synonym_expansion", "fusion_with_original": false}, "phase_h_specialists": {"formula": "phase_h_h1_formula_context_activation_v2", "table": "phase_h_h1_table_rows_activation_v2", "visual": "phase_h_h0_visual_caption_context"}, "phase_h_combined_retrieval": "phase_h_h3_combined_specialist_priors", "phase_h_distributed_evidence": {"winner": "phase_h_h4_base_top5", "retained_run_ids": ["phase_h_h4_base_top5"], "candidate_budget": 5}, "phase_i_context_assembly": {"winner": "phase_i_i0_overlap_merge_metadata_preserving", "retained_run_ids": ["phase_i_i0_overlap_merge_metadata_preserving"], "candidate_pool": 5}, "final_pipeline_selection": {"best_quality": "phase_h_h3_combined_specialist_priors", "best_lightweight_cpu": "phase_f_f0_bm25_fixed_600_100", "preferred_balanced": "phase_h_h3_combined_specialist_priors", "context_assembly": "phase_i_i0_overlap_merge_metadata_preserving"}}

## Completed experiments

- `phase_a_a1_unique_source_preservation_t080`
- `phase_a_a1_weighted_rrf_t080`
- `phase_a_a1_plain_rrf_t080`
- `phase_a_a1_fixed_source_quotas_t080`
- `phase_a_a1_quotas_then_rrf_t080`
- `phase_a_a1_diversity_mmr_t080`
- `phase_a_a2_unique_source_preservation_t080`
- `phase_a_a2_plain_rrf_t070`
- `phase_a_a2_unique_source_preservation_t090`
- `phase_a_a2_unique_source_preservation_t070`
- `phase_a_a2_weighted_rrf_t070`
- `phase_a_a2_weighted_rrf_t080`
- `phase_a_a2_plain_rrf_t080`
- `phase_a_a2_plain_rrf_t090`
- `phase_a_a2_weighted_rrf_t090`
- `phase_a_a3_query_relevance_mmr_t070`
- `phase_a_a3_query_relevance_mmr_t080`
- `phase_a_a3_query_relevance_fusion_t080`
- `phase_a_a3_query_relevance_mmr_t090`
- `phase_a_a4_uncompressed_union_t080`
- `phase_b_b0_chunk_neighbor_expansion`
- `phase_b_b0_chunk_raw_chunk`
- `phase_b_b0_chunk_chapter_chunk`
- `phase_b_b0_chunk_chapter_section_chunk`
- `phase_b_b0_page_two_relevant_windows`
- `phase_b_b0_page_leading_text`
- `phase_b_b0_page_relevant_window`
- `phase_b_b0_page_heading_relevant_window`
- `phase_b_b0_page_full_page_when_fits`
- `phase_b_b0_page_relevant_paragraph`
- `phase_b_b1_member_dense_best_member`
- `phase_b_b1_member_lexical_dense_fused_member`
- `phase_b_b1_member_lexical_best_member`
- `phase_b_b1_member_all_fused_member_windows`
- `phase_b_b1_member_top_two_fused_members`
- `phase_b_b1_member_shortest_member`
- `phase_b_b2_combination_dense_best_member_two_relevant_windows_neighbor_expansion`
- `phase_b_b2_combination_dense_best_member_leading_text_neighbor_expansion`
- `phase_b_b2_combination_dense_best_member_relevant_window_neighbor_expansion`
- `phase_b_b2_combination_dense_best_member_full_page_when_fits_neighbor_expansion`
- `phase_b_b2_combination_lexical_dense_fused_member_two_relevant_windows_neighbor_expansion`
- `phase_b_b3_combination_dense_best_member_two_relevant_windows_balanced_neighbor_expansion`
- `phase_b_b3_combination_dense_best_member_leading_text_balanced_neighbor_expansion`
- `phase_b_b3_combination_lexical_dense_fused_member_two_relevant_windows_balanced_neighbor_expansion`
- `phase_b_b4_rerank_combination_shortest_member_leading_text_chapter_section_chunk`
- `phase_b_b4_rerank_combination_dense_best_member_leading_text_chapter_section_chunk`
- `phase_b_b4_rerank_combination_dense_best_member_leading_text_neighbor_expansion`
- `phase_b_b4_rerank_combination_dense_best_member_two_relevant_windows_neighbor_expansion`
- `phase_c_c1_soft_fusion_no_reranker_full_pool`
- `phase_c_c1_plain_rrf_full_pool`
- `phase_c_c1_weighted_rrf_full_pool`
- `phase_c_c1_bge_reranker_score_full_pool`
- `phase_c_c1_bge_rank_plus_rrf_rank_full_pool`
- `phase_c_c1_bge_score_plus_normalized_rrf_full_pool`
- `phase_c_c1_bge_rank_plus_soft_fusion_rank_full_pool`
- `phase_c_c2_rrf_preselector_budget_8`
- `phase_c_c2_rrf_preselector_budget_10`
- `phase_c_c2_rrf_preselector_budget_15`
- `phase_c_c2_bm25_fast_reranker_budget_8`
- `phase_c_c2_bm25_fast_reranker_budget_10`
- `phase_c_c2_bm25_fast_reranker_budget_15`
- `phase_d_d1_minilm_l6_full_pool`
- `phase_d_d3_bge_v2_m3_full_pool_screen_8`
- `phase_d_d4_mxbai_base_v1_full_pool_screen_8`
- `phase_e_e0_bge_small_fixed_400_80_control`
- `phase_e_e1_bge_m3_dense_fixed_400_80`
- `phase_e_e2_bge_m3_sparse_and_fusion_fixed_400_80`
- `phase_e_e3_nomic_embed_v1_5_full_fixed_400_80`
- `phase_e_e4_nomic_embed_v1_5_512_fixed_400_80`
- `phase_e_e5_e5_large_v2_fixed_400_80`
- `phase_f_f0_bm25_fixed_300_50`
- `phase_f_f0_bm25_fixed_400_80`
- `phase_f_f0_bm25_fixed_600_100`
- `phase_f_f0_bm25_fixed_400_80_headings`
- `phase_f_f0_bm25_paragraph_groups`
- `phase_f_f0_bm25_section_aware`
- `phase_f_f1_e5_fixed_600_100`
- `phase_f_f1_e5_paragraph_groups`
- `phase_f_f1_e5_fixed_400_80`
- `phase_f_f2_parent_page_child`
- `phase_f_f2_page_prior_rrf`
- `phase_f_f2_neighbor_expansion`
- `phase_f_f2_query_relevant_windows`
- `phase_f_f3_bge_small_fixed_600_100`
- `phase_f_f4_bge_small_page_prior_rrf`
- `phase_g_g0_raw`
- `phase_g_g0_spelling_normalization`
- `phase_g_g0_grammar_cleanup`
- `phase_g_g0_textbook_synonym_expansion`
- `phase_g_g0_acronym_expansion`
- `phase_g_g0_formula_symbol_normalization`
- `phase_g_g1_original_plus_textbook_synonym_expansion`
- `phase_g_g1_original_plus_formula_symbol_normalization`
- `phase_h_h0_formula_equation_lines`
- `phase_h_h0_formula_equation_context`
- `phase_h_h0_table_flattened`
- `phase_h_h0_table_rows_with_headers`
- `phase_h_h0_table_key_value`
- `phase_h_h0_visual_caption_context`
- `phase_h_h1_formula_context_activation_v2`
- `phase_h_h1_table_rows_activation_v2`
- `phase_h_h2_formula_context_activation_v3`
- `phase_h_h3_combined_specialist_priors`
- `phase_h_h4_base_top5`
- `phase_h_h4_neighbor_expansion`
- `phase_h_h4_same_page_expansion`
- `phase_h_h4_same_section_expansion`
- `phase_h_h4_coverage_diversity`
- `phase_h_h4_multi_stage_distinct_pages`
- `phase_i_i0_top3_relevance`
- `phase_i_i0_top5_relevance`
- `phase_i_i0_token_budget_1200`
- `phase_i_i0_token_budget_1800`
- `phase_i_i0_token_budget_2400`
- `phase_i_i0_overlap_merge`
- `phase_i_i0_same_page_merge`
- `phase_i_i0_redundancy_removal`
- `phase_i_i0_diversity_selection`
- `phase_i_i0_textbook_order`
- `phase_i_i0_direct_support_grouping`
- `phase_i_i0_overlap_merge_metadata_preserving`

## Retained directions

- `uncompressed_union_t080`
- `combination_dense_best_member_two_relevant_windows_neighbor_expansion`
- `soft_fusion_no_reranker`
- `bge_rank_plus_rrf_rank`
- `minilm_l6_reranker_rank_plus_rrf_rank`
- `bge_small_hybrid_rrf`
- `bge_m3_dense_sparse_bm25_rrf_quality_frontier`
- `bge_small_hybrid_phase_e`
- `e5_large_v2_quality_embedding`
- `e5_fixed_600_100_page_prior_rrf`
- `e5_fixed_600_100_neighbor_expansion`
- `bge_small_fixed_600_100_hybrid_rrf`
- `g0_raw`
- `g0_grammar_cleanup`
- `g0_textbook_synonym_expansion`
- `g0_acronym_expansion`
- `g0_formula_symbol_normalization`
- `g1_original_plus_textbook_synonym_expansion`
- `g1_original_plus_formula_symbol_normalization`
- `synonym_bge_fixed_600_100_formula_equation_context`
- `synonym_bge_fixed_600_100_table_rows_with_headers`
- `synonym_bge_fixed_600_100_visual_caption_context`
- `synonym_bge_fixed_600_100_combined_specialist_priors`
- `combined_specialists_base_top5`
- `combined_specialists_coverage_diversity`
- `phase_i_i0_overlap_merge`
- `phase_i_i0_overlap_merge_metadata_preserving`

## Rejected directions

- `fixed_source_quotas_t080`
- `quotas_then_rrf_t080`
- `diversity_mmr_t080`
- `unique_source_preservation_t080`
- `plain_rrf_t070`
- `unique_source_preservation_t090`
- `unique_source_preservation_t070`
- `weighted_rrf_t070`
- `weighted_rrf_t080`
- `plain_rrf_t080`
- `plain_rrf_t090`
- `weighted_rrf_t090`
- `query_relevance_mmr_t070`
- `query_relevance_mmr_t080`
- `query_relevance_fusion_t080`
- `query_relevance_mmr_t090`
- `chunk_chapter_chunk`
- `page_heading_relevant_window`
- `page_full_page_when_fits`
- `page_relevant_paragraph`
- `member_lexical_best_member`
- `member_all_fused_member_windows`
- `member_top_two_fused_members`
- `combination_dense_best_member_full_page_when_fits_neighbor_expansion`
- `combination_lexical_dense_fused_member_two_relevant_windows_neighbor_expansion`
- `plain_rrf`
- `weighted_rrf`
- `bge_reranker_score`
- `bge_score_plus_normalized_rrf`
- `bge_rank_plus_soft_fusion_rank`
- `rrf_preselector_budget_8`
- `rrf_preselector_budget_10`
- `rrf_preselector_budget_15`
- `bm25_fast_reranker_budget_8`
- `bm25_fast_reranker_budget_10`
- `bm25_fast_reranker_budget_15`
- `bge_v2_m3_reranker_score_screen_8`
- `mxbai_base_v1_screen_8_stopped`
- `bge_v2_m3_full_run`
- `mxbai_base_v1_full_run`
- `bge_m3_dense_balanced`
- `bge_m3_sparse_balanced`
- `bge_m3_multivector_escalation`
- `nomic_full_embedding`
- `nomic_512_embedding`
- `bge_m3_embedding_family`
- `e5_fixed_600_100_parent_page_child`
- `e5_fixed_600_100_query_relevant_windows`
- `bge_small_fixed_600_100_page_prior_rrf`
- `g0_spelling_normalization`
- `synonym_bge_fixed_600_100_formula_equation_lines`
- `synonym_bge_fixed_600_100_table_flattened`
- `synonym_bge_fixed_600_100_table_key_value`
- `synonym_bge_fixed_600_100_formula_equation_context`
- `combined_specialists_neighbor_expansion`
- `combined_specialists_same_page_expansion`
- `combined_specialists_same_section_expansion`
- `combined_specialists_multi_stage_distinct_pages`
- `phase_i_i0_top3_relevance`
- `phase_i_i0_top5_relevance`
- `phase_i_i0_token_budget_1200`
- `phase_i_i0_token_budget_1800`
- `phase_i_i0_token_budget_2400`
- `phase_i_i0_same_page_merge`
- `phase_i_i0_redundancy_removal`
- `phase_i_i0_diversity_selection`
- `phase_i_i0_textbook_order`
- `phase_i_i0_direct_support_grouping`

## Unresolved questions

- A reviewed generation benchmark for correctness, faithfulness, citations, and abstention is required before Phase J.

## Exact next command or task

Review reports/experiments/final_experiment_report.md; create and approve a grounded-answer generation benchmark before Phase J.

## Warnings and invariants

- Do not modify the benchmark, reviewed gold, historical reports, or previous baseline outputs.
- Gold evidence is evaluation-only; never use it to build, score, truncate, or rerank candidates.
- Use successive narrowing and do not introduce unapproved models or uncontrolled configuration grids.
- Resume from the append-only run log; never overwrite a completed run directory.
