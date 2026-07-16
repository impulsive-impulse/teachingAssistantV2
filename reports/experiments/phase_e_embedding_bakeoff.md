# Phase E — embedding model bake-off

All runs use the same front-matter-free fixed 400/80 chunk corpus, book-local search, normalized embeddings, cosine similarity, and BM25 RRF.

| Run | Selected | H@1 | H@3 | H@5 | MRR | Natural H@5 | p95 | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `phase_e_e0_bge_small_fixed_400_80_control` | hybrid_rrf | 15/61 | 34/61 | 42/61 | 0.442 | 13/20 | 53.1 ms | retain |
| `phase_e_e1_bge_m3_dense_fixed_400_80` | dense | 16/61 | 32/61 | 42/61 | 0.447 | 11/20 | 219.7 ms | investigate |
| `phase_e_e2_bge_m3_sparse_and_fusion_fixed_400_80` | sparse | 17/61 | 33/61 | 42/61 | 0.464 | 10/20 | 719.1 ms | investigate |
| `phase_e_e3_nomic_embed_v1_5_full_fixed_400_80` | hybrid_rrf | 16/61 | 37/61 | 43/61 | 0.460 | 14/20 | 145.2 ms | investigate |
| `phase_e_e4_nomic_embed_v1_5_512_fixed_400_80` | hybrid_rrf | 16/61 | 36/61 | 42/61 | 0.458 | 14/20 | 148.6 ms | investigate |
| `phase_e_e5_e5_large_v2_fixed_400_80` | dense | 22/61 | 35/61 | 46/61 | 0.524 | 12/20 | 455.8 ms | investigate |

## BGE-M3 stopping gate

- Balanced control retained: `phase_e_e0_bge_small_fixed_400_80_control`.
- Overall-quality frontier retained: `phase_e_e2 dense_sparse_bm25_rrf variant`.
- BGE-M3 dense and sparse-alone are rejected as balanced choices; multi-vector escalation stopped on quality/latency grounds.

Detailed dense and hybrid slice metrics and complete rankings are in each run directory.

## Final selection

- Lightweight/balanced: BGE-small hybrid RRF.
- Quality: E5-large-v2, retaining dense and BM25-hybrid operating points.
- Rejected from Phase F: BGE-M3 and Nomic full/512.
