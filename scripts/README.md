# Script entry points

Scripts are intentionally thin wrappers around `src/textbook_audit/`. Prefer
these canonical commands over importing experiment internals directly.

## Frozen baselines

- `manage_retrieval_baseline_v1.py`: build, evaluate, validate, or checksum the
  frozen retrieval baseline.
- `manage_generation_baseline_v1.py`: validate or checksum the frozen generation
  decision without running a model or making an API call.
- `query_final_pipeline.py`: retrieve the approved evidence for one question and book.

## Corpus and benchmarks

- `audit_textbooks.py`: extract and audit page-level textbook data.
- `generate_retrieval_benchmark.py`: generate/validate retrieval benchmark candidates.
- `build_generation_benchmark_v1.py`: deterministically rebuild Generation Benchmark v1.

## Historical experiments

Files beginning with `run_` execute individual research phases. They remain for
reproduction and should write beneath their existing report directories. The
OpenAI runner is zero-call by default and requires an exact uncached-call
approval before paid execution.

Report builders (`build_*`) transform existing artifacts and do not perform
model inference unless their documentation explicitly says otherwise.
