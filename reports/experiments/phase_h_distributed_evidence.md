# Phase H — distributed evidence-set construction

All selectors consume the same complete combined-specialist ranking and are gold-blind.

| Selector | Multi-page complete@3/5 | Multi-page direct@5 | Mean page coverage@5 | Multi-chunk direct@5 | Overall direct@5 | Avg tokens@5 | p95 latency | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| base_top5 | 17/18 of 21 | 17/21 | 0.913 | 23/27 | 50/61 | 2955 | 71.2 ms | retain (final) |
| neighbor_expansion | 12/18 of 21 | 18/21 | 0.873 | 22/27 | 48/61 | 2962 | 71.2 ms | reject |
| same_page_expansion | 12/17 of 21 | 17/21 | 0.849 | 21/27 | 47/61 | 2962 | 71.4 ms | reject |
| same_section_expansion | 17/18 of 21 | 16/21 | 0.913 | 20/27 | 47/61 | 2970 | 71.5 ms | reject |
| coverage_diversity | 14/19 of 21 | 16/21 | 0.960 | 20/27 | 46/61 | 2988 | 71.4 ms | reject (final; screen retained) |
| multi_stage_distinct_pages | 17/18 of 21 | 17/21 | 0.913 | 23/27 | 50/61 | 2968 | 71.3 ms | reject |

Complete-page coverage uses reviewed PDF pages only during evaluation. The benchmark does not label every separately required fact, so multi-chunk completeness is reported as direct accepted-evidence coverage rather than claimed full answer sufficiency.

## Final preservation gate

Base top-5 is the production winner. Coverage/diversity gains one complete multi-page case but loses four overall direct-evidence hits, so its screen-stage retain label is rejected by the required direct-evidence preservation gate.
