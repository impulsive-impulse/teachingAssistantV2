# Phase H — textbook-specific retrieval specialists

Specialists use static query-text activation; dependency labels are evaluation-only.

| Method | Branch | Activated | Target H@1/3/5 | Target MRR | Overall H@1/3/5 | Natural H@1/3/5 | p95 | Decision |
|---|---|---:|---:|---:|---:|---:|---:|---|
| formula_equation_lines | formula | 29 | 3/9/10 | 0.415 | 21/39/47 | 8/11/15 | 86.2 ms | reject |
| formula_equation_context | formula | 29 | 4/9/10 | 0.444 | 24/40/49 | 9/12/16 | 75.2 ms | retain |
| table_flattened | table | 6 | 3/3/3 | 1.000 | 23/42/50 | 8/13/16 | 107.1 ms | reject |
| table_rows_with_headers | table | 6 | 3/3/3 | 1.000 | 23/43/50 | 8/13/16 | 60.5 ms | retain |
| table_key_value | table | 6 | 3/3/3 | 1.000 | 23/43/50 | 8/13/16 | 36.0 ms | reject |
| visual_caption_context | visual | 6 | 3/6/6 | 0.667 | 23/44/50 | 9/13/16 | 33.7 ms | retain |
| formula_equation_context | formula | 15 | 5/9/10 | 0.478 | 23/43/50 | 8/13/16 | 84.2 ms | retain |
| table_rows_with_headers | table | 3 | 3/3/3 | 1.000 | 22/43/50 | 8/13/16 | 74.6 ms | retain |
| formula_equation_context | formula | 16 | 4/9/10 | 0.447 | 22/43/50 | 8/13/16 | 83.7 ms | reject |

## Visual capability boundary

Caption/nearby text is evaluated locally. Embedded PDF images can be extracted for inspection, but no approved local multimodal encoder is available, so image-semantic retrieval and generated diagram descriptions are not scored or treated as text-retrieval failures.
