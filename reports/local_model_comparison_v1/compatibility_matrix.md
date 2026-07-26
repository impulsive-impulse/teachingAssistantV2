# Compatibility matrix — in progress

| Model | Exact artifact | License | ARM64 CPU | Adreno OpenCL | State |
|---|---|---|---|---|---|
| Qwen3-8B Q4_K_M control | Frozen official 4.682 GiB GGUF, SHA-256 verified | Apache-2.0; frozen production control | Valid output; validity TTFT 189.40 s | X1-85 and 37/37 offload confirmed; 16-question development complete | Control only; production baseline untouched |
| Gemma 3 12B IT QAT Q4_0 | Official 7.519 GiB GGUF, SHA-256 verified | Gemma terms; compatible with conditions | Valid output; very slow | X1-85 and 49/49 offload confirmed | Rejected at smoke citation gate |
| gpt-oss-20b native MXFP4 | llama.cpp conversion, 11.278 GiB, SHA-256 verified | Apache-2.0; compatible | Valid output; unacceptable latency | X1-85 and 25/25 offload confirmed; invalid JSON | Rejected at validity |
| Phi-4 14B Q4_K_S | Official Microsoft 7.861 GiB GGUF, SHA-256 verified | MIT; compatible | Valid output; TTFT 197.48 s, latency 258.08 s | X1-85 and 41/41 offload confirmed; slower than CPU | Rejected at validity for latency and quality |
| Granite 3.3 8B Instruct Q4_K_M | Official IBM 4.603 GiB GGUF, SHA-256 verified | Apache-2.0; compatible | Parseable JSON but invalid citation metadata; TTFT 210.67 s | X1-85 and 41/41 offload confirmed; identical citation failure | Rejected at validity |

“Expected” is not a benchmark result. A backend becomes compatible only after
valid output plus log-confirmed device selection and layer offload. Runtime
compatibility alone did not overcome the quality or latency failures of the
all four rejected candidates.
