# Compatibility Matrix

| Candidate | Artifact | License | llama.cpp architecture | Adreno selected | Optimized kernels | Layer offload | Inference ready | Decision |
|---|---|---|---|---:|---:|---:|---:|---|
| Sarvam-30B Q4_K_M | Six-shard GGUF, 18.227 GiB | Apache-2.0 compatible | `bailingmoe2` loaded | Yes, X1-85 | Yes | 20/20 | No | Reject: startup memory/latency |
| Qwen3-8B Q4_K_M control | Frozen v1 artifact | Apache-2.0 | Existing validated control | Yes | Yes | 37/37 | Yes | Production control unchanged |

Sarvam's runtime compatibility is partial: model parsing, OpenCL selection, and
offload succeed, but the server cannot reach request readiness within safe host
memory on this machine.
