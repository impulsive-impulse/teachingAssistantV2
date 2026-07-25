# Discovery findings

Collected on 2026-07-25 before installing an SDK or downloading a model.

## Device and operating system

- Windows 11 Enterprise, version `10.0.26200`, build `26200`, ARM64.
- Snapdragon X Elite X1E80100, 12 physical/logical cores.
- 63.49 GiB installed unified memory.
- Qualcomm Adreno X1-85, healthy, driver `31.0.133.1`.
- Qualcomm Hexagon NPU, healthy, driver `30.0.220.3000`.

## Installed acceleration surfaces

- Qualcomm-signed `C:\Windows\System32\OpenCL.dll`, version `31.0.133.1`,
  exactly matching the display driver.
- Microsoft-signed Vulkan loader `1.3.300.0`.
- `vulkaninfo` enumerates the native Qualcomm proprietary Adreno driver as
  Vulkan 1.3.295, plus Microsoft Dozen adapters.
- DirectML ARM64 runtime `1.15.5` is present.
- Windows AI components are present, including `Microsoft.AIFabric.CBS.1.6`.
- Qualcomm QNN Windows workload packages `1.8.41.0` and framework `1.8.46.0`
  are installed.
- No `llama-cli`, ONNX Runtime GenAI, Foundry Local, QNN SDK/Genie CLI, CMake,
  Ninja, Visual Studio, or Clang command is currently on `PATH`.
- WSL is not installed.

## Existing local evidence

The tracked `reports/hardware_backend_v1/` audit previously tried:

- x64 llama.cpp Vulkan build `b10046` with Qwen3-8B Q4_K_M: the GPU backend
  ran and generated 15.26 tokens/s, but output was only repeated `G`
  characters, so it was invalid.
- x64 ORT GenAI DirectML `0.13.1` with Gemma 3 4B ONNX: 4.40 tokens/s, but the
  output was dominated by invalid `<unused...>` tokens.
- QNN and DirectML ONNX micrographs: provider loading was demonstrated, but
  these were not valid LLM generation proofs.

Those failures must not be reclassified as successes. They motivate a native,
small-model proof on the new upstream OpenCL backend.

## Frozen-v1 boundary

The production offline profile remains Qwen3-8B Q4_K_M through CPU-only
llama.cpp. Its configs, runtime setup, and provider implementation are outside
this experiment's write scope. Generation Baseline v1 validation and the
Retrieval Baseline v1 read-only checksum action both pass. The retrieval
`validate` action was found to refresh latency/provenance reports, so the
experiment wrapper deliberately uses `checksums` instead.

## Primary sources

- llama.cpp OpenCL backend:
  https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/OPENCL.md
- llama.cpp releases:
  https://github.com/ggml-org/llama.cpp/releases/tag/b10107
- Qwen2.5 0.5B official GGUF:
  https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF
- ONNX Runtime GenAI:
  https://github.com/microsoft/onnxruntime-genai
- ONNX Runtime DirectML:
  https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html
- Windows ML:
  https://learn.microsoft.com/windows/ai/new-windows-ml/overview
- Qualcomm Genie tutorial:
  https://github.com/quic/ai-hub-apps/blob/main/tutorials/llm_on_genie/README.md
