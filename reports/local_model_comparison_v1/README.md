# Local Model Comparison v1

This directory contains the controlled experiment for finding a stronger local
answering model than the frozen Qwen3-8B Generation Baseline v1 fallback.

Production v1 files are controls, not experiment outputs. In particular, this
experiment must not modify:

- `config/retrieval_baseline_v1.yaml`
- `config/generation_baseline_v1.json`
- `config/generation_experiments_v1.json`
- `data/benchmarks/generation_benchmark_v1.jsonl`
- any historical run below `reports/generation_experiments/`

## Fixed comparison contract

- Retrieval Baseline v1 remains frozen.
- Every candidate receives the same saved top-five development evidence.
- Prompt strategy is P1 and context strategy is
  `retrieved_top5_page_order_compact`.
- The five-key JSON answer schema and existing citation validator remain fixed.
- Each model uses its official embedded GGUF chat template and its documented
  decoding defaults. Model-specific template handling is recorded, not hidden.
- The 24-question holdout is not generated against until a model passes the
  development and human-review gates.

## Successive-narrowing stages

1. Artifact, license, memory, and runtime compatibility review.
2. One-answer output-validity probe.
3. Native ARM64 CPU runtime probe.
4. Adreno OpenCL probe where the quantization is supported.
5. Eight-question smoke subset.
6. Sixteen-question development set.
7. Blinded human review for finalists.
8. Untouched 24-question holdout for finalists only.

Any invalid/corrupted output, silent CPU fallback, incompatible runtime,
unacceptable latency, or clearly inferior quality is an early-stop condition.

Model weights and llama.cpp binaries belong only under the Git-ignored
`app_data/models/` tree. Per-run logs and compact results belong below this
directory.

## Runner

The isolated runner is `scripts/run_local_model_comparison.py`. It:

- verifies every frozen input hash and the model SHA-256 before load;
- reads only `inputs/development_retrieved_top5.jsonl`;
- uses the model's embedded GGUF chat template;
- applies the candidate-specific recorded decoding settings;
- checkpoints every answer below `runs/`;
- records llama.cpp prompt/generation timings, TTFT, latency, RSS, and sampled
  Windows GPU process memory;
- rejects missing Adreno device/kernel/offload log evidence; and
- rejects empty, repeated-token, `<unused…>`, or replacement-character output.

The `validity`, `smoke`, and `development` stages map to one, eight, and sixteen
questions. The runner intentionally refuses `holdout` until a finalist decision
creates a separately pinned holdout evidence snapshot.

## Directory layout

- `artifact_registry.json`: pinned repositories, revisions, files, licences,
  memory expectations, templates, decoding, checksums, and decisions.
- `experiment_config.json`: frozen comparison contract, hardware, runtimes,
  stage gates, and source hashes.
- `inputs/`: immutable saved development evidence; no holdout snapshot exists.
- `runs/`: authoritative per-run manifests, question results, and llama.cpp
  runtime logs.
- `logs/downloads/`: retained non-empty artifact-transfer logs.
- `logs/runner_summaries/`: retained non-empty wrapper summaries; detailed
  runtime evidence remains in each run.
- `human_review/finalists/`: finalist gate status and packet manifest.
- `benchmark_tables.md`, `compatibility_matrix.md`, `decisions.md`, and
  `completion_audit.md`: final review surface.

## Final outcome

The ordered core comparison is complete. All four alternatives were rejected
by successive-narrowing gates:

- Gemma failed the smoke citation/reliability gate.
- gpt-oss failed OpenCL structured output and latency gates.
- Phi-4 failed latency and comparative-quality gates.
- Granite failed citation validity and comparative latency/quality gates.

Qwen3-8B remains the only model to pass smoke and complete the frozen
16-question development benchmark. No alternative reached finalist status, so
the blinded two-model packet and holdout were not opened. Production v1 remains
unchanged.

Final evidence:

- `compatibility_matrix.md`
- `benchmark_tables.md`
- `decisions.md`
- `completion_audit.md`
- `human_review/finalists/packet_manifest.json`
