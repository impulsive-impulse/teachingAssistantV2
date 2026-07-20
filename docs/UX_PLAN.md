# Local Textbook Chat — UX and System Plan

## 1. Purpose

This document plans a single-user, locally hosted web application that turns a
supported English textbook PDF into a persistent, book-scoped RAG chat
experience.

The user will be able to:

1. Upload an English, digitally generated textbook PDF.
2. Wait while the application validates, extracts, structures, chunks, and
   indexes the textbook locally.
3. Keep the processed book in a persistent library across application restarts.
4. Start one or more chats that are permanently scoped to that book.
5. Ask independent questions whose answers use only retrieved textbook
   evidence.
6. Select the frozen online GPT-4o profile or frozen offline Qwen profile at the
   chat level and override that selection for an individual message.
7. Inspect the evidence behind an answer through a collapsed **View sources**
   control.
8. Regenerate an answer with the other generation backend while reusing the
   exact same retrieval result.
9. Inspect runtime diagnostics when needed.
10. Delete books, chats, and their derived local artifacts.

The first release is a Windows-only, developer-run localhost application. It
uses a FastAPI backend and a React frontend, starts from one command, and opens
the browser automatically. It is not a hosted service and does not have user
accounts or multi-user isolation.

## 2. Product decisions fixed for the first release

| Area | Decision |
|---|---|
| User model | One local user; no authentication or accounts |
| Library | Persistent library containing multiple processed books |
| Retrieval scope | Every chat is permanently restricted to one explicitly selected book |
| Accepted content | English, digitally generated textbook PDFs with usable text layers |
| Rejected content | Scans without adequate text, corrupt/encrypted PDFs, papers, reports, novels, and PDFs with unreliable structure or provenance |
| OCR | Not supported |
| Metadata review | No manual chapter or page-map correction step |
| Indexing hardware | CPU only; CUDA/GPU support is deferred |
| Retrieval | Uploaded-book runtime adapter using the frozen Retrieval Baseline v1 algorithm and parameters |
| Online generation | Frozen `gpt-4o-2024-08-06` profile, 768 output tokens |
| Offline generation | Frozen Qwen3-8B Q4_K_M profile through the evaluated llama.cpp runtime, 384 output tokens |
| Backend selection | Chat-level default plus per-message override |
| Streaming | Both online and offline answers stream to the UI |
| Conversation semantics | Transcript is persisted and displayed, but every question is retrieved and generated independently |
| Grounding | Answers use only the supplied book evidence and abstain when it is insufficient |
| Online failure | Show the failure; do not automatically retry, switch providers, or suggest a provider fallback |
| Settings | Baseline model names, prompt, retrieval parameters, and output limits are not user-editable |
| App mode | Windows localhost, developer-run, one launch command |

## 3. Scientific and architectural boundary

### 3.1 What is frozen research

The following files remain the source of truth and must not be edited to make
the web application work:

- `config/retrieval_baseline_v1.yaml`
- `config/generation_baseline_v1.json`
- `reports/retrieval_baseline_v1/`
- `reports/generation_baseline_v1/`

The research baseline was validated against two known books whose source
filenames, `book_id` values, printed-page offsets, chapter boundaries, processed
page paths, and index paths are explicitly frozen. Its reviewed retrieval
benchmark contains 66 questions and its generation benchmark contains 40
questions. Those validation claims do not automatically extend to a newly
uploaded textbook.

### 3.2 What the application may truthfully claim

For the two original research books, the application can use and identify the
actual frozen Retrieval Baseline v1 artifacts when their file checksums match.

For any other accepted textbook, the application uses an **Uploaded Textbook
Runtime Profile derived from Retrieval Baseline v1**. It preserves the winning
retrieval algorithm and fixed parameters, but replaces book-specific inputs
with automatically derived inputs for that upload. It must not label a new
book's retrieval quality as benchmark-validated or claim that the new book is
part of Retrieval Baseline v1.

The generation profiles can remain exactly frozen because their behavior is
defined by model, prompt strategy, context strategy, decoding settings, output
schema, and output ceiling. Their published quality metrics still apply only to
the reviewed 40-question benchmark, not to every uploaded book.

### 3.3 Three clearly separated configuration layers

1. **Frozen research configuration**
   - Read-only v1 YAML/JSON files already in the repository.
   - Used for integrity checks and as the source of fixed algorithm values.

2. **Uploaded-book manifest**
   - Generated once per accepted PDF.
   - Contains its checksum, title, generated `book_id`, page map, chapter map,
     artifact locations, extraction metrics, and compatibility declaration.
   - Contains no tunable model or retrieval choices.

3. **Application settings**
   - Contains operational paths, ports, API-key readiness, and UI preferences.
   - Cannot override frozen retrieval or generation behavior.

This separation prevents a product convenience from silently changing a
research decision.

## 4. Baseline behavior carried into the application

### 4.1 Retrieval contract

Each accepted uploaded textbook uses these fixed values from Retrieval Baseline
v1:

- Search is restricted to the explicit `book_id` attached to the chat.
- The searchable field is `cleaned_text`.
- Front matter is excluded from the searchable corpus.
- Fixed chunks target 600 tokens with 100 tokens of whole-boundary overlap.
- Chunks do not cross detected chapter boundaries.
- All contributing PDF pages, textbook pages, chapter metadata, and section
  metadata are retained.
- Dense retrieval uses `BAAI/bge-small-en-v1.5` at the frozen revision,
  384-dimensional normalized embeddings, and the frozen query prefix.
- Dense indexing and query embedding run on CPU with batch size 16.
- Lexical retrieval uses the in-repository Okapi BM25 implementation with
  `k1=1.5`, `b=0.75`, and the frozen tokenizer.
- The frozen textbook synonym rules remain unchanged in the first release.
- Formula, table, and visual specialist branches use the existing activation
  patterns, page filters, representations, and lifting behavior.
- All active rankings are combined through reciprocal-rank fusion with
  `rrf_k=60` and equal source weights.
- The final result contains exactly five evidence chunks.
- Context assembly uses the frozen overlap-aware, metadata-preserving merge,
  with an eight-word minimum and 140-word maximum exact overlap check.
