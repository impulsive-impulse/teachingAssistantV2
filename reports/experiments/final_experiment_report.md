# Final local RAG experiment report

The approved retrieval loop is complete through stable context assembly. Answer generation was finalized separately under Generation Baseline v1.

## Completion audit

| Phase | Completed runs | Disposition |
|---|---:|---|
| A — candidate preservation | 20 | Full deduplicated union retained 61/61; every capped pool lost evidence. |
| B — text representation | 28 | Query-dense member + two page windows + neighbours retained for controlled reranker tests. |
| C — fusion/reranking logic | 13 | Soft fusion retained for speed; capped preselectors rejected on recall. |
| D — reranker bake-off | 3 | MiniLM retained only as diagnostic; larger models stopped by successive runtime gates. |
| E — embedding bake-off | 6 | BGE-small retained for local balance; E5 retained as quality reference. |
| F — chunking | 15 | Fixed 600/100 selected; BGE-small hybrid confirmed. |
| G — query processing | 8 | Deterministic textbook synonyms retained; Gemma remained separately gated. |
| H — specialists | 16 | Combined equation/table/caption priors retained; base top-five preserved. |
| I — context assembly | 12 | Overlap merge retained. |
| J — answer generation | 0 | Separate reviewed program; see Generation Baseline v1. |

All 121 immutable run records have unique IDs, complete required fields, reproduction commands, and locally existing declared outputs; pending run count is zero. The artifact manifest hashes all 362 declared files. 120 bulky per-query detail files are reproducible and intentionally excluded from Git; compact configurations, metrics, ledgers, and reports are tracked.

## Selected pipelines

| Role | Run | Overall H@1/3/5 | MRR | Natural H@5 / MRR | Canonical H@5 | p95 | Peak RSS |
|---|---|---:|---:|---:|---:|---:|---:|
| best_quality | `phase_h_h3_combined_specialist_priors` | 26/61 (42.6%) / 44/61 (72.1%) / 50/61 (82.0%) | 0.601 | 16/20 (80.0%) / 0.599 | 34/41 (82.9%) | 71.2 ms | 688 MB |
| best_lightweight_cpu | `phase_f_f0_bm25_fixed_600_100` | 20/61 (32.8%) / 38/61 (62.3%) / 45/61 (73.8%) | 0.509 | 12/20 (60.0%) / 0.421 | 33/41 (80.5%) | 1.8 ms | 132 MB |
| preferred_balanced | `phase_h_h3_combined_specialist_priors` | 26/61 (42.6%) / 44/61 (72.1%) / 50/61 (82.0%) | 0.601 | 16/20 (80.0%) / 0.599 | 34/41 (82.9%) | 71.2 ms | 688 MB |

Best quality and balanced are the same combined-specialist pipeline. The lightweight profile is fixed-600/100 BM25 with no neural model; it trades four natural and five overall Hit@5 successes for a roughly 40x lower p95 and much smaller memory footprint. Differences of one question should be treated cautiously.

## Balanced pipeline slices

| Slice | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---:|---:|---:|---:|---:|
| book:biology | 30 | 16/30 (53.3%) | 24/30 (80.0%) | 28/30 (93.3%) | 0.702 |
| book:physical_sciences | 31 | 10/31 (32.3%) | 20/31 (64.5%) | 22/31 (71.0%) | 0.504 |
| formula_dependent | 16 | 5/16 (31.2%) | 9/16 (56.2%) | 10/16 (62.5%) | 0.478 |
| visual_dependent | 6 | 3/6 (50.0%) | 6/6 (100.0%) | 6/6 (100.0%) | 0.667 |
| table_dependent | 3 | 3/3 (100.0%) | 3/3 (100.0%) | 3/3 (100.0%) | 1.000 |
| multi_page | 21 | 8/21 (38.1%) | 15/21 (71.4%) | 17/21 (81.0%) | 0.567 |
| multi_chunk | 27 | 10/27 (37.0%) | 19/27 (70.4%) | 23/27 (85.2%) | 0.565 |
| difficulty:easy | 9 | 6/9 (66.7%) | 9/9 (100.0%) | 9/9 (100.0%) | 0.833 |
| difficulty:medium | 33 | 15/33 (45.5%) | 22/33 (66.7%) | 24/33 (72.7%) | 0.590 |
| difficulty:hard | 19 | 5/19 (26.3%) | 13/19 (68.4%) | 17/19 (89.5%) | 0.511 |
| query_style:colloquial | 4 | 2/4 (50.0%) | 3/4 (75.0%) | 3/4 (75.0%) | 0.642 |
| query_style:short_underspecified | 3 | 0/3 (0.0%) | 1/3 (33.3%) | 3/3 (100.0%) | 0.278 |
| query_style:different_vocabulary | 3 | 3/3 (100.0%) | 3/3 (100.0%) | 3/3 (100.0%) | 1.000 |
| query_style:cause_effect | 3 | 1/3 (33.3%) | 1/3 (33.3%) | 2/3 (66.7%) | 0.440 |
| query_style:misconception | 4 | 1/4 (25.0%) | 3/4 (75.0%) | 3/4 (75.0%) | 0.536 |
| query_style:imperfect_grammar | 3 | 2/3 (66.7%) | 2/3 (66.7%) | 2/3 (66.7%) | 0.708 |

