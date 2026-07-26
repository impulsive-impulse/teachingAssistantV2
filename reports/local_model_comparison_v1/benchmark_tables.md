# Generated benchmark tables

This file is generated from immutable run manifests. Validity and early-stopped smoke rows are not quality-leaderboard finals.

## CPU/GPU benchmark table

| Model | Stage | Backend | Questions | GPU offload | TTFT p50 (s) | Latency p50 (s) | Prompt tok/s | Gen tok/s | Peak RAM (GiB) | GPU local (GiB) | Decision |
|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| Qwen3-8B Q4_K_M — frozen v1 control | validity | cpu_arm64 | 1 | CPU only | 189.40 | 249.93 | 24.59 | 2.76 | 10.28 | 0.00 | pending_review |
| Qwen3-8B Q4_K_M — frozen v1 control | validity | adreno_opencl | 1 | 37/37 | 73.29 | 100.70 | 63.55 | 6.09 | 10.85 | 5.95 | pending_review |
| Qwen3-8B Q4_K_M — frozen v1 control | smoke | adreno_opencl | 8 | 37/37 | 80.24 | 126.62 | 55.98 | 5.73 | 14.96 | 5.95 | pending_review |
| Qwen3-8B Q4_K_M — frozen v1 control | development | adreno_opencl | 16 | 37/37 | 65.95 | 104.84 | 67.05 | 6.66 | 18.44 | 5.95 | pending_review |
| Gemma 3 12B IT QAT Q4_0 | validity | cpu_arm64 | 1 | CPU only | 113.27 | 135.09 | 41.16 | 5.73 | 14.80 | 0.00 | pending_review |
| Gemma 3 12B IT QAT Q4_0 | validity | adreno_opencl | 1 | 49/49 | 82.36 | 108.96 | 56.61 | 5.86 | 17.20 | 8.94 | pending_review |
| Gemma 3 12B IT QAT Q4_0 | smoke | adreno_opencl | 3 | 49/49 | 81.20 | 122.79 | 58.60 | 5.27 | 19.66 | 8.94 | reject |
| gpt-oss-20b native MXFP4 | validity | cpu_arm64 | 1 | CPU only | 120.35 | 158.62 | 38.03 | 4.65 | 22.29 | 0.00 | pending_review |
| gpt-oss-20b native MXFP4 | validity | adreno_opencl | 1 | 25/25 | 98.54 | 136.08 | 46.39 | 10.16 | 22.88 | 11.36 | reject |
| Phi-4 14B Q4_K_S | validity | cpu_arm64 | 1 | CPU only | 197.48 | 258.08 | 23.25 | 2.79 | 17.13 | 0.00 | pending_review |
| Phi-4 14B Q4_K_S | validity | adreno_opencl | 1 | 41/41 | 238.49 | 274.98 | 19.26 | 3.89 | 17.73 | 9.67 | pending_review |
| Granite 3.3 8B Instruct Q4_K_M | validity | cpu_arm64 | 1 | CPU only | 210.67 | 259.12 | 26.96 | 3.03 | 10.39 | 0.00 | pending_review |
| Granite 3.3 8B Instruct Q4_K_M | validity | adreno_opencl | 1 | 41/41 | 94.34 | 122.87 | 60.22 | 7.22 | 11.09 | 6.33 | pending_review |

## Quality observations by completed stage