- Retrieval is gold-blind. No benchmark labels or answer spans are available to
  the application at query time.

The existing science-oriented synonym rules are retained because the first
release does not alter frozen retrieval behavior. They only activate when their
specific trigger fragments occur. Textbooks outside the reviewed science
domain receive no new subject vocabulary in this release. This is a documented
coverage limitation, not a reason to generate unreviewed synonyms silently.

### 4.2 Specialist evidence behavior

The application does not introduce image understanding or OCR. It reuses the
researched text-layer heuristics:

- **Formula specialist:** detects equation-like pages, builds equation-line
  context with one neighboring line, and normalizes the same operator/unit
  forms as the baseline.
- **Table specialist:** detects table-bearing pages and constructs flattened
  row representations with repeated detected headers.
- **Visual specialist:** detects image-bearing pages and retrieves caption text
  plus nearby lines; if no caption is found, it uses the existing fallback
  representation.

The UI must not imply that diagrams have been visually interpreted. A source
may be labeled “visual/caption evidence,” but not “diagram understood.” Tables
may lose row/column geometry, and equations may have degraded symbols because
those are known source-extraction limitations.

### 4.3 Generation contract shared by both backends

Every new question follows the shared Generation Baseline v1 pipeline:

- Prompt strategy: P1.
- Context strategy: retrieved top five, page-order compact evidence.
- Temperature: `0.0`.
- No conversational history in the prompt.
- No query rewriting from prior messages.
- No generation reranking.
- No access to benchmark gold labels.
- The prompt states that only supplied textbook evidence may be used.
- The model must return `insufficient_evidence` when the evidence cannot support
  an answer.
- Output is the frozen five-field grounded-answer object:
  `status`, `answer`, `selected_evidence_ids`, `citations`, and
  `missing_information`.
- Evidence IDs and page citations are validated against the exact evidence sent
  to the model before the answer is committed to the transcript.

The application may adapt display labels for page provenance, but it must never
invent a printed textbook page. An accepted book must have a reliable numeric
printed-page mapping for its instructional body. PDF page is always retained as
the immutable source coordinate.

### 4.4 Online profile

- Provider: OpenAI Responses API.
- Model sent to the provider: `gpt-4o-2024-08-06` rather than a moving alias.
- Maximum output: 768 tokens.
- Temperature: `0.0`.
- Strict structured-output schema.
- API key: `OPENAI_API_KEY` loaded from the process environment or repository
  `.env`, never entered or displayed in the browser.
- Automatic SDK retries: disabled.
- Automatic cross-provider retry: disabled.
- Retrieved textbook excerpts and the question leave the machine in this mode.

### 4.5 Offline profile

- Engine: llama.cpp, frozen build `10046`, commit
  `32e789fdfd598e9a1872da55ac941e4d94f030bd`.
- Model repository: `Qwen/Qwen3-8B-GGUF`.
- Model revision:
  `7c41481f57cb95916b40956ab2f0b139b296d974`.
- File: `Qwen3-8B-Q4_K_M.gguf`.
- Required SHA-256:
  `d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785`.
- Quantization: Q4_K_M.
- Thinking: disabled.
- Maximum output: 384 tokens.
- Temperature: `0.0`; seed: `42`.
- CPU runtime: context size 8192, ten inference threads, ten batch threads,
  batch 512, micro-batch 256, zero GPU layers, one parallel slot.

The backend keeps one llama.cpp process and the model resident after first use.
Because the frozen runtime permits only one parallel slot, generation requests
are serialized through a local queue. Stopping an answer cancels the active
request; stopping the server is a last-resort recovery action if the runtime
does not release the request cleanly.

## 5. Product information architecture

The application has five primary surfaces.

### 5.1 Startup and system readiness

The first screen appears while the backend performs local readiness checks. It
contains a compact status list:

- Application database ready.
- Writable application-data directory ready.
- Frozen retrieval and generation configurations valid.
- BGE embedding model available and checksum/revision compatible.
- OpenAI mode available or unavailable based on `.env` and SDK readiness.
- Offline mode ready, setup required, downloading, loading, or unavailable.
- CPU and memory summary.

The library can open even if a generation provider is unavailable. Provider
availability is shown non-blockingly. If neither provider is ready, books can
still be uploaded and indexed, but chat submission is disabled with a precise
reason.

If the offline runtime or model is missing, the startup surface exposes **Set
up offline model**. It explains the download size, expected disk requirement,
expected memory requirement, and that generation may be slow on CPU. Setup
downloads only the pinned artifacts, verifies them, and never substitutes a
newer model or engine build.

### 5.2 Library

The library is the default post-startup view. It contains:

- **Add textbook** action.
- Search/filter by inferred title.
- A card or row for every book, including cover placeholder, title, page count,
  chapter count, ingestion date, status, and last-opened time.
- Status values: `Validating`, `Processing`, `Indexing`, `Ready`, `Failed`, and
  `Deleting`.
- A progress summary on books that are not ready.
- **Open**, **New chat**, **View processing details**, and **Delete** actions.
- A recoverable error explanation and **Remove failed upload** action for failed
  books.

Only books in `Ready` state can create or open a chat. Selecting a processing
book opens its progress view rather than a partially functional chat.

### 5.3 Upload and processing view

The upload interaction supports drag-and-drop and file selection. It accepts
one PDF at a time so that each job has an unambiguous status and error report.

The view progresses through named, user-readable stages:

1. Uploading locally
2. Checking duplicate
3. Validating PDF
4. Validating textbook suitability
5. Extracting pages
6. Detecting printed pages and chapters
7. Cleaning and annotating text
8. Building 600/100 chunks
9. Building formula, table, and visual representations
10. Loading the embedding model
11. Creating dense indexes
12. Creating BM25 indexes
13. Verifying artifacts
14. Ready

Each stage shows a status icon, current page or item count when meaningful, and
elapsed time. The browser receives progress through server-sent events (SSE).
The durable job record remains the source of truth so refreshing or reopening
the application restores the current state.

The user can leave this view while indexing continues. Chat is unavailable for
that book until the final atomic transition to `Ready`.

