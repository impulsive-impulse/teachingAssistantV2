# Decision log

## 2026-07-25 — Experiment controls

- Created a separate `local_model_comparison_v1` report tree.
- Kept every production v1 baseline and historical generation run read-only.
- Selected the historical Qwen3-8B P1 development run as the source of the
  exact frozen top-five evidence snapshot.
- Adopted successive narrowing and reserved the 24-question holdout for
  finalists only.

## 2026-07-25 — Gemma 3 12B artifact gate

- Verified the official repository and pinned revision:
  `google/gemma-3-12b-it-qat-q4_0-gguf` at
  `7929e34ac7c459bbfd1f38d7358e6839f204578b`.
- Selected only `gemma-3-12b-it-q4_0.gguf` for the text benchmark. The separate
  0.796 GiB vision projector is not required and will not be downloaded.
- Classified local educational evaluation as license-compatible with
  conditions under the Gemma Terms. Production distribution/hosting would
  require the stated downstream terms and notice obligations plus legal
  sign-off.
- Confirmed Q4_0, Windows ARM64, and Adreno X1-85 are listed as supported by
  the installed llama.cpp/OpenCL line. Actual device selection and layer
  offload still must be proven from each run log.
- A dry-run download was rejected because the repository requires manual
  approval. No model data was downloaded.
- Next action: user accepts the Gemma terms/requests repository access and
  explicitly approves the 7.519 GiB weight download.

## 2026-07-25 — Gemma download approval

- The user explicitly approved the Gemma artifact download.
- The approved scope is the pinned 7.519 GiB text GGUF only; the vision
  projector remains excluded.
- A new authenticated dry run still returned `Access denied. This repository
  requires approval.` The download remains blocked until the Hugging Face
  account `AmanImpulse` accepts the Gemma terms and is granted access.

## 2026-07-25 — Gemma repository access granted

- Rechecked the authenticated `AmanImpulse` account.
- The pinned dry run succeeded and resolved exactly one 8.1 GB decimal
  (7.519 GiB) file.
- Started the previously approved text-only artifact download. The separate
  vision projector remains excluded.

## 2026-07-25 — Gemma artifact verified

- Download completed at exactly 8,074,473,920 bytes.
- Local SHA-256 matched the pinned Hub LFS digest:
  `dd53172ff3a7b1b16c8fb3d944b87f42a6228ff2de3825b8813ae90d988434cd`.
- `hf cache verify` checked the pinned repository revision. Its warning about
  three missing remote files is expected because the approved download
  intentionally excluded README metadata and the vision projector.
- Artifact gate passed. Next stage is one-question native ARM64 CPU validity.

## 2026-07-25 — Gemma successive-narrowing decision

- Native ARM64 CPU validity produced non-corrupt structured output, but its
  citation was invalid. TTFT was 113.27 s, total latency 135.09 s, and peak
  process RSS 14.80 GiB.
- Adreno OpenCL validity explicitly selected the X1-85, used the optimized
  Adreno kernels, and offloaded all 49 layers. Output remained citation-invalid.
  TTFT was 82.36 s, total latency 108.96 s, peak process RSS 17.20 GiB, and
  sampled local GPU memory 8.94 GiB.
- The OpenCL smoke stage stopped after question 3 of 8 because the required
  87.5% citation-validity gate had become mathematically unreachable. One of
  three outputs was fully schema/citation valid; one was invalid JSON.
- Decision: **reject Gemma 3 12B IT QAT Q4_0**. Do not run the development
  benchmark or untouched holdout.

## 2026-07-25 — gpt-oss-20b artifact gate

- Verified the llama.cpp project's conversion repository and pinned revision:
  `ggml-org/gpt-oss-20b-GGUF` at
  `c9a07b972b8979719fd97b8ff2c10dc79ebf5d26`.
- Selected exactly `gpt-oss-20b-MXFP4.gguf`: 12,109,566,624 bytes
  (11.278 GiB), SHA-256
  `27cd6c432c7672cb812a92f611cf3ba7bbc35928262bb1e1253ff4ee6ae35901`.
- Apache-2.0 is compatible with the educational experiment and future
  commercial use subject to its notice and attribution requirements.
- The installed llama.cpp line supports gpt-oss on ARM64 CPU. Its pinned
  OpenCL documentation lists Windows ARM64/Snapdragon X Elite, Adreno X1-85,
  and MXFP4 as supported. Actual device selection and layer offload remain
  mandatory runtime gates.
- Use the embedded Harmony template, OpenAI's recommended temperature 1.0 and
  top-p 1.0, and the official reference client's low reasoning-effort default.
- A no-download dry run resolved exactly one 12.1 GB decimal artifact.
  Awaiting explicit approval before download.

## 2026-07-25 — gpt-oss-20b download approval

