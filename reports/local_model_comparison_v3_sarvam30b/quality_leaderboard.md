# Quality Leaderboard

| Rank | Model | Eligibility | Quality evidence | Result |
|---:|---|---|---|---|
| 1 | Qwen3-8B Q4_K_M control | Eligible frozen control | Existing completed development benchmark and human-review evidence | Best quality, speed, and balance by default |
| — | Sarvam-30B Q4_K_M | Ineligible | No answer generated; quality was not measured | Rejected before output-validity gate |

Sarvam cannot be ranked as worse or better on answer quality because its Adreno
server never became ready. It should not proceed toward Answering Baseline v2 on
this hardware. Qwen3-8B remains the production baseline; no production files or
weights were replaced.
