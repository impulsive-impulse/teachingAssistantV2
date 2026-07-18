# Generation Phase A v1

This directory is the complete checkpoint for the eight-question Qwen3-8B
gold-context smoke gate. It is derived from, and does not modify,
`data/benchmarks/generation_benchmark_v1.jsonl`.

## Artifact map

- `benchmark_split.json`: fixed 8-row development/smoke and 32-row held-out split.
- `smoke_subset.jsonl`: unchanged copies of the eight selected benchmark rows.
- `gold_contexts.jsonl`: accepted PDF pages with stable evidence IDs and hashes.
- `runs/*.json`: atomic raw response, claim citations, validation, rubric, and latency.
- `smoke_results.jsonl`: deterministic ordered view rebuilt from the run files.
- `manual_review.jsonl`: point-level completeness and grounding review.
- `smoke_metrics.json`: automatic and reviewed aggregate metrics.
- `experiment_state.json`: immutable input hashes, completed IDs, and resume gates.
- `runtime_logs/`: local llama.cpp initialization logs; per-question timings are in `runs/`.
- `phase_a_smoke_report.md`: concise results and gate decision.

## Result and gate

All eight generations completed and returned valid claim-level JSON with known
evidence IDs. Strict manual review found two complete and fully grounded answers,
mean required-point coverage of 0.6937, five fully supported citation sets, and
three partially supported sets. No unsupported claim was found.

The infrastructure gate passed, but answer completeness plus grounding did not.
Prompt comparisons and other model downloads therefore remain disabled pending
review of `phase_a_smoke_report.md`.

## Reproduce or resume

```powershell
$env:PYTHONPATH = "src"
temp\python-x64\python.exe scripts\run_generation_phase_a.py --prepare-only
temp\python-x64\python.exe scripts\run_generation_phase_a.py `
  --llama-server <path-to-native-arm64-llama-server.exe> `
  --model <path-to-Qwen3-8B-Q4_K_M.gguf>
temp\python-x64\python.exe scripts\run_generation_phase_a.py --reevaluate-only
```

A completed resume verifies immutable hashes and returns without starting the
server. An interrupted run skips atomic per-question files already completed.