### 5.4 Book detail

The book detail view shows:

- Inferred title and source filename.
- PDF checksum abbreviation.
- Total pages and searchable instructional pages.
- Detected chapters and their page ranges.
- Extraction quality summary.
- Formula/table/image-bearing page counts.
- Index creation date and runtime-profile version.
- Existing chats for the book.
- **New chat**, **Open source PDF**, **Processing details**, and **Delete book**.

This is an inspection view, not an editing view. There is no manual correction
workflow for title, page mapping, or chapter boundaries in the first release.

### 5.5 Chat

The chat layout contains:

- Left sidebar: library navigation, the current book, chats for that book, new
  chat, and delete chat.
- Header: book title, global backend toggle, provider readiness indicator, and
  diagnostics button.
- Transcript: persisted user questions and assistant answer attempts.
- Composer: question field, per-message backend selector, send/stop button, and
  online-disclosure state.

The book selector is not changeable inside an existing chat. Switching books
means returning to the library or opening a different book's chat. This makes
book scope explicit and prevents accidental cross-book retrieval.

The global toggle sets the chat's default backend. The composer inherits that
setting but allows a one-message override. A per-message override does not
change the global default.

When online mode is selected, a persistent disclosure near the composer says:
“Your question and retrieved textbook excerpts will be sent to OpenAI.” The
first online submission in an application session requires acknowledgement.
The disclosure is informational after acknowledgement and cannot be hidden
while online mode is active.

## 6. Textbook acceptance and rejection gate

Because there is no manual review and no OCR, validation must be conservative.
A file becomes a library book only after every required gate passes. Proposed
initial thresholds below belong to the uploaded-book adapter, not to the frozen
research baseline; they should be recorded in a versioned ingestion policy.

### 6.1 File and PDF integrity

The backend streams the upload to a temporary file while calculating SHA-256.
It never trusts the browser filename as a storage path.

Reject when:

- Extension or parsed content is not PDF.
- The PDF cannot be parsed completely.
- It is password protected or encrypted.
- It has zero pages or exceeds an application-configured local safety limit.
- Page traversal or text extraction throws unrecoverable structural errors.

No permanent book row or artifact directory is published before these checks
pass.

### 6.2 Duplicate detection

The PDF SHA-256 is the content identity.

- If the checksum belongs to a `Ready` book, do not upload or index it again.
  Show **Already in your library** and open the existing book.
- If it belongs to an active ingestion job, open that job's progress view.
- If it belongs to a failed job, allow a clean retry after removing only that
  failed job's temporary artifacts.
- A renamed but byte-identical PDF is still the same book.

### 6.3 Extractable text gate

Extract raw text from every page with `pypdf`. Measure, at minimum:

- Pages with non-whitespace text.
- Character count per page and median character count.
- Alphabetic-character ratio.
- Replacement-character ratio.
- Pages containing images but negligible text.
- Long runs of empty or near-empty pages.

The initial policy should reject a PDF when more than 10% of likely
instructional pages are image-only/near-empty, when extracted prose is too
sparse to build meaningful chunks, or when corrupted characters exceed the
policy threshold. Front matter and intentionally blank pages are classified
before the final ratio is calculated so they do not create false rejection.

The rejection message distinguishes “scanned or image-only,” “text extraction
is corrupted,” and “not enough instructional text.” It does not offer OCR.

### 6.4 English-language gate

Language detection runs locally over deterministic samples from the beginning,
middle, and end of the instructional body. The sample excludes tables of
contents, indexes, references, and pages dominated by formulas.

Accept only when the aggregate language confidence is English and the great
majority of prose-bearing pages have Latin-script instructional text. Reject
mixed or ambiguous books rather than indexing them without review. Numbers,
formula symbols, and scientific names are ignored when estimating language.

### 6.5 Textbook-type gate

“Any supported book” means any English textbook that passes this gate, not any
PDF. Classification is local and deterministic in the first release.

Positive textbook signals include:

- A table of contents or PDF outline with multiple instructional units.
- Repeated chapter/unit/lesson headings.
- Hierarchical numbered sections.
- Exercises, activities, examples, summaries, learning objectives, or review
  questions distributed across the book.
- A stable page-label sequence across a substantial instructional body.
- Repeated running headers consistent with chapter or book structure.

Negative signals include:

- Paper structure dominated by abstract, methods, results, references, and a
  small page count.
- Report structure dominated by executive summary, findings, appendices, and
  organizational boilerplate without instructional chapters.
- Novel-like continuous prose with no instructional hierarchy, exercises, or
  sectional teaching structure.
- Slide-deck or presentation formatting.

The gate requires multiple independent positive signals and no dominant
negative classification. The stored processing report records which signals
were observed. Ambiguous content is rejected because the first release has no
human adjudication screen.

### 6.6 Printed-page and front-matter mapping gate

Page provenance is required for grounded answers. Mapping uses evidence in this
order:

1. Valid PDF page labels, when present.
2. Numeric footer/header labels extracted consistently from consecutive pages.
3. Table-of-contents printed page numbers reconciled with detected chapter
   heading locations.

The application derives a constant or explicitly segmented mapping from PDF
page number to printed textbook page. Roman-numbered front matter may be stored
for inspection but is excluded from retrieval. Covers, copyright pages, and
unmapped front matter receive no numeric textbook page.

Accept only if the numeric instructional body has a monotonic mapping with high
confidence and detected chapter starts agree with it. Reject if mappings are
conflicting, discontinuous without an explainable section transition, or too
weak to validate automatically. This strictness is necessary because the
frozen generation schema validates both PDF and textbook page citations.

### 6.7 Chapter detection gate

Chapter discovery reconciles three sources:

1. PDF outline/bookmarks.
2. Parsed table-of-contents entries.
3. Chapter/unit heading text found on mapped source pages.

For each proposed chapter, store number or stable ordinal, normalized title,
printed start page, PDF start page, PDF end page, detection sources, and
confidence. A chapter start is accepted only when the title or a strong heading
variant occurs near the expected page. Boundaries must be ordered,
non-overlapping, and cover the instructional body.

