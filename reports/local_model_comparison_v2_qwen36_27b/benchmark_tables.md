# Generated benchmark tables

This file is generated from immutable run manifests. Validity and early-stopped smoke rows are not quality-leaderboard finals. The Decision column records the runner's immediate gate result; final eligibility is recorded in the leaderboard.

## CPU/GPU benchmark table

| Model | Stage | Backend | Questions | GPU offload | TTFT p50 (s) | Latency p50 (s) | Prompt tok/s | Gen tok/s | Peak RAM (GiB) | GPU local (GiB) | Run gate result |
|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| Qwen3.6-27B Q4_K_M | validity | cpu_arm64 | 1 | CPU only | 396.70 | 578.22 | 12.32 | 1.50 | 35.99 | 0.00 | pending_review |
| Qwen3.6-27B Q4_K_M | validity | adreno_opencl | 1 | 65/65 | 182.23 | 348.72 | 26.82 | 1.87 | 36.56 | 18.35 | pending_review |

## Frozen control validity reference

This row is copied from the checksum-pinned v1 control manifest named in `artifact_registry.json`; it was not rerun or modified in this experiment.

| Model | Backend | TTFT (s) | Latency (s) | Prompt tok/s | Gen tok/s | Peak RAM (GiB) | GPU local (GiB) |
|---|---|---:|---:|---:|---:|---:|---:|
| Qwen3-8B Q4_K_M — frozen v1 control | adreno_opencl | 73.29 | 100.70 | 63.55 | 6.09 | 10.85 | 5.95 |

## Quality observations by completed stage

| Model | Stage | Backend | N | Coverage | Citation valid | Citation support | Unsupported | Formula | Multi-passage | Schema valid | Full validator | Run gate result |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Qwen3.6-27B Q4_K_M | validity | cpu_arm64 | 1 | 75.0% | 100.0% | 88.0% | 0.0% | — | — | 100.0% | 100.0% | pending_review |
| Qwen3.6-27B Q4_K_M | validity | adreno_opencl | 1 | 75.0% | 100.0% | 64.3% | 0.0% | — | — | 100.0% | 100.0% | pending_review |

## Gate-aware quality leaderboard

Rows use each model's furthest completed stage; stages with different question counts are not treated as directly interchangeable quality estimates.

| Model | Furthest stage | Backend | N | Coverage | Citation valid | Schema valid | TTFT p50 (s) | Latency p50 (s) | Eligibility | Outcome |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| Qwen3.6-27B Q4_K_M | validity | adreno_opencl | 1 | 75.0% | 100.0% | 100.0% | 182.23 | 348.72 | ineligible | unacceptable latency and memory |

## Winners and Answering Baseline v2 recommendation

- **Best quality model:** Qwen3-8B Q4_K_M — frozen v1 control; no candidate passed all successive-narrowing gates.
- **Best speed model (eligible models):** Qwen3-8B Q4_K_M — frozen v1 control.
- **Best balanced model:** Qwen3-8B Q4_K_M — frozen v1 control.
- **Comparison against the control:** Qwen3.6-27B Q4_K_M: unacceptable latency and memory.
- **Blinded human review:** no packet was generated because no alternative reached development/finalist status.
- **Holdout:** untouched; no alternative satisfied the finalist gate.
- **Answering Baseline v2 recommendation:** do not advance any tested candidate; retain the frozen production control.