The five negative/weak-evidence rows are excluded from Hit@K and MRR; no generation or abstention score is claimed for them.

## Quality–latency–memory Pareto frontier

Dominance maximizes natural Hit@5/MRR and overall Hit@1/MRR while minimizing warm p95 latency and peak RSS.

| Run | Natural H@5 | Natural MRR | Overall H@1 | Overall MRR | p95 | Peak RSS |
|---|---:|---:|---:|---:|---:|---:|
| `phase_h_h3_combined_specialist_priors` | 16/20 | 0.599 | 26/61 | 0.601 | 71.2 ms | 688 MB |
| `phase_h_h0_visual_caption_context` | 16/20 | 0.587 | 23/61 | 0.572 | 33.7 ms | 963 MB |
| `phase_h_h1_formula_context_activation_v2` | 16/20 | 0.574 | 23/61 | 0.572 | 84.2 ms | 679 MB |
| `phase_h_h2_formula_context_activation_v3` | 16/20 | 0.574 | 22/61 | 0.563 | 83.7 ms | 684 MB |
| `phase_f_f4_bge_small_page_prior_rrf` | 16/20 | 0.511 | 24/61 | 0.558 | 30.8 ms | 756 MB |
| `phase_g_g0_textbook_synonym_expansion` | 16/20 | 0.562 | 21/61 | 0.551 | 46.7 ms | 694 MB |
| `phase_g_g1_original_plus_textbook_synonym_expansion` | 16/20 | 0.543 | 20/61 | 0.528 | 146.5 ms | 673 MB |
| `phase_g_g0_formula_symbol_normalization` | 15/20 | 0.547 | 22/61 | 0.530 | 42.1 ms | 701 MB |
| `phase_g_g0_acronym_expansion` | 14/20 | 0.525 | 21/61 | 0.522 | 41.7 ms | 697 MB |
| `phase_g_g0_grammar_cleanup` | 14/20 | 0.526 | 20/61 | 0.514 | 48.4 ms | 692 MB |
| `phase_f_f3_bge_small_fixed_600_100` | 14/20 | 0.525 | 20/61 | 0.514 | 29.0 ms | 755 MB |
| `phase_g_g0_raw` | 14/20 | 0.525 | 20/61 | 0.514 | 44.0 ms | 678 MB |
| `phase_f_f0_bm25_fixed_600_100` | 12/20 | 0.421 | 20/61 | 0.509 | 1.8 ms | 132 MB |
| `phase_f_f0_bm25_fixed_400_80` | 11/20 | 0.335 | 17/61 | 0.450 | 2.5 ms | 131 MB |
| `phase_f_f0_bm25_fixed_300_50` | 9/20 | 0.265 | 14/61 | 0.382 | 3.8 ms | 108 MB |

## Exact balanced architecture

