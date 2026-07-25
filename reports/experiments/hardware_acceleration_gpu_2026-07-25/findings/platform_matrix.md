# Platform comparison

| Path | Installed readiness | Small-model availability | Main risk | Decision |
|---|---|---|---|---|
| Native ARM64 llama.cpp OpenCL Adreno | Matching OpenCL driver is installed; upstream prebuilt exists | Official Qwen2.5 0.5B GGUF Q4_0, about 429 MB | New backend; performance is unknown | **First proof** |
| x64 llama.cpp Vulkan | Vulkan works and an older probe initialized the GPU | Same small GGUF is usable | Earlier 8B run produced corrupted output under x64 emulation | Fallback investigation |
| Native ARM64 llama.cpp Vulkan | Vulkan driver works | Same GGUF | No official Windows ARM64 Vulkan build; needs a compiler and Vulkan SDK | Defer |
| Foundry Local / Windows ML | Windows AI and DirectML components exist | Catalog includes Qwen2.5 0.5B | Current provider/device selection on ARM64 may prefer QNN NPU; additional install and catalog downloads | Second GPU option |
| ORT GenAI DirectML | Prior x64 environment and a 4B export exist | Smaller model would need a matching DirectML ONNX export | Prior Gemma export generated corrupted tokens; DirectML is in sustained engineering | Defer |
| Qualcomm QNN / Genie | NPU driver and Windows QNN workload packages exist | Ready-made bundles tend to start around 3B/4B | Major QAIRT SDK/model bundle; targets NPU, not the requested first GPU proof | Investigate after GPU |

## Why Q4_0

The upstream OpenCL backend explicitly supports Q4_0 and is optimized for
Adreno. Q4_0 is selected over Q4_K_M for the first correctness probe to keep the
kernel path simple and distinct from the earlier corrupted Q4_K_M Vulkan run.
If Q4_0 succeeds, Q4_K_M can be tested as a quality/performance follow-up.