If the system cannot establish a usable chapter hierarchy without manual
review, the book is rejected. It must not quietly treat the entire PDF as one
chapter because that would weaken the baseline's chapter-boundary isolation.

## 7. Ingestion and index-building pipeline

### 7.1 Durable job creation

After upload and checksum calculation:

- Create an ingestion job with a generated UUID.
- Store the upload in a job-scoped temporary directory.
- Persist stage, progress, timestamps, checksum, and policy version.
- Acquire a checksum lock so two browser actions cannot process the same PDF.
- Run only one CPU-heavy indexing job at a time in the first release to avoid
  competing with local inference and exhausting memory.

Jobs run outside the HTTP request lifecycle. Closing the browser does not stop
them. On backend restart, a job that stopped before artifact publication is
marked interrupted and safely restarted from the last verified stage or from
the beginning of its current non-atomic stage.

### 7.2 Page extraction

For every PDF page, produce the established page-record fields:

- `book_id`
- `source_file`
- `pdf_page_number`
- `textbook_page_number`
- `chapter_number`
- `chapter_title`
- `section_title`
- `raw_text`
- `cleaned_text`
- `text_length`
- `has_image`
- `has_table`
- `has_equation_like_text`
- `extraction_notes`

`raw_text` is immutable text-layer output. `cleaned_text` applies the existing
whitespace normalization and conservative alphabetic line-break dehyphenation.
Book-specific removal of the original research books' government running line
must not be generalized blindly. The uploaded-book adapter instead detects
repeated headers/footers across pages and removes only high-confidence repeated
running material, recording each removal rule in the book manifest.

The existing section-title, equation, table, figure-reference, and embedded
image heuristics remain unchanged. Dynamic chapter metadata is attached only
after page mapping and chapter detection have passed.

### 7.3 Searchable-page selection

Include a page in retrieval only when:

- It belongs to the accepted instructional body.
- It has a numeric textbook-page mapping.
- It is not classified as cover, copyright, table of contents, index,
  references, or other front/back matter.
- Its cleaned text is non-empty.

Excluded pages remain in the page manifest so book diagnostics can explain the
decision.

### 7.4 Chunk construction

Run the existing deterministic fixed chunker:

- Target 600 frozen tokenizer tokens.
- Carry approximately 100 tokens of whole-boundary overlap.
- Prefer cleaned-text lines and sentence boundaries before hard wrapping.
- Never cross a chapter boundary.
- Preserve contributing PDF pages, textbook pages, chapter, section, previous
  chunk ID, next chunk ID, token count, and corpus order.
- Generate stable chunk IDs from `book_id`, strategy, chapter/page provenance,
  and ordinal rather than filesystem names.

The complete chunk corpus is written before indexes are built and is hashed for
cache invalidation.

### 7.5 Specialist corpora

Build all three researched specialist representations for the book:

- Formula/equation context corpus from pages flagged
  `has_equation_like_text`.
- Table row/header corpus from pages flagged `has_table`.
- Visual caption context corpus from pages flagged `has_image`.

Empty specialist corpora are valid. At query time, an activated branch with no
documents contributes no ranking rather than failing the entire question.

### 7.6 Dense index construction

- Resolve the exact pinned BGE-small revision from the local model cache.
- If absent, download it during an explicit model-setup step with visible
  progress; ingestion pauses in `Waiting for embedding model` until setup is
  complete.
- Load on CPU only.
- Embed the fixed chunk corpus with the frozen document prefix and batch size.
- L2-normalize embeddings.
- Build separate per-book matrices for fixed chunks and each specialist corpus.
- Persist matrices with corpus fingerprint, model revision, dimensions,
  strategy version, and book checksum.

An existing index is reusable only when every fingerprint field matches. A
partial or incompatible cache is rebuilt; it is never silently treated as
valid.

### 7.7 BM25 construction

Build book-local BM25 structures for the fixed chunks and each specialist
corpus using the frozen tokenizer, `k1`, and `b`. BM25 may be reconstructed on
application startup from persisted corpora if the implementation does not have
a stable serialized format. The book is not marked ready until reconstruction
has been exercised successfully once.

### 7.8 Artifact verification and publication

Before `Ready`:

- Re-read the manifest and processed pages.
- Confirm sequential PDF numbering and unique IDs.
- Confirm all searchable chunks reference valid pages and one book only.
- Confirm no chunk crosses a chapter boundary.
- Confirm embedding row counts equal corpus row counts.
- Confirm embedding dimensions and model revision.
- Confirm specialist indexes match their corpora.
- Execute one internal retrieval health query without generation and require
  five results when the corpus contains at least five chunks.
- Hash every durable artifact and add it to the book manifest.

Publish by atomically renaming the completed staging directory into the book's
final directory and changing the database status to `Ready`. The library must
never observe half-published artifacts.

## 8. End-to-end question flow

### 8.1 Submission

When the user sends a question:

1. Reject empty or whitespace-only input.
2. Snapshot the selected chat and its immutable `book_id`.
3. Resolve the message backend from the per-message override or chat default.
4. Confirm the book is `Ready` and its artifact manifest is compatible.
5. Confirm the selected generation backend is ready.
6. If online, confirm the session disclosure was acknowledged.
7. Persist the user message and an answer attempt in `Queued` state.

No earlier transcript messages are included. The submitted text is the complete
retrieval query and complete generation question.

### 8.2 Retrieval

For the selected book only:

1. Apply the frozen synonym expansion rules to the original question.
2. Determine which specialist branches activate using the frozen patterns and
   designated original/processed query source.
3. Embed the processed query with the frozen BGE query prefix.
4. Rank all fixed chunks through dense cosine similarity.
5. Rank all fixed chunks through BM25.
6. Rank each activated specialist corpus through its dense and BM25 branches.
7. Lift specialist/page evidence to fixed child chunks using the frozen method.
8. Fuse complete rankings with RRF `k=60` and deterministic corpus-order ties.
9. Select exactly the top five chunks.
10. Run overlap-aware metadata-preserving context assembly.
11. Convert the evidence to compact page-order generation blocks `E1` through
    `E5`.

