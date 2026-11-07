# Assessment submission gap plan

Status: T01 and T02 committed and published. T03 is complete; the user has
authorized implementation through T15 with a separate local commit for each
task. The user will push all commits manually at the end. T04 is implemented
and committed locally; T05 and T06 are implemented and verified. T07 is next. T16
visibility, sharing, recording, and submission actions remain outside this
authorization.

## Confirmed decisions

- Keep the two existing textbooks as a real-world demonstration corpus:
  `books/X Biology EM 2025-26.pdf` (257 pages) and
  `books/X Physics EM 2025-26.pdf` (327 pages).
- Add a separate open-benchmark corpus for evaluation.
- Limit paid execution to 500 API calls total, including failed requests,
  retries, development, baselines, ablations, and any judge calls.
- No submission deadline was provided. The task order below is dependency-based,
  not a promise of completion within a particular number of days.
- Preserve the existing single-book behavior and historical research. Introduce
  a versioned assessment pipeline instead of silently changing frozen v1 claims.
- The user's latest instruction authorizes local commits through T15.
  Repository visibility changes, sharing, pushing, and submission remain
  unauthorized.

## Scope and evaluation choices

The PDFs can demonstrate actual cross-document synthesis, but do not replace
the assignment's required open benchmark. Treat each PDF as one source;
chapters and pages must not be relabeled as separate documents.

Use HotpotQA as the initial benchmark candidate because its supporting-fact
annotations identify document titles and sentence locations:
https://hotpotqa.github.io/

T01 confirmed the upstream terms/schema and pinned the public Parquet mirror
because the original download host was unavailable. See
`reports/assessment_protocol_v1/README.md` and
`config/assessment_protocol_v1.json` for the completed selection and protocol.
Prefer a deterministically selected subset containing both
bridge and comparison questions and at least two distinct supporting documents
per question. Inspect a sample to check that the questions genuinely require
both sources, not merely that two sources are annotated.

Start with 60 questions: 15 development and 45 held out from pipeline tuning.
Source-only eligibility inspection happens before the selection is frozen; it
does not use retrieval/generation results. Record selection rules, seed, IDs,
source URL, version/date, and hashes.
Never choose rows based on which method wins. The subset is deliberately small;
report uncertainty and do not represent it as the full official leaderboard.

Use the documented HotpotQA distractor setting first: all methods see the same
10 supplied context paragraphs per question, without gold support labels. Explain
that this is bounded multi-document context selection, not full-Wikipedia search.
Do not mix distractor-setting scores with full-corpus leaderboard scores. A
pooled knowledge-base setting is optional only if time and evidence justify it,
and must be labeled as a separate protocol.

### Fair comparison

Generate answers for four arms:

1. Standard dense top-k retrieval.
2. Standard BM25+dense hybrid retrieval using RRF.
3. Proposed multi-document evidence selection and context assembly.
4. The proposed method with its new multi-document selection component removed.

Also report BM25-only retrieval metrics without requiring generated answers.
Choose the precise proposed method on development data after measuring the
standard baselines; do not assume document diversity or another heuristic helps.
Simple document-diversity selection is an initial hypothesis, not a guaranteed
winner. Prefer query-only and locally computed signals over extra model calls.

Use the same generator snapshot, prompt/citation contract, context-token budget,
output limit, decoding, corpus, and question IDs in all answer-producing arms.
Standard baselines must not inherit the proposed selector. The ablation removes
one named component and otherwise holds the pipeline fixed.

Primary context metric: complete supporting-document recall at a fixed context
budget. Supporting-fact recall/precision/F1, answer EM/F1, valid source-location
rate, citation completeness/support, abstention behavior, latency, tokens, and
cost are complementary metrics. Run the official answer/support scoring logic
where applicable and document any custom metric separately.

Use paired per-question comparisons and uncertainty intervals. Citation location
validity is not semantic support: supplement automated checks with a preselected
claim-level manual review packet and recorded rubric judgments. Do not use a
paid LLM judge by default.

### API call allocation

