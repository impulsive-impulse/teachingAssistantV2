# Hardware-aware local inference audit

## Machine

- System: Microsoft Corporation Microsoft Surface Laptop, 7th Edition
- CPU: Snapdragon(R) X 12-core X1E80100 @ 3.40 GHz (12 cores)
- RAM: 63.49 GiB
- OS: Microsoft Windows 11 Enterprise build 26200 (ARM 64-bit Processor)
- GPU: Qualcomm(R) Adreno(TM) X1-85 GPU driver 31.0.133.1
- NPU: Snapdragon(R) X Elite - X1E80100 - Qualcomm(R) Hexagon(TM) NPU (OK)

## Controlled probes

| Backend | Loaded | Valid output | TTFT / p50 | Total / p95 | Throughput | Memory | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| Native ARM64 llama.cpp CPU | 1 | 1 | 0.43391980000888 | 1.883261599999969 | None | 10640814080 | Usable |
| x64 llama.cpp Vulkan | 1 | 0 | 21.986074400003417 | 30.376419100008206 | 15.26 | 10312699904 | Reject / investigate |
| ORT GenAI CPU | 1 | 0 | 7.48000165913254e-05 | 762.7831524000212 | 0.3080823157414999 | 3801780224 | Reject / investigate |
| ORT GenAI DirectML | 1 | 0 | 0.00012079998850822449 | 53.358051599992905 | 4.404208792362112 | 6916960256 | Reject / investigate |
| ONNX DirectML microbenchmark | 1 | 0 | 0.3420000139158219 | 0.6708999862894416 | None | None | Reject / investigate |
| ONNX CPU microbenchmark | 1 | 1 | 0.056899996707215905 | 0.06730001769028604 | None | None | Provider verified |
| ONNX QNN HTP microbenchmark | 1 | 1 | 0.06479999865405262 | 0.11679998715408146 | None | None | Provider verified |

## Measured acceleration verdicts

- QNN executed the compatible QDQ graph without CPU nodes and produced valid output, but achieved only 0.88x CPU p50 performance (below 1.0x means slower).
- DirectML generated 14.30x more tokens/s than its matching x64 CPU control, but the token stream was corrupted (`<unused...>` repetition), so the apparent speedup is rejected.
- No tested GPU or NPU path both accelerated its matching control and produced valid output; therefore no accelerated generation configuration is approved.

## Compatibility findings

- ONNX Runtime GenAI officially lists Windows ARM64, DirectML, and QNN support; backend usability still depends on a matching graph and provider package.
- The official `onnxruntime/Gemma-3-ONNX` DirectML export is the controlled Gemma 3 4B GPU candidate.
- QNN requires a QNN-compatible QDQ or precompiled context graph. A detected NPU or successfully loaded provider library alone is not an acceleration result.
- DirectML is in sustained engineering; Windows ML is Microsoft's recommended long-term Windows deployment path.

## Recommendation

Use native ARM64 llama.cpp CPU as the reliable fallback. Use an accelerated backend only when its row above has both valid output and measured improvement over its matching CPU control. Never use the x64 Vulkan result because it generated invalid repeated text.

## Official references

- https://github.com/microsoft/onnxruntime-genai
- https://huggingface.co/onnxruntime/Gemma-3-ONNX
- https://github.com/onnxruntime/onnxruntime-qnn
- https://github.com/microsoft/DirectML
