# Completion audit

## Frozen controls

All configured hashes were recomputed after the experiment and matched:

- Retrieval Baseline v1:
  `736fb9325794caead4439316b6ca546bd782cd7029b4f9f7788f545c5b43baa6`
- Generation Baseline v1:
  `758c0a857b427ab73c790b6031a14762c6653f8714f0fef29830373439ab78ba`
- Historical generation experiment:
  `a80a31f19c4b606533c319dc1876686ba2cf08e54c1dcef17d745e9c28273f70`
- Generation benchmark:
  `f756e6333909c72f0e0be82b7bc16c9756f158fb39e16d463442e2bed5266680`
- Frozen development top-five evidence:
  `acd83d2a8daa2749972a54ed4ec3e05e5b34feb3896af681b1385c4b2fa6b266`

## Ordered candidates

Every required artifact is checksum-verified under Git-ignored `app_data`.
Gemma was rejected at smoke; gpt-oss, Phi-4, and Granite were rejected at
validity. Exact artifact, licence, memory expectation, chat template, decoding,
runtime evidence, metrics, and decisions are recorded in
`artifact_registry.json` and `decisions.md`.

Every completed run has both `run_manifest.json` and `results.jsonl`. OpenCL
runs contain explicit X1-85 selection, optimized-kernel, and nonzero/full-layer
offload evidence.

## Development, review, and holdout gates

Qwen completed the frozen 16-question development control. No alternative
reached development/finalist status. The human-review manifest therefore
records that no valid two-model blinded packet could be generated. There are
zero holdout run directories and zero holdout evidence snapshots.

## Requested deliverables

- Compatibility matrix: `compatibility_matrix.md`
- CPU/GPU benchmark table: `benchmark_tables.md`
- Gate-aware quality leaderboard: `benchmark_tables.md`
- Best quality, speed, and balanced declarations: `benchmark_tables.md`
- Comparison against Qwen: `benchmark_tables.md`
- Answering Baseline v2 recommendation: `benchmark_tables.md`
- Full decision trail: `decisions.md`

## Verification

- Bundled project runtime full suite: 223 passed, with one pre-existing
  Starlette deprecation warning.
- ARM64 task-specific suite: 13 passed.
- `git diff --check`: passed.
- Model weights and runtime binaries are confirmed Git-ignored.
- Production v1 baselines remain unchanged.