| Purpose | Planned calls |
|---|---:|
| Development: 15 questions x 4 arms | 60 |
| Final evaluation: 45 questions x 4 arms | 180 |
| One fresh rerun of the final evaluation | 180 |
| Diagnostics, failures, and contingency | Up to 80 |
| Maximum | 500 |

The final run and its full rerun have priority over exploratory spending.
Retrieval-only sweeps and deterministic scoring do not consume API calls.
Track every attempted paid request in a persistent ledger and reserve allowance
before dispatch; disable hidden SDK retries. Cached report rebuilding consumes
zero calls and must be distinguishable from fresh inference.

500 calls is not a monetary ceiling. Estimate dollars using actual model pricing
and configured input/output token limits before execution; seek approval if the
estimated spend is unacceptable. A call count alone does not guarantee low cost.

## Individual tasks and completion criteria

| ID | Task | Done when | Prerequisites |
|---|---|---|---|
| T01 | Freeze benchmark protocol and selection | Official benchmark source/terms verified; reproducible 15/45 selection and genuine two-document checks recorded; protocol, metrics, four arms, and call reservations frozen before final evaluation | None |
| T02 | Package reproducible inputs and environment | Hash-verified acquisition steps for benchmark, required embedding model, and demo PDFs; textbook distribution permissions checked; if redistribution is not allowed, document legal acquisition and explicit missing-file errors; tested setup requires no user's local `temp` or private cache; Git LFS and Windows path requirements documented | T01 |
| T03 | Introduce shared source and provenance contracts | Stable document IDs, content hashes, text/sentence locations for benchmark documents, and exact PDF page/span locations for textbooks survive chunking, merging, persistence, and citations; PDFs remain distinct documents; invalid printed-page mapping is repaired or explicitly omitted in favor of physical PDF pages | T01 |
| T04 | Add collection-scoped persistence and retrieval | A collection holds multiple documents; migrations preserve current books/chats; collection retrieval searches all selected documents without outside-collection leakage; snapshots retain complete provenance and corpus/config fingerprints | T03 |
| T05 | Build benchmark ingestion through the shared pipeline | Benchmark paragraphs and PDFs use the same source/evidence contracts and context-layer code; benchmark ingestion does not go through textbook-only PDF suitability rules; gold answers/support labels are separated from runtime data | T02, T03 |
| T06 | Implement standard baselines and scorer | Dense, hybrid, and BM25 retrieval baselines are runnable; answer EM/F1, all-document recall, supporting-fact metrics, failure inclusion, and paired reports are tested on fixed fixtures; raw per-question outputs are retained | T01, T05 |
| T07 | Implement and select multi-document context assembly | Proposed query-only/local selector tested against baselines on development rows; fixed budget and metadata-preserving packing; no gold labels used; one named ablation defined; weak evidence produces an explicit incomplete/abstention path rather than forced two-source citations | T04, T06 |
| T08 | Enforce claim-level synthesis and citation | Every factual claim carries resolvable supporting citations; nonempty answered claims cannot pass with zero citations; source/location pairs are checked together; support review distinguishes valid addresses from supported claims; invalid outputs and insufficient evidence are explicit, raw outputs retained | T03, T07 |
| T09 | Wire API, CLI, and minimal collection UI | A reviewer can ingest both PDFs, create a collection, ask across them, and open claim citations to the right document/location; existing single-book and online/offline controls still work; no extensive UI redesign | T04, T08 |
| T10 | Add call accounting and reproducible runner | One command acquires/verifies evaluation inputs, builds indexes, runs all arms, saves raw outputs, and rebuilds metrics/reports; another explicit cached mode rebuilds solely from raw outputs with no API calls; persistent 500-call ceiling includes failures/retries and survives resumes; secrets never enter artifacts | T02, T06, T08 |
| T11 | Run development experiments and freeze final configuration | All tuning restricted to the 15 development rows; benchmark/model/config hashes and selection rationale frozen; final rows not used for tuning; diagnostics fit the remaining call reservation | T07, T10 |
| T12 | Run final evaluation and honest failure analysis | All four arms evaluated on the same 45 held-out questions; raw outputs, metrics, ablation, failure cases, paired deltas, uncertainty, tokens/cost retained; a gain is demonstrated or failure to meet the requirement is reported plainly, never hidden by selecting winning rows | T11 |
| T13 | Validate textbook demo and edge cases | At least two manually verified questions genuinely require both textbooks and return supported claims from each PDF; relevant topics investigated in actual text before questions are chosen; missing evidence, conflicting evidence, invalid citations, and one-document-only support tested | T09, T10 |
| T14 | Write required root documents | Root `DESIGN.md` is 2-4 pages and covers architecture, choices, provenance, tradeoffs, failures, next steps; root `EVAL.md` records benchmark/version/subset, fair baselines, metrics, measured results, ablation, failures; README has exact setup/ingestion/API/CLI/evaluation examples and expected runtime/cost | T12, T13 |
| T15 | Verify clean-clone reproducibility and regressions | No local-only files required; LF checkout and Windows path behavior tested; line-ending-dependent hashes corrected with a documented versioned migration rather than rewriting old claims; smallest necessary raw artifacts tracked or provided via verifiable acquisition; backend/frontend pass; reserved fresh final rerun rebuilds results | T10, T12 |
| T16 | Prepare private repository and submission handoff | User approves private repo destination/visibility and sharing; meaningful implementation commits requested and made during work rather than one final dump; 5-10 minute recording or agreed live walkthrough shows two-document answer, exact citations, evaluation gain, and an evaluated failure; reviewer access and walkthrough link verified; deadline confirmed | T14, T15 |

