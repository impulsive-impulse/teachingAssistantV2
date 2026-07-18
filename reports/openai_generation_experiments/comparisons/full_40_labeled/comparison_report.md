# Local vs OpenAI generation comparison

Questions with all four answers: **40**

| Source | Completed / planned | Paired questions | Required-point coverage | Citation validity | Unsupported-claim rate | P95 latency (s) |
|---|---:|---:|---:|---:|---:|---:|
| local_gold | 40 / 40 | 40 | 0.4654 | 0.9750 | 0.0250 | 85.7361 |
| local_retrieved | 40 / 40 | 40 | 0.4704 | 0.9500 | 0.0250 | 229.4036 |
| openai_gold | 40 / 40 | 40 | 0.5779 | 1.0000 | 0.1000 | 6.2071 |
| openai_retrieved | 40 / 40 | 40 | 0.5450 | 0.9500 | 0.0750 | 8.7332 |

Automatic token-overlap metrics are screening signals, not the final quality judgment.
Use the blinded packet for unbiased scoring, or the labeled packet and revealed HTML for direct
local-Qwen versus GPT-4o gap analysis. Review scientific correctness, completeness, grounding,
and clarity manually in either workflow.