```text
student question + explicit book_id
  -> deterministic textbook-synonym expansion
  -> [fixed 600/100 BM25] + [normalized BGE-small cosine]
  -> static specialist activator
       formula -> equation + surrounding-text page prior
       table   -> row-with-repeated-header page prior
       visual  -> caption + nearby-text page prior
  -> lift active page priors to child chunks
  -> reciprocal-rank fusion (k=60)
  -> top five fixed chunks
  -> exact-overlap merging with PDF/textbook/chapter/section metadata
  -> grounded evidence context (generation intentionally absent)
```

## Reproduce

```powershell
# Rebuild/reuse the selected indexes and benchmark runs
temp\python-x64\python.exe scripts\run_chunking_bakeoff.py --stage bge_confirmation --device cpu --batch-size 16
temp\python-x64\python.exe scripts\run_query_processing.py --stage screen --device cpu --batch-size 16
temp\python-x64\python.exe scripts\run_specialist_retrieval.py --stage combined --device cpu --batch-size 16
temp\python-x64\python.exe scripts\run_evidence_sets.py
temp\python-x64\python.exe scripts\run_context_assembly.py
python scripts\finalize_experiments.py

# Query the retained balanced pipeline with full evidence text
temp\python-x64\python.exe scripts\query_final_pipeline.py "How do plants eat?" --book-id biology --profile balanced --include-text
```

## Remaining top-five failures

- distributed evidence not ranked in top five: 2
- formula/symbol semantic mismatch: 6
- general lexical/semantic ranking miss: 2
- natural wording or underspecification: 1

| ID | Book | Slice | Likely cause | Question |
|---|---|---|---|---|
| BIO-017 | biology | canonical | distributed evidence not ranked in top five | How do nervous control and hormonal control coordinate responses in the human body? |
| PSC-002 | physical_sciences | canonical | formula/symbol semantic mismatch | What relationship is expressed by Snell's law? |
| PSC-003 | physical_sciences | canonical | formula/symbol semantic mismatch | State Ohm's law and its condition. |
| PSC-004 | physical_sciences | canonical | general lexical/semantic ranking miss | What is electromagnetic induction? |
| PSC-005 | physical_sciences | canonical | formula/symbol semantic mismatch | What is the mirror formula relating focal length, object distance, and image distance? |
| PSC-006 | physical_sciences | canonical | formula/symbol semantic mismatch | How are focal length, object distance, and image distance related for a lens? |
| PSC-023 | physical_sciences | canonical | general lexical/semantic ranking miss | Why does a car mirror make vehicles behind us look smaller |
| BIO-028 | biology | natural_student | distributed evidence not ranked in top five | Does pollen turn straight into a seed? What actually happens? |
| PSC-025 | physical_sciences | natural_student | formula/symbol semantic mismatch | If I turn up the voltage, why does more current flow through the same wire? |
| PSC-026 | physical_sciences | natural_student | natural wording or underspecification | How can moving a magnet make electricity in a wire? |
| PSC-027 | physical_sciences | natural_student | formula/symbol semantic mismatch | What formula tells where a mirror image gonna form? |

These causes are post-ranking diagnostics based on dependency labels and wording; they were not used to construct or score rankings.

## Limitations and next milestone

- The benchmark has only 61 answerable questions; one row is 1.6 percentage points overall and five points in the natural slice.
- Exact reviewed spans do not prove that a generated answer would be correct, faithful, well cited, or appropriately abstaining.
- Visual retrieval is caption/nearby-text only; extracted rasters were audited but no unapproved multimodal model was used.
- CPU timings are local warm-query measurements and some earlier fusion-only runs are excluded from this comparable frontier.

## Explicitly stopped or gated work

- BGE-M3 multi-vector/ColBERT escalation stopped after dense/sparse variants were slower without a natural-student gain.
- BGE-reranker-v2-m3 was stopped after an eight-query screen at 154 seconds p95; mxbai-base was stopped as runtime-infeasible after more than 300 seconds without a completed query.
- Local Gemma rewriting remained a separate unapproved model gate and was not downloaded or run.
- Locally generated diagram descriptions and multimodal ranking were not run because no multimodal model was approved; visual-caption retrieval and raster extraction were audited separately.
- Phase J generation was intentionally evaluated in a separate program with its own reviewed benchmark.

V1 retrieval and generation decisions are frozen. Future behavior changes require a new semantic baseline version.
