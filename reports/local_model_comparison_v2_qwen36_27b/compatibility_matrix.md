# Compatibility matrix

| Model | Artifact and licence | Native ARM64 CPU | Adreno OpenCL | Experiment outcome |
|---|---|---|---|---|
| Qwen3-8B Q4_K_M frozen control | Official 4.682 GiB GGUF; Apache-2.0; checksum-pinned v1 baseline | Previously validated; production control was not rerun | Previously validated on X1-85 with 37/37 layers offloaded | Retained control; production files untouched |
| Qwen3.6-27B Q4_K_M | Official ggml-org 17.784 GiB GGUF; Apache-2.0; SHA-256 verified | Compatible; valid output; 396.70 s TTFT and 578.22 s latency | Compatible; X1-85 selected, Adreno kernels used, 65/65 layers offloaded; no CPU fallback | Rejected after validity for unacceptable latency and memory |

Runtime compatibility is distinct from suitability. Qwen3.6-27B executed
correctly on both required backends, but its performance on this machine did
not justify advancing to smoke.
