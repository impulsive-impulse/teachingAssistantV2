# GPU Validity and Benchmark Status

| Model | Backend | Ready | TTFT | Total latency | Peak observed RSS | Declared OpenCL model buffer | Output/schema | Quality |
|---|---|---:|---:|---:|---:|---:|---|---|
| Sarvam-30B Q4_K_M | Adreno OpenCL | No | N/A | N/A | 30.08 GiB | 18,081.84 MiB | Not attempted | Not measured |
| Qwen3-8B Q4_K_M control | Adreno OpenCL | Yes | 73.29 s | 100.70 s | 10.85 GiB | N/A | Valid | Frozen control reference |

Sarvam has no CPU/GPU generation-speed comparison or quality score because it
failed before the first request. Recording zeros would be misleading; all
generation metrics are explicitly N/A. The candidate cannot enter a quality
leaderboard, and Qwen3-8B remains the best quality, speed, and balanced eligible
model for this isolated comparison.
