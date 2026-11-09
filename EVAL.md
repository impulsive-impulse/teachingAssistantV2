# Assessment evaluation

## Result and readiness

The demonstrated gain is **complete supporting-document context coverage** at
the same 1,024-token budget: 97.78% proposed, 88.89% dense and 80.00% hybrid.
The proposed-minus-baseline paired intervals are positive for this primary
metric. This is not a claim of reliable end-to-end multi-hop reasoning: complete
fact coverage did not improve over dense, answer/joint gains over dense remain
uncertain, and invalid outputs are substantial.

The open evaluation and genuine fresh rerun are complete. The authorized PDF
demo has two source-reviewed answers, one generated and one explicit zero-call
adapter replay. Local Qwen remains unreliable, and two fresh successes under
the final PDF adapter are not established. Repository/access/recording handoff
is separate T16 work. Do not describe these results alone as a fully ready
submission.

## Benchmark, eligibility and frozen inputs

Use [HotpotQA](https://hotpotqa.github.io/), Yang et al. (2018),
[D18-1259](https://aclanthology.org/D18-1259/), public development **distractor**
setting. The original CMU host was unavailable, so the protocol explicitly pins
the public `hotpotqa/hotpot_qa` mirror, not a silently substituted dataset.
Every method sees the same ten original paragraphs for a question. This is not
fullwiki search or an official hidden-test/leaderboard result.

| Input | Frozen identity |
|---|---|
| Mirror revision | `1908d6afbbead072334abe2965f91bd2709910ab` |
| Artifact | `distractor/validation-00000-of-00001.parquet`, 27,452,575 bytes, 7,405 rows |
| Artifact SHA-256 | `c20b638ca82b21d04fe12e14ff417ad05153d4d215a65de54497fca4e972f7c6` |
| BGE-small-en-v1.5 revision | `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, curated 11-file MIT snapshot |
| BGE aggregate identity | `a76ed7f34fddfec52b0d6f9829f767fb2bcf1a05540e272b4ceb2e0081d846b4` |
| Protocol SHA-256 | `61bd6fb0b0fde78a8475c8fe789a9e343b3628f7bdb57a37ca61f5a989a25304` |
| Final pipeline SHA-256 | `ee191d743434eb85f7f5a44556d221c811a6e2395c813d5d0e64f5d15bb2c1ba` |

The seed is 1729; ordering is SHA-256 of namespace, seed and question ID, then
ID. Structural checks exclude bad contexts/support indices. Source-only
inspection excluded shortcuts, ambiguous premises and qualifier-only second
sources before experiments. Every selected row records two necessary source
roles. IDs, exclusions and semantic input hashes are in
`data\benchmarks\assessment_protocol_v1\selection_manifest.json` and
`reports\assessment_protocol_v1\necessity_review.json`.

| Split | Bridge | Comparison | Total |
|---|---:|---:|---:|
| Development/tuning | 12 | 3 | 15 |
| Held out from tuning | 36 | 9 | 45 |

All 600 context article titles are distinct across selected questions/splits.
Source eligibility review saw held-out sources; "held out" means excluded from
algorithm/prompt tuning, not unseen to the reviewer or necessarily to model
pretraining. The filtered cohort narrows the source distribution and is small.
Dataset/derived records are CC BY-SA 4.0 with attribution and indicated changes.

## Arms and metric definitions

Four generated arms share corpus/chunks, embedding snapshot, question IDs,
GPT-4o `2024-08-06`, temperature zero, literal-quote prompt/claim schema, 768
output tokens and 1,024 evidence tokens including headings. SDK retries and
paid judges are disabled.

| Arm | Definition |
|---|---|
| Dense | Normalized dense top-five; relevance-only packing |
| Hybrid | BM25/dense unweighted RRF, k=60, top-five; no proposed allocation |
| Proposed | Six documents, three local source units per document, title-link weight 0.2, round-robin allocation and shared packing |
| Without allocation | Bypass only the new selector; exactly hybrid evidence/packing |

BM25-only is an additional retrieval reference, not a generated fifth arm.
The ablation's equivalence is intentional. Identical terminal requests reuse
within a run; new fresh runs do not reuse previous generation.

**Custom context metrics:** complete document recall is the fraction with
actual retained text from both supporting articles, not just title headings.
Complete fact recall requires every annotated supporting sentence to survive
in full; partial sentence coverage is reported separately. Document/fact
precision exposes the cost of additional distractor evidence.

**Official metrics:** the unmodified HotpotQA scorer at
`3635853403a8735609ee997664e1528f4480762a` is vendored, Apache-2.0, SHA-256
`d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0`.
It scores the short answer and the union of cited original title/sentence
pairs, then joint scores. Failed/invalid output receives empty predictions;
every selected question remains in the denominator.

Citation-location validity and factual-claim citation completeness are custom
per-question ratios averaged over the full cohort; absent claims score zero.
They are not semantic support. False abstention is measured against this
source-answerable subset, not a calibrated unanswerable-question test.

## Development and final freeze

A retrieval-only declared grid selected the allocator using only 15 development
rows: complete-document coverage 100%, complete-fact coverage 93.33%, mean
728.8 evidence tokens. The first generation run failed many literal quotes;
revision 2 clarified contiguous quoting for **all** arms without relaxing the
validator. Both complete runs remain available, not just winning rows.

| Development run | Dense answer F1 | Hybrid answer F1 | Proposed answer F1 | Proposed invalid | New calls |
|---|---:|---:|---:|---:|---:|
| Initial | 36.67% | 43.33% | 26.67% | 60.00% | 50 |
| Same-ID confirmation | 40.00% | 33.33% | 53.33% | 33.33% | 52 |

An early cache policy independently resampled invalid hybrid/ablation responses;
temperature zero did not ensure identical results. Final execution corrected
reuse to include terminal invalid responses. Earlier development outputs are
preserved unchanged. `config\assessment_freeze_v1.json` binds the chosen
pipeline, protocol, 20 execution-file LF hashes and review IDs before final
effectiveness was seen. No held-out result was used to retune it.

## Held-out results: all 45 questions

Hybrid and the bypass ablation have identical context and raw predictions on
all 45 questions. Percentages below are cohort means.

| Metric | Dense | Hybrid / bypass | Proposed |
|---|---:|---:|---:|
| Complete-document context recall | 88.89% | 80.00% | **97.78%** |
| Complete-fact context recall | 88.89% | 80.00% | 88.89% |
| Answer EM | 48.89% | 42.22% | 55.56% |
| Answer F1 | 61.06% | 51.02% | 64.20% |
| Supporting-fact F1 | 59.24% | 49.26% | 58.22% |
| Joint F1 | 53.38% | 44.77% | 54.81% |
| Invalid output | 26.67% | 31.11% | 26.67% |
| Citation-location validity | 81.11% | 77.78% | 85.56% |
| Mean evidence tokens | 686.49 | 717.67 | 724.02 |

BM25-only complete-document/fact coverage is 55.56%, with mean 737.47 tokens.
The proposed document precision is 32.96%, versus dense 37.78% and hybrid
36.00%: broader coverage introduces extra sources.

Paired, question-type-stratified bootstrap: 10,000 resamples, seed 1729, 95%
intervals. Deltas and intervals below are **percentage points**, not relative
percentage improvements.

| Proposed gain | Delta | 95% interval |
|---|---:|---|
| Document coverage over dense | +8.89 | [+2.22, +17.78] |
| Document coverage over hybrid | +17.78 | [+6.67, +28.89] |
| Answer F1 over dense | +3.14 | [-8.24, +15.29] |
| Answer F1 over hybrid | +13.18 | [+0.58, +26.38] |
| Joint F1 over dense | +1.43 | [-10.00, +13.06] |
| Joint F1 over hybrid | +10.04 | [-1.85, +22.08] |

The primary coverage gain is supported; neither first-run joint comparison nor
answer gain over dense supports an unqualified significance claim.

## Genuine fresh clean-clone rerun

A separate LF checkout, independent locked x64 environment and **rebuilt public
index** ran all 45 questions/four arms again. Public data/model/tokenizer files
were explicitly transported and reverified; they were warm artifacts, not a
new cold-network download. No original virtualenv, private model cache, `.env`
or prebuilt benchmark index was copied. The original shared ledger was used.
This is fresh inference, not cached report replay.

| Fresh-run metric | Dense | Hybrid / bypass | Proposed |
|---|---:|---:|---:|
| Complete-document context recall | 88.89% | 80.00% | 97.78% |
| Answer F1 | 58.84% | 44.91% | 68.35% |
| Joint F1 | 51.08% | 38.66% | 58.62% |
| Invalid output | 28.89% | 37.78% | 22.22% |

Document coverage and its intervals reproduce. Fresh answer gain over dense is
+9.52 points [-3.07, +22.22], still uncertain; joint gain is +7.54
[-5.04, +20.23]. Fresh gains over hybrid are +23.44 answer F1
[+10.56, +37.22] and +19.96 joint F1 [+8.11, +32.63]. Do not select the
better run, average them as 90 independent questions, or hide the first run.
Both cohorts are the same 45 IDs.

## Source review and evaluated failures

Five preselected development questions and ten preselected held-out questions
were inspected across all arms: 20/40 opaque-arm cards, 26/71 claims. The exact
packets, rubric and judgments are retained under `reports\assessment_results_v1`.
Reviewer: **assistant source inspection**, not independent human signoff or a
formal entailment model. Formatting and knowledge of aggregates can weaken
blinding.

Held-out cards: 25 supported, 3 partial, 7 invalid, 5 abstained. Proposed cards:
7 supported, 1 partial, 1 invalid, 1 abstained. Development cards: 3 supported,
8 partial, 6 invalid, 3 abstained. These sampled counts are not full-cohort
human support rates.

Concrete failures include an unsupported 1449 date at a valid source address
(`ec1bc82ab392`); omitted film/actress or psychologist intermediate roles
(`a8264ac9206b`, `abb886992498`); an unsupported summed distance
(`fd9702cacfd7`); and ellipses or punctuation changes that invalidate otherwise
supported quotations (`038da6ea0471`). Source-qualified historical enrollment
comparisons must not become claims about current enrollment. Full packets
retain the original units needed to inspect these judgments.

## Textbook demonstration boundary

The authorized 2025-26 Biology/Physics PDFs contain 257/327 physical pages and
remain two distinct documents. The source-reviewed cases compare sunlight
handling/energy conversion and coleoptile/optical-ray bending. Review included
Biology 20/55/127 and Physics 14/27/74-75; the final returned citations are
Biology 55 + Physics 14, and Biology 127 + Physics 74.

Earlier local answers had valid source addresses but quoted activities or
diagram statements rather than the required mechanisms. The local ID-selection
adapter removes copying errors but does not guarantee useful selection.
Default-profile queries `a559820c-1a02-4b7c-8d8d-fec6cd0ecd8d` and
`b2d86387-ca1c-4aa0-8a5d-3374dc5d275f` abstained (135.75/166.26 seconds
generation). The first retrieval missed the energy-conversion fact; the second
over-abstained despite relevant chemical/optical clauses. **Neither counts as a
successful two-PDF answer.** One isolated local reasoning attempt also failed
JSON decoding; no generator defaults were changed or new model acquired.
Missing/conflicting evidence, invalid citations, one-source support and
source-review binding are covered separately.

The user later confirmed transmission rights and authorized at most six paid
OpenAI requests containing retrieved excerpts only. Exactly six were made.
The original generation outcomes were two completed first-question answers
and four validation failures on the second question. These failures are not
deleted or counted as fresh successes.

The final PDF profile uses structured source-clause ID selection, avoiding
invented unit kinds and changed quote punctuation. The last genuine native
second response selected both relevant clauses and answered
"No, different mechanisms: chemical vs. physical refraction." Its added
short-answer prose failed the frozen lexical screen. A separately versioned
adapter now extracts the existing, unambiguous No for a question explicitly
requesting yes/no. Claims, quotations, source choices and answer polarity are
unchanged. This is format adaptation, not a relaxed validator or a new answer.

| Reviewed case | Retained result | Source support |
|---|---|---|
| Sunlight mechanisms | Generated query `759d728a-f221-48a5-9a48-290e86e61594` | Optical convergence versus biochemical light-to-chemical energy conversion |
| Bending mechanisms | Cached adapter replay `6c0feb40-4beb-4476-86fc-987ae035232a` of native query `b1645e0e-30db-445c-bc62-22a9588708ae` | Chemical stimulus/auxin versus refraction across optical media |

Both received assistant source inspection against the original cited pages.
The second is **zero-call cached replay, not fresh inference**. Its original
failed row remains immutable, the UI labels the replay, and the complete local
receipt/source review is bound to the returned raw-output hashes.
`reports\assessment_demo_validation_v1.json` retains metadata, all six original
query IDs, failures, cost and limits without exporting textbook text.

PDFs, derived text, quotes and raw answers stay uncommitted. The six-call
transmission approval is not redistribution permission or standing permission
for more requests. Neither PDF generation profile is a benchmark arm.

## Operations, cost and reproduction

| Run | New attempted calls | Known token-based estimate |
|---|---:|---:|
| Development initial | 50 | $0.2145475 |
| Development confirmation (contingency) | 52 | $0.2448250 |
| Held-out final | 134 | $0.6261350 |
| Fresh final rerun | 134 | $0.6263950 |
| Authorized PDF demonstration | 6 | $0.0437425 |
| Total | **376 / 500** | **$1.7556450** |

Each final run retains 180 logical outputs with 46 same-run request reuses.
The ledger has no unfinished attempts; 135 attempts ended with invalid-claim
validation, not provider dispatch failure. Four are original PDF validation
failures, including the response later adapted by zero-call replay. No paid
judge was used. Remaining phase allowances: development 10, final 46, rerun 46,
contingency 22; these are not authorization for new experiments. The specific
six-call PDF approval is exhausted.

Prices recorded for this execution: $2.50/M input, $1.25/M cached input,
$10/M output. All observed attempts have usage; this is **not an invoice**.
The conservative 500-call input/output-cap estimate is $14.08, not a monetary
ceiling. Actual billed dollars are unavailable.

First-run proposed means: 1,281.44 input/154.40 output tokens, 2.19 seconds
generation, 1,236.76 ms shared ranking and 544.95 ms selection. Fresh means:
1,281.44/149.78 tokens, 2.17 seconds generation, 81.25 ms shared ranking and
354.90 ms selection. These exclude startup/index construction and are hardware/
warm-state sensitive; reused rows inherit original generation timing. They are
not total run wall-clock measurements.

Use the exact bootstrap, authorized ingestion and explicit fresh/cached commands
in [README.md](README.md) and [requirements/README.md](requirements/README.md).
The tracked `final` and `fresh_final` runs contain every raw question/arm output
(lossless gzip), references, pipeline, run manifest and metrics. Cached replay
requires dependencies and the public tokenizer only; it is zero inference.
Historical CRLF text checks use the explicit
[identity v2 profile](docs/HISTORICAL_ARTIFACT_IDENTITIES.md); binary hashes and
historical manifests are not rewritten.
