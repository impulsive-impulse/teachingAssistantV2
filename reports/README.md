# Report map

## Frozen decisions — start here

- `retrieval_baseline_v1/`: retrieval architecture, benchmark metrics, manifest.
- `generation_baseline_v1/`: approved online/local profiles, human sign-off,
  limitations, and checksum manifest.

## Benchmarks and source review

- `generation_benchmark_v1/`: generation benchmark build and validation.
- `generation_benchmark_v1_review/`: detailed textbook/source verification.
- `retrieval_baseline_v1/`: reviewed retrieval benchmark results and failures.

## Historical experiments

- `experiments/`: retrieval experiment phases and selection history.
- `generation_phase_a_v1/`: initial local generation checkpoint.
- `generation_experiments/`: local model/prompt/context experiment matrix.
- `openai_generation_experiments/`: GPT-4o runs, cache, and local-vs-online comparisons.
- `hardware_backend_v1/`: machine/backend compatibility probes.

`test_runs.md` is the concise chronological validation log. Historical reports
are preserved even when their original “provisional” or “gated” status has been
superseded by a frozen baseline.