## Implementation guardrails

- Keep historical v1 config, outputs, and research explanations intact. New
  behavior and corrected checksum/provenance policies receive their own version.
- Do not promise an evaluation improvement before measurement. If the proposed
  method loses, continue only on development data within the remaining budget;
  a new final test requires a newly declared protocol, not repeated tuning on
  the old final set.
- Verify evidence in both textbooks before selecting a demo question. Likely
  overlapping topics are hypotheses, not proof of a valid cross-document case.
- Do not expand to OCR, arbitrary file formats, full-Wikipedia search, new local
  model bake-offs, or GPU work merely to make the submission larger.
- Keep imported documents as untrusted evidence, not instructions. No benchmark
  support labels, answer rubrics, or annotated document selection enter runtime.
- Submission readiness requires all four hard requirements and every required
  deliverable, not a good aggregate score that hides a failed requirement.

## Outstanding user decisions

- Submission deadline/time remaining.
- Monetary comfort with the estimated cost of up to 500 calls.
- Private submission repository destination and authorization to change/share it.
- Final review before the user manually pushes the T03-T15 implementation commits.
- Whether the walkthrough will be recorded or live.

## T02 implementation review boundary

The input/environment task is complete. `requirements/README.md` records the
one-command setup, supported Windows/x64 Python profile, public source
identities, authorized-only PDF import, and clean-clone verification.

The implementation also fixes the application model downloader: it now
acquires the exact 11-file frozen BGE snapshot rather than every upstream file.
The existing single-book runtime and historical research remain unchanged.
No paid model calls were made. The user approved the T02 review, authorized its
commit, and pushed it manually. Local `main` and `origin/main` were verified at
`274c0c1024dce8cc2799b1fb8caf7cb691d89c18` before starting T03.

## T03 implementation review boundary

The shared source/provenance task is complete. See
`docs/SOURCE_PROVENANCE.md` for the contract and local inspection example.

- PDFs retain a document ID derived from their original bytes; pages and
  chapters remain locations inside that document, not extra sources.
- Benchmark documents retain their exact titles, original sentence indices,
  source/content hashes, and label-independent identities.
- Exact source spans survive fixed/structured chunking, overlap removal,
  context selection, word-budget clipping, atomic JSON reloads, and SQLite
  snapshot restart/regeneration.