- The user explicitly approved the pinned gpt-oss artifact.
- The approved scope is exactly the 11.278 GiB native MXFP4 GGUF recorded
  above. No alternative quantization or additional model file is included.

## 2026-07-26 — gpt-oss-20b artifact verified

- The Hub fallback stream was externally bandwidth-limited and did not reuse
  its randomized temporary filename after a restart. The experiment preserved
  the existing prefix and completed the artifact using four disjoint HTTP
  ranges; every response was required to match its exact `Content-Range`.
- The ordered assembly completed at exactly 12,109,566,624 bytes.
- Its full SHA-256 matched the pinned Hub LFS digest:
  `27cd6c432c7672cb812a92f611cf3ba7bbc35928262bb1e1253ff4ee6ae35901`.
- The verified blob and model link remain under Git-ignored `app_data`.
  Artifact gate passed; next stage is native ARM64 CPU validity.

## 2026-07-26 — gpt-oss-20b successive-narrowing decision

- Native ARM64 CPU validity used the embedded Harmony template with low
  reasoning effort and produced valid JSON with an exact evidence citation.
  TTFT was 120.35 s, total latency 158.62 s, prompt throughput 38.03 tok/s,
  generation throughput 4.65 tok/s, and peak process RAM 22.29 GiB.
- Adreno OpenCL explicitly selected the X1-85, loaded the optimized Adreno
  kernels, and offloaded all 25 layers. TTFT improved to 98.54 s and generation
  throughput to 10.16 tok/s, but total latency remained 136.08 s.
- The OpenCL response consumed all 384 allowed output tokens inside an
  unterminated JSON string. It was schema-invalid and included verbose material
  not needed by the supplied evidence. Peak process RAM was 22.88 GiB and
  sampled local GPU memory was 11.36 GiB.
- Decision: **reject gpt-oss-20b native MXFP4** for invalid OpenCL output and
  unacceptable CPU latency. Do not run smoke, development, or holdout.

## 2026-07-26 — Phi-4 artifact gate

- Verified Microsoft's official `microsoft/phi-4-gguf` repository at pinned
  revision `6edc2ef6664b739a8e11e62f2672ff6afe0c15ac`.
- Selected the repository's llama.cpp-default 4-bit variant,
  `phi-4-Q4_K_S.gguf`: 8,440,762,560 bytes (7.861 GiB), SHA-256
  `8a8189132ef70cd737e136d38b706e8cb832f9cdf3c744547694769e9313550e`.
- The MIT licence is compatible with local educational evaluation and future
  commercial use subject to retaining the copyright and permission notice.
- Both installed llama.cpp builds list Phi-4 support. The pinned OpenCL
  documentation lists Windows ARM64/Snapdragon X Elite, Adreno X1-85, and
  Q4_K as supported. Actual device selection and layer offload remain runtime
  gates.
- Use the official embedded Phi-4 chat template. Microsoft's pinned
  `generation_config.json` specifies token IDs but no sampler values, so this
  experiment uses deterministic greedy decoding for structured reliability.
- A no-download dry run resolved exactly one 8.4 GB decimal artifact.
  Awaiting explicit approval before download.

## 2026-07-26 — Phi-4 download approval

- The user explicitly approved the pinned Phi-4 artifact.
- The approved scope is exactly the 7.861 GiB official Microsoft Q4_K_S GGUF.
- Download will begin after the active Qwen smoke control finishes so network
  and disk activity cannot contaminate its timing measurements.

## 2026-07-26 — Phi-4 download verification

- Downloaded only the approved `phi-4-Q4_K_S.gguf` artifact after the Qwen
  OpenCL smoke server exited.
- The completed file is exactly 8,440,762,560 bytes and independently verified
  as SHA-256
  `8a8189132ef70cd737e136d38b706e8cb832f9cdf3c744547694769e9313550e`.
- The verified weight is stored under Git-ignored `app_data/models/generation`;
  no production baseline file was modified.
- Advance to the basic CPU output-validity gate.

## 2026-07-26 — Phi-4 validity decision

- Native ARM64 CPU produced schema-valid, citation-valid output with no
  unsupported claims, but covered only 0.50 of the required points. TTFT was
  197.48 s and total latency was 258.08 s; peak process RAM was 17.13 GiB.
- Adreno OpenCL explicitly selected the X1-85, enabled optimized Adreno
  kernels, and offloaded all 41 layers. The response remained schema-valid and
  citation-valid, but required-point coverage fell to 0.25. TTFT was 238.49 s
  and total latency was 274.98 s; peak process RAM was 17.73 GiB and sampled
  local GPU memory was 9.66 GiB.
- On the identical validity case, the Qwen3-8B OpenCL control achieved 1.00
  required-point coverage, 73.29 s TTFT, and 100.70 s total latency.