Persist a retrieval snapshot before generation. It includes the original
question, processed query, book and artifact fingerprints, activated signals,
ranked evidence, assembled context, component ranks/scores, and latency. The
snapshot is immutable and is the unit reused for regeneration.

### 8.3 Prompt construction

Construct the P1 prompt from only:

- The current question.
- The five compact evidence blocks.
- The frozen grounding, abstention, student suitability, and JSON-output
  instructions.
- Query/retrieval-activated specialist instruction where the frozen generation
  logic provides it.

The research benchmark carried expected answer depth. A normal uploaded-book
question does not have that reviewed label. The uploaded-textbook adapter must
therefore define one fixed runtime depth—`medium`—for all questions and record
this as a baseline adaptation. It must not infer depth from chat history or
expose a user control that changes the frozen prompt.

### 8.4 Generation and streaming

The backend exposes one SSE stream per answer attempt with typed events:

- `queued`
- `retrieval_started`
- `retrieval_completed`
- `generation_started`
- `answer_delta`
- `usage`
- `validation_completed`
- `completed`
- `cancelled`
- `failed`

Both providers produce structured JSON, so arbitrary raw JSON syntax must not
be shown as the assistant answer. The stream adapter incrementally extracts the
JSON `answer` string and emits decoded answer text as `answer_delta`. Citations,
status, selected evidence, and missing information remain provisional until the
complete object is parsed and validated.

If safe incremental extraction cannot continue, the card stays in a neutral
“Generating answer…” state and renders the answer only after final validation.
This is preferable to displaying malformed JSON or unvalidated citations.

For online mode, use the streaming form of the Responses API with the exact
frozen request fields and no retries. For offline mode, forward llama.cpp's
existing streamed OpenAI-compatible completion. Transport streaming changes
latency presentation, not prompt or decoding behavior.

### 8.5 Output validation

After the provider stream closes:

- Parse the complete JSON object.
- Require exactly the five frozen fields.
- Validate `status`.
- Validate every selected evidence ID exists in the retrieval snapshot.
- Validate every citation's PDF and textbook page belongs to its evidence unit.
- Validate array and string field types.
- Store provider model identity, token usage, first-token time, total generation
  time, and validation errors.

Only a valid object becomes a normal completed assistant answer. If generation
completed but schema/citation validation failed, keep the diagnostics and show
an answer error state; do not quietly strip invalid citations and present the
text as grounded.

### 8.6 Answer presentation

A valid answered response shows:

- Streamed answer text.
- Compact page citation chips derived from validated citation objects.
- Backend badge: `Online · GPT-4o` or `Offline · Qwen3-8B`.
- Completed/cancelled/error state.
- **View sources** collapsed by default.
- **Regenerate with online/offline** action for the opposite backend.

Opening **View sources** shows only the evidence supplied for that attempt,
ordered `E1` to `E5`. Each item contains:

- Evidence ID and retrieval rank.
- PDF page and printed textbook page(s).
- Chapter and section when available.
- Expandable full evidence excerpt.
- Specialist badges when formula, table, or visual retrieval contributed.

Internal scores and timings stay out of the normal source view and belong in
the developer diagnostics panel.

An `insufficient_evidence` response uses a distinct, non-alarming presentation:
“The retrieved textbook evidence is not sufficient to answer this question.”
It may display validated `missing_information`, and it still offers **View
sources** so the user can understand what was retrieved.

### 8.7 Regeneration with the other backend

Regeneration creates a new answer attempt under the same user message. It:

- Reuses the immutable retrieval snapshot byte-for-byte.
- Reuses the same evidence IDs, ordering, context, and prompt content.
- Changes only the selected frozen generation provider and its provider-specific
  output ceiling.
- Does not run retrieval again.
- Keeps both attempts accessible through an attempt switcher so comparisons are
  not destructive.

The UI labels the attempts clearly and does not imply that different answers
were caused by different retrieval evidence.

### 8.8 Cancellation

While retrieval or generation is active, **Send** becomes **Stop**.

- During retrieval, cancellation stops the request after the current safe CPU
  operation and records `cancelled`.
- During online generation, close the provider stream and do not retry.
- During offline generation, close the local request. If llama.cpp continues
  occupying its only slot, use the backend's controlled cancellation/recovery
  path and restart the resident server if necessary.
- Preserve partial streamed text only as diagnostic data. Mark it visibly as
  incomplete and never attach validated citations to it.

The user may submit the question again after cancellation.

## 9. Conversation semantics

Chats are organizational transcripts, not conversational model sessions.

- Every chat belongs to exactly one book.
- Messages and answer attempts persist across restarts.
- Previous messages are displayed in chronological order.
- A new question does not include previous questions or answers in retrieval or
  generation.
- Pronouns and implicit follow-ups are not resolved from context.

The empty-chat state should explain this succinctly: “Each question is answered
independently from this textbook. Include the topic in your question.” If a user
asks “Can you explain that more?”, the system processes those exact words and
will usually abstain. It must not silently inject transcript context.

## 10. Provider readiness and setup

### 10.1 Online readiness

At startup and before an online request:

- Load `.env` without overwriting already defined process variables.
- Check only whether `OPENAI_API_KEY` is present; never return its value to the
  browser or logs.
- Confirm the optional OpenAI SDK is installed.
- Report `Ready`, `Missing API key`, or `SDK not installed`.

Do not make a paid readiness call. Provider authentication and availability are
verified on the first explicit user request. A failure is attached to that
attempt with a concise message and correlation metadata that excludes secrets
and evidence text.

### 10.2 Offline discovery

Search the configured application model/runtime directories and any known
existing research artifact paths. Reuse an artifact only after verifying:

- Exact filename.
- Exact byte checksum.
- Expected model revision metadata when available.
- Exact llama.cpp build/commit identity.
- Windows architecture compatibility.

Never assume that a similarly named GGUF or newer llama.cpp binary is
equivalent.

### 10.3 Offline setup

If artifacts are missing:

1. Show required download and disk/memory information.
2. Require an explicit **Download and set up** action.
3. Download to a temporary `.partial` path with resumable progress where the
   source permits it.
