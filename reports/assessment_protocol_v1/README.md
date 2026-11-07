# Assessment Context Protocol v1

T01 freezes the benchmark selection and comparison rules **before any model
experiment**. It does not implement multi-document retrieval, produce new
answer-quality scores, or claim an improvement.

The source of truth is
[`config/assessment_protocol_v1.json`](../../config/assessment_protocol_v1.json).
The reproducible IDs and input fingerprints are in
[`selection_manifest.json`](../../data/benchmarks/assessment_protocol_v1/selection_manifest.json).
Source-necessity decisions are in [`necessity_review.json`](necessity_review.json).

## Why HotpotQA, and why keep the textbooks?

[HotpotQA](https://hotpotqa.github.io/) is a public, Wikipedia-based multi-hop
benchmark with question/answer pairs and supporting facts addressed by article
title and zero-based sentence index. It includes bridge questions that join
facts across sources and comparison questions that combine facts about two
subjects. The [original paper](https://aclanthology.org/D18-1259/) explains these
choices. This directly tests the context layer's cross-document evidence
coverage and provides more precise reference locations than answer strings alone.

The Biology and Physical Sciences PDFs remain the real-world demonstration
corpus. Each PDF is one source document. Chapters, pages, and chunks are not
relabeled as distinct documents to manufacture a multi-document result.
Textbook ingestion and the open benchmark must eventually use the same
source/evidence and context-layer contracts; that integration is T03-T09.

We use the **distractor setting**: every method receives the same ten supplied
Wikipedia paragraphs for a question. This is bounded multi-document selection
and synthesis, not search over all Wikipedia. We do not pool paragraphs across
questions, change the distractors, or compare these subset scores to fullwiki
or official hidden-test leaderboard scores.

## Provenance, license, and acquisition

The original release is `hotpot_dev_distractor_v1`, the public development set.
The original CMU download host did not resolve during preparation. We explicitly
use the public Hugging Face `hotpotqa/hotpot_qa` Parquet mirror rather than
silently substituting another dataset:

| Identity | Value |
|---|---|
| Mirror revision | `1908d6afbbead072334abe2965f91bd2709910ab` |
| Mirror artifact | `distractor/validation-00000-of-00001.parquet` |
| Bytes | 27,452,575 |
| SHA-256 | `c20b638ca82b21d04fe12e14ff417ad05153d4d215a65de54497fca4e972f7c6` |
| Source rows | 7,405 |
| Parser | PyArrow 25.0.0, available through `.[assessment]` |

The mirror revision, exact download URL, expected shape, and file checksum are
recorded in the protocol. The original JSON and the Parquet file are different
formats; original-host byte parity was not verified. The schema matches the
upstream documented fields, and each selected row's semantic fingerprint is
recorded for reproducibility.

The dataset is **CC BY-SA 4.0**, as stated by both the
[upstream README](https://github.com/hotpotqa/hotpot/blob/3635853403a8735609ee997664e1528f4480762a/README.md#license)
and the [dataset card](https://huggingface.co/datasets/hotpotqa/hotpot_qa).
Give the original authors credit, retain the license link, and indicate changes
when redistributing derived dataset material. The selection and source-review
artifacts in this directory and `data/benchmarks/assessment_protocol_v1/` use
the same [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) terms.
The questions, answers, context text, and source indices are not rewritten;
the subset, partitioning, hash-based context order, and review notes are our
documented changes.

The upstream code uses Apache 2.0, a separate license. We pin its evaluation
script at commit `3635853403a8735609ee997664e1528f4480762a` and SHA-256
`d35fc91a6db21d791dbdda11daf3856e9359f5701d54e3eefba20d88fecc02c0`.
T06 will integrate and check scoring parity; the original training model and
its obsolete PyTorch environment are not required for this protocol.

Attribution: Yang, Qi, Zhang, Bengio, Cohen, Salakhutdinov, and Manning (2018),
*HotpotQA: A Dataset for Diverse, Explainable Multi-hop Question Answering*,
EMNLP, https://aclanthology.org/D18-1259/.

## Selection algorithm and source-necessity screening

1. Verify the raw Parquet byte count and checksum before parsing.
2. Validate all 7,405 source rows. Parallel title/sentence arrays must align;
   IDs must be unique; source fields and sentence-index types must be valid.
3. Exclude nonstandard context counts, duplicate normalized article titles,
   missing/out-of-range/empty supporting sentences, and rows whose supporting
   facts do not address two distinct articles. All exclusions have stable IDs
   and reasons in the manifest.
4. Apply the documented source-only review exclusions. We inspected the
   question, answer, and both supporting paragraphs before running any model.
   Fifty inspected candidates were excluded for single-source shortcuts,
   qualifier-only second sources, ambiguous questions, or reference/premise
   problems. Sixty-five other rows failed structural eligibility.
5. Within each question type, sort by
   `SHA256("sarvam-context-v1:1729:" + question_id)`, then question ID.
6. Select in this fixed order: development bridge, development comparison,
   held-out bridge, held-out comparison. Reject normalized question duplicates
   and reuse of any normalized article title already selected, including
   distractors. Never change input order or the seed to obtain a better score.
7. Require a recorded role for each of the two supporting documents and an
   explanation of why the facts must be combined for every selected question.
   A missing review prevents publication of the frozen manifest.

| Split | Bridge | Comparison | Total |
|---|---:|---:|---:|
| Development | 12 | 3 | 15 |
| Held out from tuning | 36 | 9 | 45 |
| Total | 48 | 12 | 60 |

The 80/20 type mix approximates the source set's 5,918 bridge and 1,487 comparison
rows. The selected contexts contain 600 distinct article titles; neither gold
articles nor distractors are shared between selected questions or splits.
These are document identities, not 600 sentences from one article.

Examples from the development split:

- `5abe79c755429976d4830b2a`: Mesih Pasha identifies his uncle as Constantine XI;
  the emperor's biography supplies the beginning of his reign. The required
  relationship and year are not in the same paragraph.
- `5a8e276b5542995a26add468`: compare Swervedriver's 1989 formation with Incubus's
  1991 formation. Both dates are needed.

A counterexample we rejected is
`5ae1ee6d5542997283cd22fd`: the film paragraph already gives its title, year,
genre, and Taylor Nichols in the cast. Merely having a second annotated biography
does not make that a convincing two-source question.

This is an **assistant source-inspection record**, not a human quality signoff
or proof that a pretrained model cannot guess an answer. Eligibility screening
includes held-out source text; "held out" means excluded from algorithm and
prompt tuning, not unseen to the dataset reviewer. The screening is conservative
and narrows the original distribution. Report subset results under this protocol
name, not as unrestricted HotpotQA performance.

## Fair comparisons and ablation

Four answer-producing arms share the question IDs, candidate text, chunking,
embedding identity, generator, prompt/citation schema, token budget, and decoding:

| Arm | Purpose |
|---|---|
| `dense_top_k` | Standard relevance-only dense retrieval |
| `hybrid_rrf` | Standard BM25+dense RRF retrieval |
| `proposed` | Development-selected cross-document context selection/assembly |
| `without_cross_document_selection` | Remove only the proposed selector |

BM25-only retrieval is an additional reference without paid generation.
The proposed algorithm is a hypothesis, not a promised winner. T06-T07 will
implement baselines and choose the selector using development data; T11 will
freeze their exact algorithm settings before final evaluation. Baselines must
not inherit the new selector or be deliberately given weaker budgets.

The ablation can be identical to the hybrid baseline if removing the selector
returns that pipeline. In that case, report the equivalence honestly and reuse
identical requests instead of inventing another component merely to make an
ablation look distinct.

The fixed shared constraints are BGE-small at its existing pinned revision,
GPT-4o `2024-08-06`, temperature 0, 768 output tokens, and 1,024 evidence tokens
using `o200k_base`. Evidence headings count against the context budget.
No previous chat history, gold supporting facts, answers, question-type labels,
or review notes may enter retrieval or generation.

`runtime_projection` exposes only `id`, `question`, and `context`. Context order
is hash-based and independent of gold labels. The selection manifest is an
evaluation artifact and must not be passed as runtime evidence.

## Metrics and interpretation

Primary metric: **complete supporting-document recall** at the fixed evidence
budget, averaged over all selected questions. A question succeeds only when
both annotated articles have actual source evidence retained in the packed
context; retaining headings or document IDs without text is not success.

This does not establish that every needed fact was retained. Also measure
supporting-fact context precision/recall and complete supporting-fact coverage.
For synthesis, use the pinned official answer EM/F1, supporting-fact EM/F1, and
joint EM/F1 semantics. Score the short answer separately from explanatory prose;
map claim citations back to the original article titles and sentence indices.

Citation-address validity, factual-claim citation completeness, and semantic
citation support are separate measures. A real source location may still fail
to support the claim. The manifest preselects five development and ten held-out
questions for the same blinded claim-level review across all arms. T12 must
record actual judgments and limitations, not turn an automated lexical check
into a human support score.

Also retain invalid outputs, abstentions, operational failures, latency, token
usage, attempted call count, and actual cost. Missing/invalid answer and support
predictions receive empty predictions under the official scorer. Do not drop
failed questions from the denominator or replace them with easier ones.

Report per-question paired deltas, type slices, and 95% paired-bootstrap
intervals with 10,000 resamples and seed 1729. Do not claim statistical
significance when the interval does not support it. A gain over one weak
baseline is not a reason to hide a loss against the stronger hybrid baseline.
If improvement is not demonstrated, record the unmet requirement.

The held-out set is small. Pretraining contamination, annotation incompleteness,
short-answer exact-match sensitivity, historical source facts, and the bounded
ten-paragraph setting limit what conclusions it supports. Known source quirks
are retained and called out in the necessity review.

## API-call reservations

| Allocation | Calls |
|---|---:|
| Development, 15 questions x 4 arms | 60 |
| Final, 45 questions x 4 arms | 180 |
| Fresh final rerun, 45 questions x 4 arms | 180 |
| Contingency | 80 |
| Approved maximum | 500 |

This task made **zero model API calls**. Downloads and source inspection do not
consume this generation budget. T10 must implement persistent dispatch-time
accounting, failure/retry inclusion, and the final/rerun reservations.
SDK retries and paid judging are disabled by the protocol. Cached scoring from
raw outputs must be distinct from a fresh-inference rerun and use zero calls.

The 500-call ceiling is not a dollar ceiling. Before any paid run, estimate cost
from the pinned model's actual pricing and token limits and report the estimate.

## Reproduce T01

Use x64 Python 3.10+ and install the project with its benchmark reader:

```powershell
python -m pip install -e ".[assessment]"

New-Item -ItemType Directory -Force data\retrieval\cache\assessment_protocol_v1
curl.exe --fail --location --output `
  data\retrieval\cache\assessment_protocol_v1\hotpotqa-validation.parquet `
  "https://huggingface.co/datasets/hotpotqa/hotpot_qa/resolve/1908d6afbbead072334abe2965f91bd2709910ab/distractor/validation-00000-of-00001.parquet"

python scripts\build_assessment_protocol.py `
  --source data\retrieval\cache\assessment_protocol_v1\hotpotqa-validation.parquet `
  --check

python -m pytest -q tests\test_assessment_protocol.py
```

The downloaded raw file is a regenerable, ignored cache, not a required private
asset. T02 will add automated acquisition/environment setup; T10 will provide
the full one-command evaluation. These commands currently verify selection,
**not answer-generation results**.

`--preview` reports candidate IDs and missing reviews without publishing a
manifest. Running without `--check` creates a missing manifest or verifies an
identical existing one; it refuses to overwrite a changed frozen selection.
Protocol and review locks hash canonical semantic JSON so Windows CRLF and
Unix LF checkouts agree. Raw Parquet is verified by its exact binary hash.
Existing v1 research manifests are not modified.
