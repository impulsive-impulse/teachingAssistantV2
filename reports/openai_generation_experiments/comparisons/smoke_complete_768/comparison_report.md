# Local vs OpenAI generation comparison

Questions with all four answers: **8**

| Source | Completed / planned | Paired questions | Required-point coverage | Citation validity | Unsupported-claim rate | P95 latency (s) |
|---|---:|---:|---:|---:|---:|---:|
| local_gold | 8 / 8 | 8 | 0.5396 | 1.0000 | 0.0000 | 82.3022 |
| local_retrieved | 8 / 8 | 8 | 0.6771 | 1.0000 | 0.0000 | 201.2608 |
| openai_gold | 8 / 8 | 8 | 0.7271 | 1.0000 | 0.2500 | 7.6895 |
| openai_retrieved | 8 / 8 | 8 | 0.6708 | 1.0000 | 0.2500 | 6.3963 |

Automatic token-overlap metrics are screening signals, not the final quality judgment.
Use the blinded packet for scientific correctness, completeness, grounding, and clarity review.
