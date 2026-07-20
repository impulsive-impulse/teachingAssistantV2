# Local generation experiments v1

> Historical experiment report. Its provisional recommendation was reviewed
> and is now frozen as the `local_offline` fallback in Generation Baseline v1.
> The current decision is in `config/generation_baseline_v1.json`.

## Historical local recommendation

- Model: `qwen3_8b_q4_k_m`
- Prompt: `P1`
- Retrieved context: `retrieved_top5_page_order_compact`
- Maximum output: 384 tokens
- Status: superseded by the frozen Generation Baseline v1 decision.

## Configuration roles

- Best lightweight: `qwen3_8b_q4_k_m`; retrieved holdout coverage 0.4903, p95 351.7045 s, max output 384 tokens.
- Best automatic quality: `qwen3_14b_q4_k_m`; retrieved holdout coverage 0.5632, p95 469.418 s, max output 512 tokens.
- Preferred balanced: Qwen3-8B. It has the stronger grounding score (citation validity minus unsupported rate), lower latency and memory, and is the exact configuration used for the final 40-question run.

## Finalist holdout comparison

| Model | Mode | Coverage | Citation | Unsupported | Formula | p95 latency | Peak RSS GiB |
|---|---|---:|---:|---:|---:|---:|---:|
| qwen3_8b_q4_k_m | gold | 0.5028 | 0.9583 | 0.0417 | 0.0000 | 97.3338 | 14.22 |
| qwen3_8b_q4_k_m | retrieved | 0.4903 | 0.9583 | 0.0000 | 0.0000 | 351.7045 | 17.73 |
| qwen3_14b_q4_k_m | gold | 0.5215 | 1.0000 | 0.0000 | 0.0000 | 186.9131 | 20.97 |
| qwen3_14b_q4_k_m | retrieved | 0.5632 | 0.9583 | 0.0417 | 0.2000 | 469.418 | 24.89 |

## Final 40-question comparison

| Mode | Required coverage | Citation validity | Unsupported rate | Structured output | p50 latency | p95 latency |
|---|---:|---:|---:|---:|---:|---:|
| Gold | 0.4654 | 0.9750 | 0.0250 | 0.9750 | 50.4694 | 85.7361 |
| Frozen retrieved | 0.4704 | 0.9500 | 0.0250 | 0.9750 | 187.2606 | 229.4036 |

## Dependency diagnostics

| Slice | Questions | Coverage | Citation validity |
|---|---:|---:|---:|
| formula | 10 | 0.4450 | 0.9000 |
| multiple_passages | 11 | 0.3273 | 0.9091 |
| table | 1 | 0.6000 | 1.0000 |
| visual | 2 | 0.5000 | 0.5000 |

## Retrieved results by book and difficulty

| Slice | Questions | Coverage | Citation validity |
|---|---:|---:|---:|
| biology | 20 | 0.4717 | 1.0000 |
| physical_sciences | 20 | 0.4692 | 0.9000 |
| medium | 18 | 0.5000 | 1.0000 |
| easy | 9 | 0.5185 | 1.0000 |
| hard | 13 | 0.3962 | 0.8462 |

## Retrieved-context failures

