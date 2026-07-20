# Generation Baseline v1

Generation Baseline v1 (`1.0.0`) is frozen following the project owner's
high-level review of all 40 questions in the explicitly labeled local-Qwen
versus GPT-4o comparison. The machine-readable source of truth is
`config/generation_baseline_v1.json`, whose frozen SHA-256 is
`758c0a857b427ab73c790b6031a14762c6653f8714f0fef29830373439ab78ba`.

## Decision

| Profile | Role | Frozen generator | Output ceiling |
|---|---|---|---:|
| `online_quality` | Default quality profile | `gpt-4o-2024-08-06` via OpenAI Responses API | 768 |
| `local_offline` | Offline cost/privacy fallback | Qwen3-8B Q4_K_M via llama.cpp | 384 |

Both profiles use Retrieval Baseline v1, prompt P1, deterministic temperature
0, and the same retrieved top-five page-order compact context. Profile choice
happens before generation; v1 does not automatically resend a request to a
second provider.

The online experiment requested the `gpt-4o` alias, and all 80 retained
completed responses resolved to `gpt-4o-2024-08-06`. The baseline pins that
resolved snapshot so future alias movement cannot silently change v1.

## Evidence

| Source | Completed | Required-point coverage | Citation validity | Unsupported screen | Structured | p95 latency |
|---|---:|---:|---:|---:|---:|---:|
| Local Qwen — Gold | 40/40 | 0.4654 | 0.9750 | 0.0250 | 0.9750 | 85.7361 s |
| Local Qwen — Retrieved | 40/40 | 0.4704 | 0.9500 | 0.0250 | 0.9750 | 229.4036 s |
| GPT-4o — Gold | 40/40 | 0.5779 | 1.0000 | 0.1000 | 1.0000 | 6.2071 s |
| GPT-4o — Retrieved | 40/40 | 0.5450 | 0.9500 | 0.0750 | 1.0000 | 8.7332 s |

The automatic metrics are lexical diagnostics. They helped navigate the review
but are not treated as scientific adjudication. The final approval is captured
in `human_review_signoff.json` and deliberately states that no per-question
human rubric scores were recorded.

## Human-review interpretation

The review established that the answer set looked acceptable overall for the
project's v1 decision. It did not establish inter-rater reliability, blinded
preference rates, per-question pass rates, or statistical superiority. Claims
about the baseline must preserve that qualification.

The review source is:

`reports/openai_generation_experiments/comparisons/full_40_labeled/local_vs_gpt4o_labeled_comparison.html`

## Validate the lock

Run from the repository root:

```powershell
$env:PYTHONPATH = "src"

# Verify config semantics, upstream hashes, 40x4 comparison completeness,
# source result sets, resolved model, labels, sign-off, and every manifest hash.
temp\python-x64\python.exe scripts\manage_generation_baseline_v1.py validate

# Recompute only the recorded file checksums.
temp\python-x64\python.exe scripts\manage_generation_baseline_v1.py checksums
```

These commands are read-only and make no retrieval, local-model, or paid API
call. `manifest.json` is the portable artifact inventory.

## Limitations

- The human review was high-level rather than per-question scored.
- Local and online outputs used different token ceilings, 384 and 768.
- Formula and unsupported-claim automatic screens remain weak lexical proxies.
- The 40-question benchmark covers only the two reviewed Class 10 textbooks.
- Provider availability, latency, and price can change even though the model
  snapshot and experiment observations are frozen.

## Immutability policy

Any change to the benchmark, retrieval baseline, prompt, evidence assembly,
model snapshot, quantization, output ceiling, decoding, structured response
schema, or default/fallback roles requires Generation Baseline v2 (or another
new semantic version). V1 config, sign-off, manifests, source results, and
review artifacts remain unchanged and available for comparison.