4. Pin the Hugging Face repository revision and exact filename.
5. Download the exact approved Windows llama.cpp build from its recorded source.
6. Calculate SHA-256 locally.
7. Reject and remove/quarantine a mismatching download.
8. Atomically publish verified artifacts.
9. Start llama.cpp on loopback only and wait for `/health`.
10. Report load time and resident memory estimate.

If the current Windows CPU architecture cannot run the exact evaluated binary,
offline mode is disabled with an explicit compatibility message. The first
release does not silently select a different build, model, quantization, GPU
backend, or thread configuration.

### 10.4 Resident runtime lifecycle

- Do not load Qwen at application startup unless offline mode was recently used
  or the user explicitly selects **Load offline model**.
- Load it on the first offline request and show model-load progress.
- Keep it resident for subsequent messages.
- Show `Loaded`, `Loading`, `Queued`, `Generating`, `Stopped`, or `Error`.
- Provide a settings action to unload it and recover RAM when no request is
  active.
- Shut it down cleanly with the FastAPI process.

The UI shows a hardware note and approximate wait based on recorded research
latency until enough local observations exist. It should present this as an
estimate, not a countdown guarantee.

## 11. Persistence and storage layout

Use SQLite for metadata and the filesystem for PDFs, corpora, matrices, and
logs. Keep runtime application data outside frozen `data/`, `config/`, and
`reports/` research artifacts.

Suggested layout:

```text
app_data/
  app.db
  books/
    <book_uuid>/
      source.pdf
      manifest.json
      pages.jsonl
      chapter_map.json
      chunks.jsonl
      specialists/
        formula.jsonl
        table.jsonl
        visual.jsonl
      indexes/
        chunks.npz
        formula.npz
        table.npz
        visual.npz
      processing_report.json
  jobs/
    <job_uuid>/
      upload.partial
      staging/
  models/
    embeddings/
    generation/
    llama.cpp/
  logs/
    app/
    llama/
```

`app_data/` must be Git-ignored. Paths stored in SQLite should be relative to
the application-data root where possible, allowing the project directory to be
moved as a unit.

### 11.1 Core records

**Book**

- UUID and generated stable `book_id`.
- SHA-256 content identity.
- Original filename and inferred title.
- Status and status reason.
- Page/chapter/searchable-page counts.
- Source and artifact paths.
- Ingestion-policy and uploaded-runtime-profile versions.
- Created, indexed, last-opened, and deleted timestamps.

**Ingestion job**

- UUID, checksum, book UUID when assigned.
- Current stage, stage progress, overall progress.
- State, error code, safe user message, internal detail.
- Started, updated, and completed timestamps.

**Chat**

- UUID, immutable book UUID, generated/display title.
- Default backend.
- Created, updated, and deleted timestamps.

**User message**

- UUID, chat UUID, exact submitted question, created timestamp.
- No normalized conversational rewrite.

**Retrieval snapshot**

- UUID, message UUID, book/artifact/profile fingerprints.
- Original and processed query.
- Activated signals, top-five evidence, assembled context.
- Component diagnostics and timing.
- Full snapshot checksum.

**Answer attempt**

- UUID, message UUID, retrieval snapshot UUID, backend.
- State and final structured output.
- Provider/runtime identity, token usage, timing, and validation result.
- Cancellation/error metadata.
- Created and completed timestamps.

Storing attempts separately is essential for comparing online and offline
answers without overwriting either result.

## 12. Backend architecture

The FastAPI backend owns all filesystem access, PDF processing, model access,
retrieval, generation, persistence, and deletion. React never accesses local
book files directly.

Recommended backend services:

- **Application lifecycle service:** startup checks, shutdown, browser launch,
  and component health.
- **Library service:** book records, duplicate lookup, detail, and deletion.
- **Ingestion coordinator:** durable single-worker job queue and progress.
- **Textbook validator:** PDF, text-layer, English, textbook-type, page-map, and
  chapter gates.
- **Artifact builder:** page records, chunks, specialists, embeddings, and
  manifests.
- **Retrieval runtime registry:** lazily loads and caches one per-book runtime;
  evicts idle runtimes when memory pressure requires it.
- **Prompt service:** converts a retrieval snapshot to the locked P1 prompt.
- **Online generator:** pinned Responses API adapter with streaming and no
  retries.
- **Offline runtime manager:** installation, checksum verification, resident
  llama.cpp process, queue, streaming, and cancellation.
- **Answer validator:** frozen JSON and citation validation.
- **Chat service:** transcripts, independent messages, attempts, and
  regeneration.
- **Diagnostics service:** redacted operational data for the developer panel.

Heavy extraction and embedding work must not run on the async HTTP event loop.
Use a dedicated local worker/process boundary so progress and cancellation APIs
remain responsive. The first release deliberately serializes ingestion jobs
and offline generations; online generation can run independently, but a single
message may have only one active attempt at a time.

### 12.1 Adapting the existing source modules

Do not duplicate the researched algorithms in the web layer. Extract reusable
interfaces from the current modules:

- A dynamic `BookSpec`/manifest adapter rather than adding uploads to the frozen
  `SPECS` tuple.
- Page extraction accepting a source path and generated book manifest.
- Corpus builders accepting already loaded page records rather than assuming
  repository-wide `data/processed` paths.
- A per-book `RetrievalBaselineDerivedRuntime` accepting chunk/specialist
  corpora and index paths while reading all fixed parameters from v1.
- A prompt input type for ordinary runtime questions, separate from benchmark
  rows, with the fixed `medium` answer-depth adaptation.
- Streaming provider interfaces sharing the same final normalized generation
  object.

The existing frozen `retrieve(question, book_id, ...)` entry point must continue
to work unchanged for research reproduction.

## 13. API surface

The exact schemas can evolve during implementation, but responsibilities should
remain stable.

### 13.1 System and provider APIs

- `GET /api/system/status` — app, storage, retrieval model, online provider, and
  offline runtime readiness.
- `POST /api/system/offline/setup` — begin explicit pinned download/setup.
- `GET /api/system/offline/setup/events` — setup progress SSE.
- `POST /api/system/offline/load` — load the verified local model.
- `POST /api/system/offline/unload` — release it when idle.
- `GET /api/system/diagnostics` — redacted developer diagnostics.

