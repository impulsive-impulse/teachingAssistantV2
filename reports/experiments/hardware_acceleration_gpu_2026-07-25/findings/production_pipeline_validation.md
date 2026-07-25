# Production offline OpenCL integration validation

Verdict: **pass**

The production `OfflineRuntimeManager` was exercised after implementing the
typed CPU/OpenCL strategy gate. This is distinct from the standalone hardware
proof: it uses the application's artifact registry, setup workflow, shared
generation request builder, resident server lifecycle, current-session log
parser, streamed response handling, and runtime diagnostics.

## Configuration

```yaml
offline_generation:
  backend: opencl_gpu
  allow_fallback: false
```

- Model: the existing shared `Qwen3-8B-Q4_K_M.gguf`; no model copy or model
  download was performed.
- Model SHA-256:
  `d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785`.
- Runtime: official native Windows ARM64 llama.cpp b10107 OpenCL/Adreno
  package, installed and manifest-verified below the Git-ignored
  `app_data/models/llama.cpp/opencl_gpu/` directory.
- Frozen request settings remained at context 8192, seed 42, temperature 0,
  384 maximum output tokens, thinking disabled, and JSON response mode.

## Initialization result

```text
requested_backend: opencl_gpu
active_backend: opencl_gpu
runtime_build: 10107
selected_device: Qualcomm(R) Adreno(TM) X1-85 GPU
offloaded_layer_count: 37
expected_layer_count: 37
initialization_status: ready
fallback_used: false
load_seconds: 45.29
```

The manager accepted the backend only after the current process session log
proved the exact Adreno device, Adreno-optimized kernels, and complete 37/37
Qwen3-8B layer offload.

## Streamed output

```json
{
  "status": "insufficient",
  "answer": "GPU pipeline active.",
  "selected_evidence_ids": [],
  "citations": [],
  "missing_information": ["No textbook evidence was supplied."]
}
```

Resolved provider identity:

```text
Qwen3-8B-Q4_K_M.gguf · llama.cpp b10107 · opencl_gpu
```

The test deliberately kept fallback disabled. An earlier deliberately strict
loader-message check rejected the healthy process, and the runtime failed
closed instead of switching to CPU. The validator was corrected to use the
authoritative requirements: verified runtime DLL checksums plus runtime log
evidence for device selection, Adreno kernels, and full layer offload.