- Decision: **reject Phi-4 14B Q4_K_S** for unacceptable latency and clearly
  worse validity-case quality than the Qwen control. Do not run smoke,
  development, or holdout.

## 2026-07-26 — Granite 3.3 8B artifact gate

- Verified IBM's official
  `ibm-granite/granite-3.3-8b-instruct-GGUF` repository at pinned revision
  `e40e9dd739c7be00fa965c16ce167088190ce114`.
- Selected the official repository's llama.cpp-default `Q4_K_M` artifact,
  `granite-3.3-8b-instruct-Q4_K_M.gguf`: 4,942,873,344 bytes (4.603 GiB),
  SHA-256
  `77bcee066a76dcdd10d0d123c87e32c8ec2c74e31b6ffd87ebee49c9ac215dca`.
- Apache-2.0 is compatible with the educational application and future
  commercial use, subject to its licence, notice, modification, and patent
  conditions.
- IBM's official GGUF page provides llama.cpp server and CLI commands for the
  exact Q4_K_M artifact. The pinned installed OpenCL documentation supports
  Windows ARM64, Adreno X1-85, and Q4_K. Actual device selection and layer
  offload remain runtime gates.
- Use the official embedded Granite chat template with its `thinking=false`
  option so output starts directly with the frozen JSON schema. The pinned
  generation config specifies token IDs but no sampler values, so the
  experiment retains deterministic greedy decoding.
- A no-download dry run resolved exactly one 4.9 GB decimal artifact.
  Awaiting explicit approval before download.

## 2026-07-26 — Qwen control development run

- Completed the same-harness Qwen3-8B Q4_K_M development control on all 16
  frozen development questions using the saved top-five evidence snapshot.
- Adreno X1-85 selection, optimized kernels, and 37/37 layer offload were
  confirmed from the runtime log. The run did not access the holdout.
- Schema-valid output rate was 1.00 and citation validity was 0.9375.
  Automatic required-point coverage was 0.45, citation-support token recall
  was 0.6492, unsupported-claim rate was 0.125, formula accuracy was 0.00,
  multi-passage completeness was 0.00, and there was one false-insufficient
  response. These lexical/heuristic results require blinded human review.
- Median TTFT was 65.95 s, median total latency was 104.84 s, mean prompt
  throughput was 67.05 tok/s, and mean generation throughput was 6.66 tok/s.
  Peak process RAM was 18.44 GiB and sampled local GPU memory was 5.95 GiB.
- Immutable result hashes: manifest
  `553a48ddc203586a6579d9d7c9475b27d9e90988c847fbfe02153878e1216d53`;
  results
  `ea500e9d08efa40385a29af1978d0d68cafea7b67510e74f2ff513c7dc8bce96`.

## 2026-07-26 — Granite download approval

- The user explicitly approved the pinned Granite artifact download.
- The approved scope is exactly IBM's 4.603 GiB
  `granite-3.3-8b-instruct-Q4_K_M.gguf` at revision
  `e40e9dd739c7be00fa965c16ce167088190ce114`.
- No other Granite quantization or repository artifact is approved.

## 2026-07-26 — Granite download verification

- Downloaded only the approved
  `granite-3.3-8b-instruct-Q4_K_M.gguf` artifact.
- The completed file is exactly 4,942,873,344 bytes and independently verified
  as SHA-256
  `77bcee066a76dcdd10d0d123c87e32c8ec2c74e31b6ffd87ebee49c9ac215dca`.
- The verified weight is stored under Git-ignored `app_data/models/generation`;
  no production baseline file was modified.
- Advance to native ARM64 output-validity testing.

## 2026-07-26 — Granite validity decision

- Native ARM64 CPU emitted parseable JSON but failed the frozen citation
  validator: it copied textbook page 22 into both page fields for E1, whose
  supplied metadata is PDF page 31 and textbook page 22. Required-point
  coverage was 0.50, TTFT was 210.67 s, total latency was 259.12 s, and peak
  process RAM was 10.39 GiB.
- Adreno OpenCL explicitly selected the X1-85, enabled optimized kernels, and
  offloaded all 41 layers. It repeated the identical invalid citation
  metadata. Required-point coverage remained 0.50, TTFT was 94.34 s, total
  latency was 122.87 s, peak process RAM was 11.09 GiB, and sampled local GPU
  memory was 6.33 GiB.
- On the identical validity case, the Qwen OpenCL control produced fully valid
  citations, achieved 1.00 required-point coverage, 73.29 s TTFT, and 100.70 s
  total latency.
- Decision: **reject Granite 3.3 8B Instruct Q4_K_M** for systematic invalid
  citation metadata and worse latency/quality than the Qwen control. Do not
  run smoke, development, or holdout.