### 13.2 Library and ingestion APIs

- `GET /api/books` — list persistent library books and current states.
- `POST /api/books/upload` — stream one PDF and create/resolve an ingestion job.
- `GET /api/ingestion/{job_id}` — durable job snapshot.
- `GET /api/ingestion/{job_id}/events` — progress SSE.
- `GET /api/books/{book_id}` — book detail and processing summary.
- `GET /api/books/{book_id}/source` — local PDF stream for explicit viewing.
- `DELETE /api/books/{book_id}` — confirmed cascade deletion.

### 13.3 Chat APIs

- `GET /api/books/{book_id}/chats` — list that book's chats.
- `POST /api/books/{book_id}/chats` — create a chat fixed to the book.
- `GET /api/chats/{chat_id}` — transcript with attempts and compact source
  metadata.
- `PATCH /api/chats/{chat_id}` — rename or change default backend only.
- `DELETE /api/chats/{chat_id}` — delete the transcript and diagnostics.
- `POST /api/chats/{chat_id}/messages` — persist a question and start retrieval.
- `GET /api/attempts/{attempt_id}/events` — retrieval/generation SSE.
- `POST /api/attempts/{attempt_id}/cancel` — cancel active work.
- `POST /api/messages/{message_id}/regenerate` — create opposite-backend attempt
  from the same retrieval snapshot.
- `GET /api/attempts/{attempt_id}/sources` — full evidence excerpts on demand.
- `GET /api/attempts/{attempt_id}/diagnostics` — developer-only local detail.

The server derives `book_id` from the chat for message operations. It must not
accept a caller-supplied alternate book ID in the question payload.

## 14. Frontend state and UX details

### 14.1 Server state

Library, jobs, chats, messages, attempts, and provider readiness are server
state. React queries them and invalidates/refetches after mutations. SSE events
update active jobs and attempts, while reconnect logic falls back to a normal
GET snapshot so refreshing never loses state.

### 14.2 Local UI state

Keep only presentation concerns locally:

- Open/closed source panels.
- Draft question text.
- Current per-message backend override.
- Selected answer attempt tab.
- Whether online disclosure was acknowledged for this browser session.
- Developer diagnostics panel visibility.

Do not treat local state as the authority for job completion, provider
readiness, or persisted messages.

### 14.3 Backend toggle behavior

The toggle uses human-readable labels:

- `Online · GPT-4o` with a cloud icon and privacy disclosure.
- `Offline · Qwen3-8B` with a device icon and readiness/wait estimate.

Disabled states explain themselves:

- Online: `.env API key missing` or `OpenAI SDK unavailable`.
- Offline: `Setup required`, `Model downloading`, `Model incompatible`, or
  `Model failed to load`.

Changing the global toggle while an answer is running affects only the next
message. It never migrates or cancels the active attempt.

### 14.4 Error language

Errors should identify the failed stage and next valid action without exposing
stack traces in the normal UI. Examples:

- “This PDF appears to be scanned. OCR is not supported.”
- “A reliable chapter and printed-page map could not be detected.”
- “This file does not appear to be an English instructional textbook.”
- “The local model file failed checksum verification and was not installed.”
- “The online request failed. No retry was made.”
- “The model returned citations that did not match the supplied evidence, so
  the answer was not published.”

Full exception type, internal stage, timestamps, and safe identifiers remain in
the diagnostics panel and local logs.

## 15. Developer diagnostics panel

The diagnostics panel is available from the header but visually separate from
the student-facing answer. It supports debugging the local application without
turning normal chat into an experiment dashboard.

### 15.1 Per-book diagnostics

- PDF and artifact checksums.
- Ingestion-policy and runtime-profile versions.
- Page extraction distributions and rejection/acceptance signals.
- Printed-page mapping method and confidence.
- Chapter detection sources and confidence.
- Searchable/excluded pages with reasons.
- Chunk and specialist corpus counts.
- Embedding revision, dimensions, cache hit/miss, and build duration.

### 15.2 Per-question diagnostics

- Exact submitted and processed query.
- Selected book and artifact fingerprint.
- Activated specialist signals.
- Top-five evidence and complete provenance.
- Dense, BM25, specialist, and fused ranks/scores.
- Retrieval and context-assembly latency.
- Prompt checksum; prompt text may be shown locally behind an explicit reveal.
- Backend, resolved model/runtime, queue time, first-token time, total latency,
  and token usage.
- Structured-output and citation-validation result.
- Cancellation or error detail.

### 15.3 Redaction

Never show or log the OpenAI API key. Normal logs should avoid full PDF text,
prompts, and answers. Evidence and prompt text may be inspected through the
local developer panel because this is a single-user local tool, but must be
loaded on explicit request rather than included in every diagnostics response.

## 16. Deletion behavior

### 16.1 Delete chat

Deleting a chat removes its messages, retrieval snapshots, answer attempts, and
chat-specific diagnostics. It does not affect the book or shared indexes. The
UI asks for confirmation and identifies the chat title and book.

### 16.2 Delete book

Deleting a book is a confirmed cascade operation:

1. Prevent new chats and questions for the book.
2. Cancel or wait for its active ingestion/retrieval work.
3. Unload its retrieval runtime from memory.
4. Delete all chats, messages, snapshots, and attempts scoped to it.
5. Delete the source PDF and all derived artifacts.
6. Delete the database book record or retain only a non-content tombstone long
   enough to complete crash-safe cleanup.

Shared BGE and generation model files are not deleted with a book. Deletion
targets must be resolved and verified inside the configured `app_data/books`
directory before recursive removal.

If deletion is interrupted, the book remains `Deleting` and cleanup resumes on
the next startup. It must not reappear as ready with missing artifacts.

## 17. One-command local launch

Provide a root-level source-checkout command such as:

```powershell
python scripts/run_textbook_chat.py
```

The launcher should:

1. Resolve the repository root and Python environment.
2. Validate required Python and frontend build dependencies.
3. Create/upgrade the local SQLite schema.
4. Load `.env` without printing secrets.
5. Start FastAPI on `127.0.0.1` only.
6. Serve the compiled React application from FastAPI so a second production
   process is unnecessary.
