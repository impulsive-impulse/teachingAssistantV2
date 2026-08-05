# Local Model Comparison v3 — Sarvam-30B

This isolated experiment evaluates the official Sarvam-30B Q4_K_M split GGUF
against the frozen Qwen3-8B Answering Baseline v1 control. It does not modify
production baselines, retrieval, benchmark questions, saved top-five evidence,
structured-answer schema, or citation validation.

## Artifact

- Repository: `sarvamai/sarvam-30b-gguf`
- Revision: `54e15edbbcb112e7d6c69b612e5041973e953c2f`
- Artifact: six `sarvam-30b-Q4_K_M` GGUF shards
- Total size: 19,570,785,664 bytes (18.227 GiB)
- License: Apache-2.0
- Storage: Git-ignored `app_data/models/generation/sarvam-30b-q4_k_m`
- Integrity: all six file sizes and SHA-256 checksums verified

## Gate order

1. Load shard 1 with the pinned ARM64 OpenCL llama.cpp runtime; llama.cpp must
   discover the other five shards.
2. Run the one-question output-validity gate directly on Adreno, as requested.
3. Require logs naming the X1-85, Adreno-optimized kernels, and nonzero layer
   offload. Reject silent CPU fallback.
4. Stop for invalid/corrupt output, incomplete GPU proof, unsafe memory use, or
   unacceptable latency.
5. Run the eight-question smoke stage only if validity is promising. Development,
   blinded human review, and untouched holdout remain successive gates.

CPU inference is deliberately deferred for this first probe. Results and the
decision will be recorded here after the GPU validity run.

## Outcome

The pinned OpenCL runtime recognized the split GGUF as `bailingmoe2`, selected
the Qualcomm Adreno X1-85, enabled Adreno-optimized kernels, and reported full
20/20 layer offload. This was not silent CPU fallback.

The server did not become inference-ready. It exceeded the harness's 180-second
startup limit and continued returning HTTP 503 while its working set grew to an
observed 30.08 GiB. System free RAM fell to 1.88 GiB, so the surviving server
process was terminated for memory safety. The log declared an 18,081.84 MiB
OpenCL model buffer. No generation request was sent, so output validity and
quality are unmeasured rather than failed.

Sarvam-30B Q4_K_M is rejected on this Adreno machine for unacceptable OpenCL
startup latency and memory pressure. Smoke, development, blinded review, and
holdout were not run. Qwen3-8B remains the eligible production control.
