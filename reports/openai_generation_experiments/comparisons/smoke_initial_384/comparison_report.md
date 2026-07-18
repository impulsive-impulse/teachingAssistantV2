# Local vs OpenAI generation comparison

Questions with all four answers: **5**

| Source | Completed / planned | Paired questions | Required-point coverage | Citation validity | Unsupported-claim rate | P95 latency (s) |
|---|---:|---:|---:|---:|---:|---:|
| local_gold | 8 / 8 | 5 | 0.6433 | 1.0000 | 0.0000 | 68.1771 |
| local_retrieved | 8 / 8 | 5 | 0.6933 | 1.0000 | 0.0000 | 199.9577 |
| openai_gold | 5 / 8 | 5 | 0.7433 | 1.0000 | 0.0000 | 5.744 |
| openai_retrieved | 5 / 8 | 5 | 0.6933 | 1.0000 | 0.0000 | 4.4247 |

Automatic token-overlap metrics are screening signals, not the final quality judgment.
Use the blinded packet for scientific correctness, completeness, grounding, and clarity review.
