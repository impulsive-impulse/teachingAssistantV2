# Configuration map

## Frozen decisions

- `retrieval_baseline_v1.yaml`: immutable Retrieval Baseline v1 (`1.0.0`).
- `generation_baseline_v1.json`: immutable Generation Baseline v1 (`1.0.0`),
  including the online default and offline fallback profiles.

Any behavior change to a frozen file requires a new semantic version and a new
matching report directory. Do not silently edit v1.

## Historical experiment configurations

- `generation_phase_a_v1.json`: first local generation checkpoint.
- `generation_experiments_v1.json`: bounded local Qwen model/prompt/context matrix.
- `openai_generation_experiments_v1.json`: paid GPT-4o comparison harness.

Experiment configs remain available for reproduction. They are evidence for a
baseline decision, not the current production source of truth.