- Citation resolution binds the document and location together and permits
  only source characters actually retained in the evidence.
- The new contract omits unverified printed-page labels in favor of physical
  PDF pages. Legacy v1 artifacts, generation behavior, and saved answers are
  not silently rewritten.

Verification covered all 600 frozen benchmark context documents and both
authorized PDFs. The dedicated locked x64 environment passed 130 focused
checks, including the frozen golden fixtures; 224 direct comparisons also
matched the pre-T03 legacy chunk/context outputs exactly.

The legacy model cache was absent, so model-backed verification used the exact
T02 application-local BGE snapshot through a process-local test resolver. This
did not change production cache discovery or the frozen configuration. The
dedicated `.venv-assessment` is now prepared locally for later tasks; no paid
model calls were made.

Interview takeaway: provenance is carried through every transformation, not
reconstructed as page labels after an answer is generated. A valid address is
still not proof that a claim is supported; T08 supplies that separate contract.
Collection persistence/retrieval, ingestion integration, and application wiring
remain T04, T05, and T09. The user authorized a local T03 commit and autonomous
implementation through T15; no pushes will be performed.

## T04 implementation checkpoint

Collection persistence and retrieval are implemented. Migration 4 is additive:
existing book-bound chats and their messages/snapshots remain unchanged.
Immutable source records can be shared by collections, and membership updates
are transactional and guarded by the previous source-set fingerprint.

The shared collection index searches all selected source documents together,
supports explicit subset scopes, and atomically saves validated corpora and
normalized vectors. Retrieval snapshots persist exact source maps and
source/corpus/profile/vector fingerprints; altered text, out-of-scope sources,
and nonretrieved character ranges are rejected on reload.

The locked environment passed 72 focused checks, including a real ten-document
HotpotQA scope encoded with the pinned BGE model, index reload, snapshot replay,
source-leakage rejection, and migration preservation.

This is the persistence/index foundation. T05 supplies reproducible benchmark
and PDF ingestion, and T09 exposes collection chats through the API/UI.
No paid model calls or pushes have been made.

## T05 implementation checkpoint

Shared ingestion exports the selected runtime questions and the exact
evaluation references into physically separate directories. The inference
loader never opens reference labels, rejects forbidden runtime fields, and
checks each ten-document question projection against T01's frozen fingerprint.

Benchmark paragraphs and authorized PDFs use the same immutable source units,
exact span metadata, normalized embedding/index format, and collection scopes.
The benchmark does not enter the textbook-only validation gate or get pooled
with the demonstration PDFs. CLI acquisition/check and authorized demo import
are documented in `requirements/README.md`.

Verification passed 44 focused checks and built the real 60-question/
600-document corpus. The compiled-input `--check` revalidated references and
left all corpus artifact hashes unchanged. Both authorized PDFs were imported
into a real two-document collection with 257/327 original page units and a
verified saved index. No PDF binaries or derived text were newly tracked.
Answer generation and paid execution remain later tasks.

## T06 implementation checkpoint

Standard dense top-k, BM25-only, and unweighted dense/BM25 RRF (k=60) are
implemented without the proposed selector. All references use the shared
source corpus and an exact 1,024 `o200k_base` token budget including headings.
The packer clips source characters safely rather than decoding broken token
prefixes, and its source maps are checked against selected evidence.

The unmodified pinned HotpotQA scorer and Apache license are vendored with
exact byte-hash checks. Official answer/support/joint EM/F1 are distinct from
custom complete-document and supporting-fact context coverage. Partial
sentences cannot inflate complete supporting-fact coverage. Failed outputs
remain in denominators, and paired 10,000-resample confidence intervals preserve
bridge/comparison strata.

Development-only retrieval measurements (15 questions, zero paid calls) give
complete-document recall of 80.0% dense, 86.7% hybrid, and 60.0% BM25. These are
baseline context results, not final evaluation or generated-answer gains.
The final T06 regression batch passed 29 focused checks, including the real
encoder/index scope, scorer parity, source isolation, and ingestion compatibility.
