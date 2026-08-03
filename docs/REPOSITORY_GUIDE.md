# Repository guide

This is the shortest path through the repository. Stable experiment paths are
intentionally not moved: frozen configs, manifests, reports, and reproduction
commands refer to them by name.

## Current source of truth

| Question | Open this file |
|---|---|
| What retrieval pipeline is approved? | `config/retrieval_baseline_v1.yaml` |
| What generation profiles are approved? | `config/generation_baseline_v1.json` |
| Why were those generation profiles selected? | `reports/generation_baseline_v1/README.md` |
| Did a newer local model beat Qwen3-8B? | `reports/local_model_comparison_v1/benchmark_tables.md` and `reports/local_model_comparison_v2_qwen36_27b/benchmark_tables.md` |
| What exactly did the human review approve? | `reports/generation_baseline_v1/human_review_signoff.json` |
| How do I inspect local vs online answers? | `reports/openai_generation_experiments/comparisons/full_40_labeled/local_vs_gpt4o_labeled_comparison.html` |
| How do I query retrieval interactively? | `scripts/query_final_pipeline.py` |
| What is the plan for the local textbook-chat application? | `docs/UX_PLAN.md` |
| How is the local application structured and run during development? | `docs/APP_DEVELOPMENT.md` |
| How do I verify frozen files? | `scripts/manage_retrieval_baseline_v1.py` and `scripts/manage_generation_baseline_v1.py` |

## End-to-end architecture

```text
student question + explicit book_id
  -> Retrieval Baseline v1
       fixed 600/100 chunks
       BGE-small + BM25 + activated formula/table/visual priors
       reciprocal-rank fusion -> top 5 -> overlap-aware context assembly
  -> Generation Baseline v1 profile selected before inference
       online_quality: GPT-4o snapshot, 768-token ceiling
       local_offline: Qwen3-8B Q4_K_M, 384-token ceiling
  -> structured grounded answer with evidence IDs and page citations
```

There is no automatic cross-provider retry in v1. The caller selects the local
profile before generation when offline operation, privacy, cost, or provider
availability requires it.

## Directory map

- `books/`: original PDFs. They are inputs and must not be edited.
- `data/processed/`: deterministic page extraction and chapter maps.
- `data/benchmarks/`: reviewed retrieval and generation benchmarks plus schemas.
- `data/retrieval/`: query-level retrieval results and Git-ignored model/index caches.
- `config/`: immutable baseline configs and experiment configs; see its README.
- `src/textbook_audit/`: reusable implementation. Scripts should remain thin wrappers.
- `scripts/`: canonical source-checkout entry points; see its README.
- `reports/retrieval_baseline_v1/`: frozen retrieval decision and checksums.
- `reports/generation_baseline_v1/`: frozen generation decision and checksums.
- `reports/local_model_comparison_v1/`: controlled 2026 local-model comparison,
  raw run evidence, compatibility matrix, leaderboard, and no-v2 recommendation.
- `reports/local_model_comparison_v2_qwen36_27b/`: isolated Qwen3.6-27B CPU and
  Adreno validity investigation, early-stop evidence, and retained-control
  recommendation.
- `reports/experiments/`: historical retrieval experiment ledger and artifacts.
- `reports/generation_experiments/`: historical local generation matrix.
- `reports/openai_generation_experiments/`: historical online comparison and paid-call cache.
- `tests/`: behavioral, deterministic, golden, and freeze-integrity regressions.

## Baseline versus experiment

A file under `config/*_baseline_v1.*` and its matching `reports/*_baseline_v1/`
directory is an immutable decision. Behavior changes require a new semantic
baseline version. Experiment directories are evidence explaining how the
decision was reached; labels such as “provisional” inside historical generated
artifacts describe their status at creation time and are superseded by the
current baseline decision.

## Canonical validation

```powershell
$env:PYTHONPATH = "src"

# Retrieval: config, indexes, benchmark, golden rankings, and manifest.
temp\python-x64\python.exe scripts\manage_retrieval_baseline_v1.py validate

# Generation: configs, source results, metrics, labels, sign-off, and manifest.
temp\python-x64\python.exe scripts\manage_generation_baseline_v1.py validate

# Repository regressions.
temp\python-x64\python.exe -m pytest -q
```

Neither baseline validation command calls an answer-generation model. The
generation validator also makes no paid provider request.
