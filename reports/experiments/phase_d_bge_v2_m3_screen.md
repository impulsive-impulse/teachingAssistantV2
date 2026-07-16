# Phase D stratified reranker screen

Model: `BAAI/bge-reranker-v2-m3` at `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`. The screen uses 2 query(ies) from each book × benchmark-slice group and does not select queries with gold labels.

Selected logic: `reranker_score`; answerable rows: 8; Hit@1/3/5: 2/4/5; MRR: 0.397; p95 latency: 154427.0 ms; peak memory: 2816.9 MiB.

## Decision

Reject the full 66-query run. Natural-student Hit@1/3/5 was only 1/4 on the balanced screen, while average latency was 115.1 seconds per query—about 20 times MiniLM. This is not a meaningful quality gain for the added CPU cost.