| Model | Stage | Backend | N | Coverage | Citation valid | Citation support | Unsupported | Formula | Multi-passage | Schema valid | Full validator | Decision |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Qwen3-8B Q4_K_M — frozen v1 control | validity | cpu_arm64 | 1 | 100.0% | 100.0% | 81.1% | 0.0% | — | — | 100.0% | 100.0% | pending_review |
| Qwen3-8B Q4_K_M — frozen v1 control | validity | adreno_opencl | 1 | 100.0% | 100.0% | 81.1% | 0.0% | — | — | 100.0% | 100.0% | pending_review |
| Qwen3-8B Q4_K_M — frozen v1 control | smoke | adreno_opencl | 8 | 67.1% | 100.0% | 68.2% | 12.5% | 0.0% | 0.0% | 100.0% | 100.0% | pending_review |
| Qwen3-8B Q4_K_M — frozen v1 control | development | adreno_opencl | 16 | 45.0% | 93.8% | 64.9% | 12.5% | 0.0% | 0.0% | 100.0% | 100.0% | pending_review |
| Gemma 3 12B IT QAT Q4_0 | validity | cpu_arm64 | 1 | 50.0% | 0.0% | 90.0% | 0.0% | — | — | 0.0% | 0.0% | pending_review |
| Gemma 3 12B IT QAT Q4_0 | validity | adreno_opencl | 1 | 75.0% | 0.0% | 97.1% | 0.0% | — | — | 100.0% | 0.0% | pending_review |
| Gemma 3 12B IT QAT Q4_0 | smoke | adreno_opencl | 3 | 41.7% | 33.3% | 57.2% | 0.0% | — | 0.0% | 66.7% | 33.3% | reject |
| gpt-oss-20b native MXFP4 | validity | cpu_arm64 | 1 | 50.0% | 100.0% | 65.8% | 0.0% | — | — | 100.0% | 100.0% | pending_review |
| gpt-oss-20b native MXFP4 | validity | adreno_opencl | 1 | 0.0% | 0.0% | 0.0% | 0.0% | — | — | 0.0% | 0.0% | reject |
| Phi-4 14B Q4_K_S | validity | cpu_arm64 | 1 | 50.0% | 100.0% | 71.4% | 0.0% | — | — | 100.0% | 100.0% | pending_review |
| Phi-4 14B Q4_K_S | validity | adreno_opencl | 1 | 25.0% | 100.0% | 80.0% | 0.0% | — | — | 100.0% | 100.0% | pending_review |
| Granite 3.3 8B Instruct Q4_K_M | validity | cpu_arm64 | 1 | 50.0% | 0.0% | 79.2% | 0.0% | — | — | 100.0% | 0.0% | pending_review |
| Granite 3.3 8B Instruct Q4_K_M | validity | adreno_opencl | 1 | 50.0% | 0.0% | 57.5% | 0.0% | — | — | 100.0% | 0.0% | pending_review |

## Gate-aware quality leaderboard

Rows use each model's furthest completed stage; stages with different question counts are not treated as directly interchangeable quality estimates.

| Model | Furthest stage | Backend | N | Coverage | Citation valid | Schema valid | TTFT p50 (s) | Latency p50 (s) | Eligibility | Outcome |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| Qwen3-8B Q4_K_M — frozen v1 control | development | adreno_opencl | 16 | 45.0% | 93.8% | 100.0% | 65.95 | 104.84 | retained control | Only model to pass smoke and complete development |
| Gemma 3 12B IT QAT Q4_0 | smoke | adreno_opencl | 3 | 41.7% | 33.3% | 66.7% | 81.20 | 122.79 | ineligible | smoke citation gate unreachable |
| gpt-oss-20b native MXFP4 | validity | adreno_opencl | 1 | 0.0% | 0.0% | 0.0% | 98.54 | 136.08 | ineligible | opencl invalid output schema and cpu latency unacceptable |
| Phi-4 14B Q4_K_S | validity | adreno_opencl | 1 | 25.0% | 100.0% | 100.0% | 238.49 | 274.98 | ineligible | unacceptable latency and clearly worse quality than qwen control |
| Granite 3.3 8B Instruct Q4_K_M | validity | adreno_opencl | 1 | 50.0% | 0.0% | 100.0% | 94.34 | 122.87 | ineligible | systematic invalid citation metadata and worse latency quality than qwen control |

## Winners and Answering Baseline v2 recommendation

- **Best quality model:** Qwen3-8B Q4_K_M control. It is the only model that passed smoke and completed the frozen development benchmark.
- **Best speed model (eligible models):** Qwen3-8B Q4_K_M control. Its OpenCL validity TTFT/latency were 73.29/100.70 s, faster than every required alternative on the identical case. Gemma had the fastest raw CPU validity latency, but is ineligible because it failed citation reliability.
- **Best balanced model:** Qwen3-8B Q4_K_M control, based on its only successful combination of schema reliability, citations, coverage, latency, and memory.
- **Comparison against Qwen:** Gemma failed the smoke citation gate; gpt-oss produced invalid OpenCL JSON and excessive latency; Phi-4 was markedly slower with lower coverage; Granite systematically emitted invalid citation page metadata and was slower/less complete.
- **Blinded human review:** no packet was generated because no alternative reached development/finalist status. The packet builder requires at least two same-stage runs with identical evidence, which prevents presenting a one-model packet as a blinded comparison.
- **Holdout:** untouched. No alternative satisfied the finalist gate.
- **Answering Baseline v2 recommendation:** do not advance any tested candidate. Retain the frozen Answering Baseline v1/Qwen3-8B control. The optional Phi-4 Mini and Mistral Small candidates remain separate future experiments requiring their own artifact review and approval.
