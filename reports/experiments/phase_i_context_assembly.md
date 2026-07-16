# Phase I — context assembly

All assemblers consume the same retained Phase H top-five pool and are gold-blind.

| Method | Direct evidence | Exact span | Complete pages | Multi-page complete | Avg tokens | p95 tokens | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| top3_relevance | 44/61 | 44/61 | 50/61 | 17/21 | 1813 | 1909 | reject |
| top5_relevance | 50/61 | 50/61 | 55/61 | 18/21 | 3000 | 3118 | reject |
| token_budget_1200 | 40/61 | 40/61 | 43/61 | 12/21 | 1200 | 1200 | reject |
| token_budget_1800 | 44/61 | 44/61 | 51/61 | 17/21 | 1800 | 1800 | reject |
| token_budget_2400 | 49/61 | 49/61 | 53/61 | 18/21 | 2400 | 2400 | reject |
| overlap_merge | 50/61 | 50/61 | 55/61 | 18/21 | 2965 | 3116 | reject (superseded) |
| overlap_merge_metadata_preserving | 50/61 | 50/61 | 55/61 | 18/21 | 2965 | 3116 | retain (final) |
| same_page_merge | 50/61 | 50/61 | 55/61 | 18/21 | 2965 | 3116 | reject |
| redundancy_removal | 50/61 | 50/61 | 55/61 | 18/21 | 3000 | 3118 | reject |
| diversity_selection | 44/61 | 44/61 | 50/61 | 17/21 | 1813 | 1909 | reject |
| textbook_order | 50/61 | 50/61 | 55/61 | 18/21 | 3000 | 3118 | reject |
| direct_support_grouping | 50/61 | 50/61 | 55/61 | 18/21 | 3000 | 3118 | reject |

## Selection

Retained `phase_i_i0_overlap_merge_metadata_preserving`. The gate first preserves accepted evidence and literal reviewed spans, then multi-page completeness and context size; the final tie-break requires per-source page/chapter/section provenance after merging.

Exact-span retention is intentionally strict and can undercount semantically complete contexts when OCR or overlap removal changes wording.
