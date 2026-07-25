# TeachingAssistantV2 hardware-acceleration experiment

Status: **successful GPU proof**

This area is isolated from the frozen v1 answering configuration. Nothing under
`config/*_baseline_v1.*`, `reports/*_baseline_v1/`, or the production offline
provider is changed by this experiment.

## Proposed first proof

- Runtime: official `llama.cpp` build `b10107`, native Windows ARM64,
  `OpenCL Adreno` backend.
- Runtime archive: `llama-b10107-bin-win-opencl-adreno-arm64.zip`,
  12,752,128 bytes, SHA-256
  `1adca072b5ef8203409bb75258faa5ab7476d93fcf1bd38fbc44cb68cb3b1eef`.
- Model: `Qwen/Qwen2.5-0.5B-Instruct-GGUF`.
- Model file: `qwen2.5-0.5b-instruct-q4_0.gguf`, approximately 429 MB.
- Model SHA-256:
  `7671c0c304e6ce5a7fc577bcb12aba01e2c155cc2efd29b2213c95b18edaf6ed`.
- Format/quantization: GGUF, Q4_0.
- Device: `GPUOpenCL` on the Qualcomm Adreno X1-85.

This is the smallest credible first path because upstream llama.cpp now:

1. ships a prebuilt native ARM64 Adreno package;
2. explicitly lists Windows 11 ARM64, Snapdragon X Elite, and Adreno X1-85 as
   verified;
3. supports Q4_0 directly in the OpenCL backend; and
4. avoids the x64 emulation and 8B model used by the earlier failed Vulkan
   probe on this machine.

The approved artifacts were downloaded, checksum-verified, and exercised. All
four required proof gates passed. See `findings/final_report.md`.

The same proof was subsequently repeated with cached Qwen3 8.19B and 14.77B
Q4_K_M models. See `findings/model_scaling_8b_14b.md` and
`findings/model_scaling_results.json`.

The integrated production `opencl_gpu` strategy was then exercised with the
shared Qwen3-8B artifact and frozen request settings. See
`findings/production_pipeline_validation.md`.

## Required proof

The run is accepted only if all of these are captured:

1. coherent text answering a fixed prompt;
2. runtime logs naming the OpenCL platform/device and reporting model-layer
   offload to `GPUOpenCL`;
3. per-process Windows GPU-engine utilization sampled during inference;
4. GPU memory and process working-set samples;
5. a CPU-only control using the same model and prompt;
6. explicit rejection if logs show partial/unexpected CPU placement, GPU
   counters stay at idle, or output is corrupted.

## Layout

- `findings/final_report.md`: primary 0.5B GPU proof and CPU comparison.
- `findings/results.json`: machine-readable primary-proof results.
- `findings/model_scaling_8b_14b.md`: larger-model compatibility and
  performance comparison.
- `findings/model_scaling_results.json`: machine-readable 8B/14B results.
- `findings/discovery.md` and `findings/platform_matrix.md`: device inventory
  conclusions and backend selection rationale.
- `scripts/`: reproducible setup, inventory, measurement, validation, and
  summarization commands.
- `logs/discovery/` and `logs/baseline-validation/`: compact evidence retained
  in Git.
- `logs/runs/`: raw server output, responses, timestamps, and GPU samples;
  retained locally and ignored by Git.
- `runtime/`: approved runtime archive, extraction, and OpenCL kernel cache;
  retained locally and ignored by Git.
- `models/`: approved experiment-only model files; retained locally and
  ignored by Git.

## Version-control policy

The repository retains the scripts and compact evidence required to understand
and reproduce the result. Downloaded executables, GGUF weights, compiled
OpenCL kernels, and verbose per-run logs are excluded because they are large
or machine-specific. Their exact versions, checksums, selected run names, and
derived measurements are recorded in `experiment_manifest.json` and the
machine-readable files under `findings/`.

## Reproduction sequence after approval

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_opencl_proof.ps1 -Approved
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_opencl_proof.ps1 -Mode gpu
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_opencl_proof.ps1 -Mode cpu
python .\scripts\summarize_opencl_proof.py
```

The setup script refuses to download unless the explicit `-Approved` switch is
present. Both downloads are checksum-verified before extraction or use.

To test an already-present GGUF without downloading it, pass `-ModelPath` and
an identifying `-RunLabel`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_opencl_proof.ps1 -Mode gpu -ModelPath "X:\path\model.gguf" -RunLabel model-name
```

The summarizer refuses to mark success unless the GPU run has valid-looking
text, native ARM64 metadata, OpenCL/Adreno initialization logs, complete layer
offload evidence, and non-idle per-process GPU counters.
