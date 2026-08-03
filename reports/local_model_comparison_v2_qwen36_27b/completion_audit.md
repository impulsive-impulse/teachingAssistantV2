# Completion audit

## Frozen controls

The experiment used a new versioned directory and did not alter the production
v1 baseline files. The configured retrieval, generation, benchmark, historical
experiment, evidence-source, and evidence-snapshot hashes were recomputed at
completion and matched their recorded values.

## Artifact and runtime

- The exact 19,095,766,304-byte Qwen3.6-27B Q4_K_M artifact is stored under
  Git-ignored `app_data`; its SHA-256 matches the pinned registry value.
- Native ARM64 CPU and Adreno OpenCL validity runs both completed with valid
  five-key structured output and valid citation metadata.
- The OpenCL manifest records the Qualcomm Adreno X1-85, optimized Adreno
  kernels, and full 65/65 layer offload. Silent CPU fallback was ruled out.

## Successive narrowing

The candidate was rejected after validity because OpenCL TTFT/latency were
182.23/348.72 seconds and measured memory was 36.57 GiB host RSS plus 18.35 GiB
sampled GPU-local memory. The frozen Qwen3-8B reference was materially faster
and smaller. Smoke and development were therefore not run, no blinded packet
was warranted, and the holdout remains untouched.

## Deliverables

- Compatibility matrix: `compatibility_matrix.md`
- CPU/GPU metrics, quality leaderboard, winners, and v2 recommendation:
  `benchmark_tables.md`
- Full rationale: `decisions.md`
- Exact artifact and measured metrics: `artifact_registry.json`

## Verification

- All six configured frozen-input hashes matched at completion.
- Focused comparison suite: 16 passed.
- Full project suite: 226 passed with one pre-existing Starlette deprecation
  warning.
- `git diff --check`: passed.
- The verified model path is confirmed Git-ignored.
- Redundant multipart download fragments were left untouched after the local
  command safety guard declined their removal; the verified artifact remains
  intact.
