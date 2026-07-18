# OpenAI generation comparison v1

This experiment keeps the frozen local winner's benchmark, prompt P1,
768-token online output limit, gold context, and retrieved top-5 page-order compact
context unchanged. It replaces only the answer generator with the OpenAI
Responses API provider configured in
`config/openai_generation_experiments_v1.json`.

The implementation was adapted from the earlier
`X:\teachingAssistant\apps\api\app\services\llm.py`: it retains a provider
boundary, local-secret credentials, optional base URL, and the Responses
API. Batch evaluation is intentionally non-streaming so a response can be
cached and evaluated once. Unlike the interactive service, the experiment
adds strict structured output, usage metadata, deterministic request hashes,
no automatic retries, and an exact paid-call gate.

## Zero-call preflight

Install the optional SDK when you are ready to execute; it is not needed for
preflight or unit tests:

```powershell
python -m pip install -e ".[online-generation]"
python scripts/run_openai_generation_experiment.py --split smoke
```

The safe default makes no API calls. It writes `preflight.json`, including the
16 planned smoke requests, cache hits, estimated prompt tokens, and an
upper-bound cost based on the dated pricing snapshot. Review this file before
enabling paid execution.

## Paid execution (only after reviewing the preflight)

Populate the root `.env` file, which is explicitly ignored by Git:

```text
OPENAI_API_KEY=your-key-here
```

The process environment still takes precedence when present. Never put the key
in a tracked config, `.env.example`, command argument, or report. Then run:

```powershell
python scripts/run_openai_generation_experiment.py `
  --split smoke `
  --execute-paid `
  --approved-new-calls 16
```

The approval count must exactly match the uncached count. Completed responses
are cached by a hash of model, prompt, settings, and JSON schema. SDK retries
are disabled and the runner has no retry loop. If execution stops, rerun the
zero-call preflight first; its new-call count will exclude completed cache
entries.

Outputs after execution are placed under `runs/<run_id>/`:

- `results.jsonl`: answers, evidence, citations, usage, latency, and automatic evaluation;
- `run_manifest.json`: provider/model settings, hashes, counts, and metrics by context mode;
- `cache/*.json`: one successful provider response per unique request hash.

Build the automatic comparison and four-answer blinded review packet after a
run completes:

```powershell
python scripts/build_openai_generation_comparison.py `
  --online-results reports/openai_generation_experiments/runs/<run_id>/results.jsonl
python scripts/build_review_packet_view.py `
  --input reports/openai_generation_experiments/comparisons/latest/blinded_human_review_packet.jsonl `
  --output reports/openai_generation_experiments/comparisons/latest/blinded_human_review_packet.html
```

Each reviewed question then contains local-gold, local-retrieved, GPT-4o-gold,
and GPT-4o-retrieved answers under per-question shuffled labels. Keep
`blinded_answer_key.json` closed until review is complete.

For direct model-gap analysis with no hidden identities, render the labeled
packet instead:

```powershell
python scripts/build_review_packet_view.py `
  --input reports/openai_generation_experiments/comparisons/full_40_labeled/labeled_comparison_packet.jsonl `
  --output reports/openai_generation_experiments/comparisons/full_40_labeled/local_vs_gpt4o_labeled_comparison.html `
  --revealed
```

This view starts with provider labels, evidence modes, and automatic screens
visible. The four fixed labels are Local Qwen — Gold evidence, GPT-4o API —
Gold evidence, Local Qwen — Retrieved evidence, and GPT-4o API — Retrieved
evidence.

## Artifact layout

- `cache/`: successful API responses keyed by complete request hash, retained
  so a resumed run never repeats a paid request;
- `runs/`: immutable raw results and manifests for each executed run;
- `comparisons/smoke_initial_384/`: first eight-question, 384-token snapshot;
- `comparisons/smoke_complete_768/`: completed eight-question snapshot after
  selective 768-token retries;
- `comparisons/full_40_labeled/`: final 40-question labeled comparison;
- `comparisons/latest/`: default destination for future ad-hoc rebuilds.

The comparison directories are derived, reproducible views. The run results
and cache provide the source-level traceability for rebuilding them without
additional provider calls.

### Output-limit retry used by the smoke experiment

For the initial 384-token run, retry only its three truncated question IDs in
both modes at the new 768-token default (six new requests):

```powershell
python scripts/run_openai_generation_experiment.py `
  --split smoke `
  --question-id GEN-BIO-012 `
  --question-id GEN-PSC-002 `
  --question-id GEN-PSC-015
```

Review the resulting six-call preflight before adding `--execute-paid` and
`--approved-new-calls 6`. Supply the base results followed by the retry results
to the comparison command; later files override only matching question/mode
rows, preserving the ten successful original answers.

GPT-4o is retained because it was the explicitly requested comparison target.
The model is configurable and the resolved model returned by the API is
recorded per response. OpenAI's current model catalog should be checked again
before spending because model availability and pricing can change.
