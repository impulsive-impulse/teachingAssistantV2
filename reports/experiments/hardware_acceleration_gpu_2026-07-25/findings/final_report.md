# Native ARM64 OpenCL/Adreno LLM proof

Verdict: **success**

A local instruction-tuned LLM generated valid text on the Qualcomm Adreno
X1-85 through llama.cpp's native Windows ARM64 OpenCL backend. The paired
control used the same executable, model, prompt, and generation settings
with zero GPU layers.

## Success gates

| Gate | Result |
|---|---:|
| valid text | PASS |
| gpu backend initialized | PASS |
| gpu activity measured | PASS |
| no silent cpu fallback | PASS |

## Selected stack

| Component | Selection |
|---|---|
| Device | Qualcomm Adreno X1-85, driver 31.0.133.1 |
| Runtime | llama.cpp b10107 (`c0bc8591e`), native ARM64 PE (`0xAA64`) |
| Backend | OpenCL 3.0 QUALCOMM build 851.0, Adreno-optimized kernels |
| Model | Qwen2.5-0.5B-Instruct |
| Format | GGUF V3, Q4_0 |
| Model file | `qwen2.5-0.5b-instruct-q4_0.gguf`, 428,730,208 bytes |
| Context | 512 tokens |

Artifact checksums:

- Runtime archive: `1adca072b5ef8203409bb75258faa5ab7476d93fcf1bd38fbc44cb68cb3b1eef`.
- Model: `7671c0c304e6ce5a7fc577bcb12aba01e2c155cc2efd29b2213c95b18edaf6ed`.

## Installation and commands

No SDK was installed. The experiment used the official prebuilt runtime and
the official Qwen GGUF. Reproduction from this directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_opencl_proof.ps1 -Approved
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_opencl_proof.ps1 -Mode gpu -Port 18085 -Prompt "Count from 1 to 200 in order, separated by commas, with no explanation." -MaxTokens 512
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_opencl_proof.ps1 -Mode cpu -Port 18086 -Prompt "Count from 1 to 200 in order, separated by commas, with no explanation." -MaxTokens 512
python .\scripts\summarize_opencl_proof.py
```

## Output validity

- Short correctness prompt: `Answer with only the city name: What is the capital of France?`
- Short GPU response: **Paris**
- Performance-run GPU output: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100
- Matching CPU output: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100

The performance prompt asked for 1 through 200; both paths stopped cleanly
after the correct uninterrupted sequence 1 through 100. The separate
objective check returned exactly "Paris". No repeated-character or
`<unused...>` corruption occurred.

## Performance and utilization

| Metric | GPUOpenCL | CPU control |
|---|---:|---:|
| Model load | 21.163 s | 1.391 s |
| Prompt processing | 775.11 tok/s | 261.54 tok/s |
| Token generation | 86.35 tok/s | 25.91 tok/s |
| Request wall time | 4.608 s | 15.291 s |
| Peak process working set | 1313.69 MiB | 1142.71 MiB |
| Peak process private bytes | 999.77 MiB | 848.54 MiB |
| Peak GPU engine activity during inference | 92.18% | 0.00% |
| Peak GPU committed memory counter | 745.14 MiB | 392.01 MiB |

Generation accelerated by **3.33x**
and request wall time improved by **3.32x**.
The sampler captured 2 GPU-process
samples inside the recorded inference interval; the peak was on the
`engtype_3d` engine.

The CPU control's process memory counter still showed shared GPU-addressable
memory because the OpenCL-capable runtime enumerates the adapter, but it had
0% GPU engine activity throughout inference and its logs assigned 0/25
layers to GPU.

## No-silent-fallback evidence

- Executable PE machine is `0xAA64` (native ARM64, not x64 emulation).
- Command explicitly selected `--device GPUOpenCL --n-gpu-layers 99`.
- Runtime log loaded `ggml-opencl.dll` and selected the Qualcomm Adreno X1-85.
- Logs assigned layers 0-24 to `GPUOpenCL` and reported `offloaded 25/25 layers to GPU`.
- OpenCL buffers: 330.25 MiB model, 6.00 MiB KV cache, 8.57 MiB compute.
- Windows counters measured 92.18% GPU activity
  during the timestamped inference interval; the CPU control measured 0%.
- The same workload ran 3.33x faster on GPU.

This proves there was no silent whole-model CPU fallback. It does not claim
zero CPU participation: llama.cpp logged a 73.03 MiB CPU-mapped/token-embedding
allocation, a 1.00 MiB CPU compute buffer, and host-side sampling/orchestration.

## Evidence locations

- GPU performance run: `20260725-123456-gpu`.
- CPU control run: `20260725-123553-cpu`.
- Short correctness run: `20260725-123359-gpu`.
- `results.json` contains the machine-readable verdict and derived metrics.
- Raw server logs, responses, commands, timestamps, and counter samples are
  retained under `logs/runs/`.

## Scope

The frozen Generation Baseline v1 remains CPU-only and unchanged. This proof
is an isolated feasibility result; it does not replace the production
Qwen3-8B answering profile. NPU/Genie work was intentionally deferred until
after a successful GPU proof.