7. Select a free configured local port or fail with a clear message.
8. Open the default browser after the health endpoint is ready.
9. Keep the console available for developer lifecycle messages.
10. On Ctrl+C, stop active jobs safely, terminate llama.cpp, close the database,
    and exit.

React's development server may still be used during frontend development, but
the normal user path remains one command and one localhost origin.

## 18. Known limitations deliberately visible in the product

- Uploaded books use a baseline-derived retrieval runtime; they do not inherit
  the benchmark validation of the two research books.
- Only English textbooks with extractable text are accepted.
- OCR and scanned books are unsupported.
- There is no manual correction path for incorrectly detected page or chapter
  structure; ambiguous books are rejected.
- The exact frozen synonym vocabulary is science-oriented. No book-specific
  vocabulary is created in the first release.
- Figures are represented through extracted captions and nearby text, not
  computer vision.
- Tables lose some spatial structure, and equations can lose formatting or
  symbols during PDF text extraction.
- Every question is independent; conversational follow-ups are not understood
  from transcript history.
- Offline generation is CPU-only, serialized, hardware-dependent, and may be
  substantially slower than online generation.
- Online mode sends the question and retrieved excerpts to OpenAI.
- No automatic online retry or provider fallback occurs.
- The application is local and single-user, not a network-hosted multi-user
  service.

## 19. Future book-specific vocabulary stage

The architecture reserves a vocabulary artifact per book, but the first
release leaves it absent and uses only the frozen v1 synonym rules.

A future researched stage may:

1. Extract glossary terms, index terms, chapter titles, section headings,
   definitions, abbreviations, and recurring aliases from the accepted book.
2. Propose trigger-to-addition rules scoped to that book only.
3. Deduplicate and normalize them deterministically.
4. Store source page provenance for every proposed relation.
5. Validate that expansion improves retrieval on a book-specific reviewed
   query set without harming negative questions.
6. Freeze an approved vocabulary profile with its own semantic version and
   checksum.
7. Load it only for the matching book checksum/profile.

It must not be generated online during upload, inferred from chat history, or
activated silently. Until that research and review exist, the UI and runtime
must report `Book-specific vocabulary: not available` rather than presenting
an unvalidated expansion as part of the baseline.

## 20. Canonical complete flows

### 20.1 First launch to first offline answer

1. User runs the one-command launcher.
2. Browser opens to system readiness and then the empty library.
3. Offline mode shows `Setup required`.
4. User starts setup; exact llama.cpp and Qwen artifacts download and verify.
5. User drops an English textbook PDF.
6. Upload is hashed and found to be new.
7. Integrity, text, language, textbook type, page mapping, and chapter gates
   pass.
8. Page/chapter records, fixed chunks, specialist corpora, BGE indexes, and
   BM25 structures are built on CPU.
9. Artifacts pass verification and the library book becomes `Ready`.
10. User creates a chat scoped to that book.
11. Global backend is set to offline.
12. User asks a self-contained question.
13. The top-five retrieval snapshot is created and persisted.
14. Qwen loads if not already resident; the UI shows load progress.
15. P1 generation streams the answer through the local server.
16. The final JSON and citations validate.
17. The answer, citations, backend badge, and collapsed **View sources** are
    committed to the transcript.

### 20.2 Online answer and offline regeneration

1. User selects online for one message.
2. The composer displays the data-sharing disclosure and obtains session
   acknowledgement.
3. The question is retrieved only within the chat's book.
4. The retrieval snapshot is persisted.
5. GPT-4o receives the question and retrieved compact evidence.
6. The answer streams, validates, and is committed.
7. User selects **Regenerate offline**.
8. The exact same retrieval snapshot and prompt content are sent to Qwen with
   its frozen 384-token ceiling.
9. The second attempt is stored beside the first and can be selected for direct
   comparison.

### 20.3 Rejected upload

1. User drops a PDF.
2. The file parses, but most instructional pages have images and negligible
   extractable text.
3. Validation stops before chunking or model loading.
4. The UI reports that the PDF appears scanned and OCR is unsupported.
5. The processing report stores non-sensitive gate metrics.
6. User removes the failed upload; temporary content is deleted.

### 20.4 Insufficient evidence

1. User asks a self-contained question about the selected book.
2. Retrieval still returns the deterministic top five.
3. The model determines that the evidence cannot support the requested answer.
4. A valid `insufficient_evidence` object is returned.
5. The UI presents the abstention and any missing-information list.
6. **View sources** remains available; the application does not supplement the
   response with outside knowledge.

### 20.5 Online provider failure

1. User explicitly sends an online question.
2. Retrieval completes and its snapshot is safely stored.
3. The OpenAI request fails or disconnects.
4. No SDK retry and no automatic provider switch occurs.
5. The attempt displays “The online request failed. No retry was made.”
6. The application preserves the transcript and diagnostics. It does not show
   an unsolicited offline fallback prompt.

## 21. Final architecture summary

```text
React localhost UI
  -> FastAPI application
       -> SQLite library/chat/job metadata
       -> app_data filesystem artifacts
       -> uploaded-textbook validation and ingestion worker (CPU)
            -> pypdf page extraction
            -> automatic page/chapter map
            -> frozen 600/100 chunking
            -> formula/table/visual specialist corpora
            -> pinned BGE-small dense indexes + BM25
       -> book-scoped retrieval runtime
            -> dense + BM25 + activated specialists
            -> RRF top five
            -> overlap-aware context assembly
            -> immutable retrieval snapshot
       -> locked P1 grounded prompt
            -> online: gpt-4o-2024-08-06, 768 tokens
            -> offline: Qwen3-8B Q4_K_M, 384 tokens
       -> structured-output and citation validation
       -> streamed, persisted answer with expandable sources
```

This design turns the finalized research into a usable local product without
rewriting the approved algorithms or overstating what was validated. New-book
ingestion is explicit, versioned, conservative, and inspectable; retrieval stays
book-scoped; generation stays locked to the approved online and offline
profiles; and every displayed grounded answer remains traceable to the exact
evidence snapshot that produced it.
