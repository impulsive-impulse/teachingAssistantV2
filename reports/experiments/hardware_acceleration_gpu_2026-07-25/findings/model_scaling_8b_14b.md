# Qwen3 8B and 14B Adreno compatibility extension

Verdict: **both models produced valid output with complete Adreno offload**

This extension tests whether the successful 0.5B proof generalizes to two
larger, already-cached model artifacts. It does not claim that the original
test validates every local LLM. Compatibility is specific to the combination
of model architecture, GGUF representation, quantization, llama.cpp build,
backend, and driver.

## Fixed workload

- Prompt: `Count from 1 to 100 in order, separated by commas, with no explanation. /no_think`
- Expected output: the exact comma-separated integer sequence 1 through 100.
- Runtime: llama.cpp b10107 (`c0bc8591e`), native Windows ARM64 (`0xAA64`).
- GPU backend: OpenCL 3.0 QUALCOMM build 851.0 with Adreno-optimized kernels.
- GPU command settings: `--device GPUOpenCL --n-gpu-layers 99`.
- CPU control: the same executable, model, prompt, seed, context, batch, and
  generation settings with `--n-gpu-layers 0`.

Both GPU runs and both CPU controls returned the exact expected sequence,
296 generated tokens, with no corruption or reasoning preamble.

## Models

| Model artifact | Metadata parameters | Format | File size | SHA-256 |
|---|---:|---|---:|---|
| `Qwen3-8B-Q4_K_M.gguf` | 8.19 B | GGUF V3, Q4_K_M | 5,027,783,488 bytes | `d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785` |
| `Qwen3-14B-Q4_K_M.gguf` | 14.77 B | GGUF V3, Q4_K_M | 9,001,752,960 bytes | `500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0` |

No model was downloaded for this extension. Both files were reused read-only
from existing local caches.

## Results

| Model | Mode | Valid | Layers on GPU | Load | Prompt | Generation | Request wall | GPU peak | GPU committed peak |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen3 8B Q4_K_M | GPUOpenCL | PASS | 37/37 | 67.474 s | 67.572 tok/s | 9.716 tok/s | 30.966 s | 98.34% | 4,982.23 MiB |
| Qwen3 8B Q4_K_M | CPU control | PASS | 0/37 | 18.223 s | 36.286 tok/s | 9.526 tok/s | 32.002 s | 0.00% | 392.01 MiB |
| Qwen3 14B Q4_K_M | GPUOpenCL | PASS | 41/41 | 106.914 s | 41.903 tok/s | 4.941 tok/s | 60.691 s | 99.01% | 8,731.48 MiB |
| Qwen3 14B Q4_K_M | CPU control | PASS | 0/41 | 24.191 s | 47.118 tok/s | 8.210 tok/s | 36.772 s | 0.00% | 392.01 MiB |

For 8B, GPU generation throughput was effectively tied with CPU
(1.02x GPU/CPU), while prompt processing was 1.86x faster and request wall
time was 3% lower. For 14B, GPU generation reached only 0.60x CPU throughput
and the request took 1.65x as long. First-load OpenCL allocation and kernel
preparation were also substantially slower than CPU mapping.

These are compatibility successes, not performance wins for large Qwen3
models on this llama.cpp/OpenCL build.

## No-silent-fallback evidence

Qwen3 8B:

- Runtime selected `Qualcomm(R) Adreno(TM) X1-85 GPU`.
- Log reported `offloaded 37/37 layers to GPU`.
- Allocations included a 4,455.47 MiB OpenCL model buffer, 72.00 MiB OpenCL
  KV buffer, and 24.13 MiB OpenCL compute buffer.
- Windows per-process counters measured 98.34% peak GPU activity during the
  timestamped inference interval and 4,982.23 MiB committed GPU memory.
- The matched CPU control reported `offloaded 0/37 layers to GPU` and measured
  0.00% GPU engine activity during inference.

Qwen3 14B:

- Runtime selected `Qualcomm(R) Adreno(TM) X1-85 GPU`.
- Log reported `offloaded 41/41 layers to GPU`.
- Allocations included an 8,161.89 MiB OpenCL model buffer, 80.00 MiB OpenCL
  KV buffer, and 33.13 MiB OpenCL compute buffer.
- Windows per-process counters measured 99.01% peak GPU activity during the
  timestamped inference interval and 8,731.48 MiB committed GPU memory.
- The matched CPU control reported `offloaded 0/41 layers to GPU` and measured
  0.00% GPU engine activity during inference.

There is still normal host participation for tokenization, sampling,
orchestration, and small CPU-mapped/compute allocations. The evidence rules
out silent whole-model CPU fallback; it does not assert zero CPU involvement.

## Reproduction

From the experiment directory, pass the desired external model to the extended
harness:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_opencl_proof.ps1 -Mode gpu -Port 18087 -ModelPath "<Qwen3-8B-Q4_K_M.gguf>" -RunLabel qwen3-8b-q4_k_m -Prompt "Count from 1 to 100 in order, separated by commas, with no explanation. /no_think" -MaxTokens 512
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_opencl_proof.ps1 -Mode cpu -Port 18088 -ModelPath "<Qwen3-8B-Q4_K_M.gguf>" -RunLabel qwen3-8b-q4_k_m -Prompt "Count from 1 to 100 in order, separated by commas, with no explanation. /no_think" -MaxTokens 512
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_opencl_proof.ps1 -Mode gpu -Port 18089 -ModelPath "<Qwen3-14B-Q4_K_M.gguf>" -RunLabel qwen3-14b-q4_k_m -Prompt "Count from 1 to 100 in order, separated by commas, with no explanation. /no_think" -MaxTokens 512
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_opencl_proof.ps1 -Mode cpu -Port 18090 -ModelPath "<Qwen3-14B-Q4_K_M.gguf>" -RunLabel qwen3-14b-q4_k_m -Prompt "Count from 1 to 100 in order, separated by commas, with no explanation. /no_think" -MaxTokens 512
```

Raw responses, server logs, timestamps, and GPU-process samples are retained
under `logs/runs/` in directories whose names begin `20260725-124448`,
`20260725-124704`, `20260725-124819`, and `20260725-125203`.

## What is and is not generalized

The accumulated evidence now validates this exact native ARM64 llama.cpp
OpenCL/Adreno path for:

- Qwen2 architecture with Q4_0 at 0.5B;
- Qwen3 architecture with Q4_K_M at 8.19B; and
- Qwen3 architecture with Q4_K_M at 14.77B.

It makes other GGUF models using operations and quantizations supported by
this backend more credible, but it does not pre-validate arbitrary GGUF,
ONNX, DLC, model architecture, quantization, context size, or multimodal
projector. Each materially different combination still needs at least a short
output, layer-placement log, utilization trace, and CPU control.

The frozen v1 CPU answering configuration was not changed.
