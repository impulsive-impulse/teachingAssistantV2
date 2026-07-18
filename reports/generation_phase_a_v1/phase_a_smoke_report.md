# Phase A gold-context smoke test

This gate uses the approved Qwen3-8B Q4_K_M model and accepted textbook PDF pages. No prompt comparison or additional model download is part of this run.

## Summary

- Completed: 8/8
- Valid structured outputs and evidence IDs: 8
- Strict lexical citation-support passes: 3
- Deterministic automatic passes: 1
- Mean required-point coverage: 0.4854
- Mean rubric score: 0.4578
- Mean latency: 34.5646 seconds
- Manual review remains required before prompt comparisons.

## Per-question results

| Question | Book | Difficulty | JSON/IDs | Lexical citation support | Required coverage | Score | Pass | Latency (s) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| GEN-BIO-002 | biology | easy | 1 | 1 | 1.0000 | 1.0000 | 1 | 20.729 |
| GEN-BIO-005 | biology | medium | 1 | 0 | 0.5000 | 0.3750 | 0 | 40.713 |
| GEN-BIO-012 | biology | hard | 1 | 0 | 0.8000 | 0.6000 | 0 | 44.248 |
| GEN-BIO-014 | biology | medium | 1 | 0 | 0.6000 | 0.4500 | 0 | 32.809 |
| GEN-PSC-002 | physical_sciences | hard | 1 | 0 | 0.0000 | 0.0000 | 0 | 35.241 |
| GEN-PSC-006 | physical_sciences | easy | 1 | 1 | 0.3333 | 0.5000 | 0 | 26.814 |
| GEN-PSC-009 | physical_sciences | medium | 1 | 1 | 0.2500 | 0.4375 | 0 | 32.912 |
| GEN-PSC-015 | physical_sciences | hard | 1 | 0 | 0.4000 | 0.3000 | 0 | 43.050 |

## Manual rubric and citation review

- Strict answer-and-grounding passes: 2/8
- Mean strict required-point coverage: 0.6937
- Fully supported citation sets: 5/8
- Partially supported citation sets: 3/8
- Unsupported claims found: 0

| Question | Required coverage | Citation verdict | Strict pass |
|---|---:|---|---:|
| GEN-BIO-002 | 1.0000 | supported | 1 |
| GEN-BIO-005 | 1.0000 | partially_supported | 0 |
| GEN-BIO-012 | 0.8000 | partially_supported | 0 |
| GEN-BIO-014 | 0.6000 | supported | 0 |
| GEN-PSC-002 | 0.5000 | partially_supported | 0 |
| GEN-PSC-006 | 1.0000 | supported | 1 |
| GEN-PSC-009 | 0.2500 | supported | 0 |
| GEN-PSC-015 | 0.4000 | supported | 0 |

## Gate decision

The infrastructure smoke gate passed (8/8 completed and resumable), but the answer-quality and grounding gate did not: only 2/8 answers passed strict manual rubric plus citation review. Prompt comparisons and other model downloads therefore remain gated. The next action is to correct context sufficiency and answer instructions using this same Qwen baseline, after the user reviews these results.

## Reproduction

```powershell
temp\python-x64\python.exe scripts\run_generation_phase_a.py `
  --llama-server <path-to-native-arm64-llama-server.exe> `
  --model <path-to-Qwen3-8B-Q4_K_M.gguf>
```

Configuration: `generation_phase_a_gold_context_smoke_v1`. Benchmark SHA-256: `f756e6333909c72f0e0be82b7bc16c9756f158fb39e16d463442e2bed5266680`.
