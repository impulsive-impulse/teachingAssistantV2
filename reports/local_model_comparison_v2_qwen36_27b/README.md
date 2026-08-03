# Local Model Comparison v2 — Qwen3.6-27B

This isolated experiment compares Qwen3.6-27B Q4_K_M against the frozen
Qwen3-8B Answering Baseline v1 control. It reuses the exact Retrieval Baseline
v1 evidence, generation benchmark, structured answer schema, and citation
validator without modifying any production baseline or the completed Local
Model Comparison v1 directory.

## Candidate

- Repository: `ggml-org/Qwen3.6-27B-GGUF`
- Revision: `8a7ee08e8b9bfb857107ecc25a5599d2f38b76f8`
- Artifact: `Qwen3.6-27B-Q4_K_M.gguf`
- Size: 19,095,766,304 bytes (17.784 GiB)
- SHA-256: `65b753ea835627f7b511143c6ceb976525c7f21f5df8c664bc0a9c23d1c49921`
- License: Apache-2.0
- Vision projector: excluded because the benchmark is text-only

## Gate order

1. Checksum and tensor-validity verification.
2. Native ARM64 CPU one-question validity run.
3. Adreno OpenCL one-question validity run with explicit device and offload
   evidence.
4. Eight-question smoke stage if validity output and latency are acceptable.
5. Frozen sixteen-question development stage only if smoke passes.
6. Blinded human review before any untouched holdout run.

Weights and runtime binaries remain under Git-ignored `app_data`.

## Outcome

Testing stopped after the one-question CPU and Adreno OpenCL validity probes.
Both backends produced valid structured output, and the GPU log confirmed the
Qualcomm X1-85, Adreno-optimized kernels, and 65/65 layer offload. The OpenCL
run nevertheless took 182.23 seconds to first token and 348.72 seconds total,
versus 73.29 and 100.70 seconds for the frozen Qwen3-8B validity control. It
also peaked at 36.57 GiB host RSS and 18.35 GiB sampled GPU-local memory.

Qwen3.6-27B is rejected for unacceptable latency and memory on this machine.
The smoke, development, blinded-review, and holdout gates remain untouched.
Qwen3-8B remains the best quality, speed, and balanced eligible model, and no
future Answering Baseline v2 promotion is recommended from this experiment.