| Question | Category | Coverage |
|---|---|---:|
| GEN-BIO-001 | evidence present but incomplete | 0.5000 |
| GEN-BIO-002 | evidence present but incomplete | 0.5000 |
| GEN-BIO-003 | evidence absent from retrieved context | 0.5000 |
| GEN-BIO-004 | evidence present but incomplete | 0.4000 |
| GEN-BIO-005 | multi-passage synthesis failure | 0.5000 |
| GEN-BIO-006 | evidence present but incomplete | 0.5000 |
| GEN-BIO-007 | multi-passage synthesis failure | 0.2000 |
| GEN-BIO-008 | evidence present but incomplete | 0.8000 |
| GEN-BIO-009 | evidence present but incomplete | 0.7500 |
| GEN-BIO-010 | evidence present but incomplete | 0.3333 |
| GEN-BIO-011 | evidence absent from retrieved context | 0.0000 |
| GEN-BIO-012 | multi-passage synthesis failure | 0.6000 |
| GEN-BIO-013 | evidence present but incomplete | 0.6667 |
| GEN-BIO-014 | evidence present but incomplete | 0.8000 |
| GEN-BIO-015 | multi-passage synthesis failure | 0.2000 |
| GEN-BIO-016 | evidence present but incomplete | 0.6000 |
| GEN-BIO-017 | evidence present but incomplete | 0.2500 |
| GEN-BIO-019 | evidence present but incomplete | 0.3333 |
| GEN-BIO-020 | multi-passage synthesis failure | 0.0000 |
| GEN-PSC-002 | formula error or omission | 0.7500 |
| GEN-PSC-003 | formula error or omission | 0.2000 |
| GEN-PSC-004 | formula error or omission | 0.5000 |
| GEN-PSC-005 | formula error or omission | 0.5000 |
| GEN-PSC-006 | evidence present but incomplete | 0.6667 |
| GEN-PSC-007 | evidence present but incomplete | 0.8000 |
| GEN-PSC-008 | formula error or omission | 0.0000 |
| GEN-PSC-010 | evidence present but incomplete | 0.5000 |
| GEN-PSC-011 | formula error or omission | 0.5000 |
| GEN-PSC-012 | unsupported extrapolation | 0.2000 |
| GEN-PSC-013 | citation failure | 0.0000 |
| GEN-PSC-014 | evidence present but incomplete | 0.5000 |
| GEN-PSC-015 | formula error or omission | 0.6000 |
| GEN-PSC-016 | multi-passage synthesis failure | 0.2000 |
| GEN-PSC-017 | formula error or omission | 0.4000 |
| GEN-PSC-018 | visual information unavailable | 0.0000 |
| GEN-PSC-019 | evidence present but incomplete | 0.6667 |
| GEN-PSC-020 | evidence present but incomplete | 0.4000 |

## Abstention diagnostic

Prompt-only abstention: 4/5; model plus deterministic citation-support check: 5/5. Treat this as diagnostic only.

## Model availability

The approved Gemma 3 4B and 12B repositories returned access denied for the signed-in Hugging Face account, so those arms and the Gemma-only visual diagnostic were not run. This is an external repository-access limitation, not a runtime rejection.

## Interpretation limits

Lexical rubric matching is a repeatable screen, not proof of scientific correctness. Review `blinded_human_review_packet.jsonl` before freezing a generation baseline.

## Success-target assessment

- Gold required-point coverage: 46.54% versus the 85% target: **not met**.
- Retrieved required-point coverage: 47.04% versus the 75% target: **not met**.
- Gold citations valid: 39/40; retrieved citations valid: 38/40.
- Retrieved formula screen: 1/10. Formula answering is the clearest blocker.
- Conclusion: this is a reproducible experiment winner, but it is not strong enough to freeze as the production generation baseline without blinded human review and a targeted formula/completeness improvement cycle.

## Exact retained runtime and model

- Model: `Qwen/Qwen3-8B-GGUF` revision `7c41481f57cb95916b40956ab2f0b139b296d974`, file `Qwen3-8B-Q4_K_M.gguf`, SHA-256 `d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785`.
- Runtime: llama.cpp build 10046 commit `32e789fdfd598e9a1872da55ac941e4d94f030bd`; Windows ARM64 CPU; 10 threads; context 8192; batch/ubatch 512/256; GPU layers 0.
- Sampling: seed 42, temperature 0.0, max output 384, thinking disabled.

## Exact retained prompt template

```text
/no_think
Use only the supplied textbook evidence. Do not use outside knowledge. If it cannot support the question, return insufficient_evidence. Never invent page numbers. First select the relevant evidence IDs internally, then write the answer. Make the answer {depth} and suitable for a Class 10 student.
Return only valid JSON with exactly this shape: {"status":"answered|insufficient_evidence","answer":"...","selected_evidence_ids":["E1"],"citations":[{"evidence_id":"E1","pdf_page":1,"textbook_page":1}],"missing_information":[]}

QUESTION:
{normalized_question}

TEXTBOOK EVIDENCE:
[{evidence_id}] PDF {pdf_page}; textbook {textbook_page}
{evidence_text}
```

## Reproduction

```powershell
temp\python-x64\python.exe scripts\run_generation_experiment_matrix.py `
  --llama-server <path-to-native-arm64-llama-server.exe> `
  --qwen8 <path-to-Qwen3-8B-Q4_K_M.gguf> `
  --qwen14 <path-to-Qwen3-14B-Q4_K_M.gguf>
```

Completed checkpoints are reused, and frozen input hashes are verified before every configuration.
