# Decision log

## 2026-08-03 — experiment opened

- Interpreted the requested “Qwen3.8-27B” as the verifiable official
  open-weight `Qwen/Qwen3.6-27B` release after reporting the name distinction.
- Selected the ggml-org Q4_K_M conversion pinned in `artifact_registry.json`.
- Recorded the user's instruction to proceed as approval for the disclosed
  19.1 GB public artifact.
- Kept the completed Local Model Comparison v1 and production baselines
  immutable by opening this new versioned directory.

## 2026-08-03 — artifact verified

- Downloaded only `Qwen3.6-27B-Q4_K_M.gguf`; the optional vision projector was
  not downloaded.
- Verified the exact 19,095,766,304-byte boundary and SHA-256
  `65b753ea835627f7b511143c6ceb976525c7f21f5df8c664bc0a9c23d1c49921`.
- Exposed the verified blob through a zero-copy hard link under Git-ignored
  `app_data/models/generation/qwen3.6-27b/`.

## 2026-08-04 — validity completed and candidate rejected

- Native ARM64 CPU inference produced valid structured JSON with valid
  citations, but required 396.70 seconds to first token and 578.22 seconds
  total, with 36.0 GiB peak RSS.
- Adreno OpenCL inference selected the Qualcomm X1-85, used the optimized
  Adreno kernels, and offloaded all 65/65 layers. Silent CPU fallback was
  therefore ruled out.
- The GPU result was also structurally valid, with 75% required-point
  coverage and 100% citation validity, but citation-support recall was only
  64.29%. The answer also introduced gall-bladder storage despite noting that
  this detail was not present in the supplied evidence, a human-review
  weakness not captured by the lexical unsupported-claim score.
- OpenCL performance remained unacceptable: 182.23-second TTFT, 348.72-second
  total latency, 26.82 prompt tokens/s, 1.87 generation tokens/s, 36.57 GiB
  peak RSS, and 18.35 GiB sampled GPU-local memory.
- Against the frozen Qwen3-8B OpenCL validity control (73.29-second TTFT and
  100.70-second latency), Qwen3.6-27B was 2.49x slower to first token and
  3.46x slower overall while using about 3.4x the measured host and GPU
  memory.
- Rejected after validity for unacceptable latency and memory. Per successive
  narrowing, smoke, development, blinded review, and holdout were not run.
