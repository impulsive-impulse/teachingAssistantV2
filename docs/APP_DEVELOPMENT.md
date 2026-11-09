# Local Textbook Chat development guide

This guide describes the implementation that realizes `docs/UX_PLAN.md`. The
plan remains the product and scientific contract; this guide records concrete
package boundaries, commands, and implementation status.

## Architecture boundary

The application has two top-level components:

- `src/textbook_chat/` contains FastAPI, operational configuration, SQLite
  migrations, persistence repositories, and business services.
- `frontend/` contains the React and TypeScript client. It obtains all durable
  state from `/api`; it never reads PDFs, indexes, environment variables, or
  model files directly.

The existing `src/textbook_audit/` package and frozen files under `config/` and
`reports/` remain the research source of truth. Startup performs a lightweight
integrity check without importing Torch. Full model imports are reserved for
ingestion and retrieval workers, so an unavailable model runtime does not
prevent the library or diagnostics UI from opening.

Runtime content is written below Git-ignored `app_data/`. Tests supply an
isolated temporary data directory and never write into research artifact trees.

The assessment track adds an opt-in
[source-provenance contract](SOURCE_PROVENANCE.md) shared by PDFs and benchmark
sentences. Source-aware chunk/context helpers reject mixed or altered source
metadata and retain exact addresses through clipping and persistence. Legacy
book ingestion and generation still use their frozen contracts; collection
integration and claim-level citations are subsequent assessment tasks.

SQLite migration 4 adds immutable `source_documents`, `collections`, and
`collection_documents` without changing existing books, chats, messages, or
attempts. Collection membership changes use an expected fingerprint so a stale
query cannot silently broaden its source set. A library book referenced by a
collection cannot be deleted until that membership is removed.

`textbook_audit/collection_index.py` builds one collection-wide dense corpus,
not a concatenation of separately truncated single-book results. Its subset
views search only their explicit source IDs. Index and retrieval JSON
publication retain source maps plus corpus/profile/vector fingerprints and
verify them when reloaded. Collection HTTP/chat integration remains T09.

## Backend layout

```text
src/textbook_chat/
  app.py                 FastAPI factory, lifecycle, compiled-SPA hosting
  config.py              settings and frozen-config integrity gate
  database.py            forward-only SQLite migrations and transactions
  domain.py              lifecycle and backend enums
  repositories.py        metadata SQL
  schemas.py             public response and strict request contracts
  api/
    dependencies.py      request-scoped service composition
    routes/               system, library, ingestion, chat collections
  services/
    system.py             readiness checks without paid calls
    uploads.py            bounded streaming, hashing, duplicate staging
    ingestion.py          durable serialized worker and atomic publication
    model_setup.py        pinned BGE discovery/download/checksum workflow
    chat.py               question, retrieval, generation, SSE orchestration
  ingestion/
    policy.py             versioned uploaded-book acceptance thresholds
    validator.py          text, English, textbook, page-map, chapter gates
    artifacts.py          frozen chunk/specialist/index artifact adapter
  retrieval/
    runtime.py            uploaded-book Retrieval Baseline v1 adapter
    registry.py           lazy CPU encoder and per-book runtime cache
  generation/
    backends.py           CPU/OpenCL strategy, command flags, log validation
    prompt.py             exact P1 prompt and citation validator boundary
    offline.py            shared resident llama.cpp streaming provider
    online.py             pinned Responses API streaming provider
```

Important invariants already enforced are:

- A content checksum identifies one persistent book.
- A chat references one immutable book.
- Foreign-key cascades keep transcript ownership explicit.
- A message can have only one active answer attempt at a time.
- Upload paths are server-generated; browser filenames are metadata only.
- Model names and output limits come from the frozen baseline, not the UI or
  environment settings.
- Every new message creates one immutable retrieval snapshot; regeneration
  references that same row and never retrieves again.
- Transcript messages are displayed but are never supplied as model history.
- Online disclosure is enforced by the API as well as represented in the UI.
- Provider failure never triggers an automatic online/offline switch. The
  offline OpenCL strategy also fails closed unless its operational
  `allow_fallback` flag explicitly permits and records a CPU fallback.

## Offline execution strategies

`config/runtime.yaml` contains the typed operational gate:

```yaml
offline_generation:
  backend: cpu
  allow_fallback: false
```

`AppSettings.load()` validates it at API startup. The backend factory itself is
resolved later, when the resident offline server starts. This keeps frontend
assets and the shared generation provider independent of the execution
backend. Environment overrides are available as
`TEXTBOOK_CHAT_OFFLINE_BACKEND` and
`TEXTBOOK_CHAT_OFFLINE_ALLOW_FALLBACK`.

The CPU strategy preserves the evaluated b10046 command byte-for-byte. The
OpenCL strategy uses the verified native ARM64 b10107 Adreno runtime, requests
`--device GPUOpenCL --n-gpu-layers 99`, and then validates the current process
session log. Readiness alone is insufficient: the log must prove the OpenCL
DLL loaded, the Qualcomm Adreno X1-85 was selected, optimized Adreno kernels
were enabled, and all 37 Qwen3-8B layers were offloaded.

Both strategies receive the same model path and the same shared runtime
dimensions, request payload, prompt, retrieval context, generation settings,
stream parser, and answer validator. Backend-specific code is confined to
`generation/backends.py`, runtime artifact resolution, and setup extraction.

Runtime locations:

```text
app_data/models/generation/                 shared Qwen3-8B GGUF/cache
app_data/models/llama.cpp/bin/              frozen CPU b10046 runtime
app_data/models/llama.cpp/opencl_gpu/bin/   OpenCL Adreno b10107 runtime
app_data/logs/llama/                         append-only server sessions
```

`GET /api/system/diagnostics` includes the offline runtime diagnostic; the
focused `GET /api/system/offline/runtime` endpoint returns the same backend
state. An OpenCL initialization error is raised to the caller unless fallback
was explicitly enabled. When enabled, both the GPU failure and CPU decision
are written to the application log and the diagnostic status becomes
`ready_with_fallback`.

## Frontend layout

```text
frontend/src/
  App.tsx                         application shell and navigation
  lib/api.ts                     typed HTTP client
  features/library/              library cards and upload interaction
  features/chat/                 transcript, composer, SSE, sources, providers
  features/system/               readiness presentation
  styles.css                     responsive local-first visual system
```

TanStack Query owns server-state caching. Component state is limited to
presentation concerns such as search text and the open upload dialog. The
production build makes no external font or asset request, keeping the shell
usable without internet access.

## Development commands

On a conventional x64 Python where the research ML stack is supported, install
the application extra with:

```powershell
python -m pip install -e ".[app]"
```

Install the optional OpenAI SDK only on machines that will use online answers:

```powershell
python -m pip install -e ".[app,online-generation]"
```

Native ARM64 Python cannot install the required PyTorch dependency of Sentence
Transformers on the current machine. The launcher therefore tests the invoking
runtime and automatically selects the repository's existing x64 Python runtime
when it can import Sentence Transformers and Torch. If neither is compatible,
startup fails with an installation action instead of exposing a nonfunctional
chat surface.

Run the backend during development:

```powershell
python -m uvicorn textbook_chat.app:app --host 127.0.0.1 --port 8765
```

Or build as needed, validate the configured loopback port, wait for health,
open the browser, and own graceful Ctrl+C shutdown with one Windows command:

```powershell
python scripts/start_textbook_chat.py
```

Run the React development server in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Build the production frontend, after which FastAPI serves `frontend/dist`:

```powershell
cd frontend
npm run build
cd ..
python -m uvicorn textbook_chat.app:app --host 127.0.0.1 --port 8765
```

## Verification

```powershell
python -m pytest tests/test_textbook_chat_*.py -q
cd frontend
npm run typecheck
npm run build
npm audit --audit-level=high
```

The app-focused suite covers database migrations, upload and validation gates,
artifact checksums, model setup, retrieval ranking/scoping, frozen generation
settings, citation validation, independent message persistence, byte-identical
regeneration prompts, and coordinator terminal states without making paid calls.
The complete suite is expected to pass under the selected x64 runtime. A real
Biology upload also passed validation, dense indexing, manifest
publication, and a five-result retrieval smoke query on the Windows ARM host.

## Current implementation status

Implemented:

- Configuration and frozen-profile integrity checks.
- Initial SQLite schema for books, ingestion jobs, chats, messages, retrieval
  snapshots, and answer attempts.
- System readiness, library listing/detail, upload, ingestion snapshot, and
  chat collection API foundations.
- Streamed upload staging, SHA-256 content identity, initial PDF signature
  check, and active-duplicate reuse.
- Durable single-worker ingestion with restart recovery, SQLite progress, and
  reconnectable server-sent progress events.
- Conservative integrity, text-layer, English, textbook-type, printed-page,
  and chapter validation gates with stable rejection codes.
- Dynamic page records, exact fixed 600/100 chunks, frozen formula/table/visual
  specialist representations, exercised BM25 structures, manifest hashing,
  and dense-index construction through the pinned BGE model interface.
- Atomic verified book publication; when the model runtime is absent, accepted
  work remains safely staged in `waiting_for_embedding_model` instead of being
  marked ready.
- Responsive compiled React library, readiness, processing-card, and upload
  surfaces with durable progress rendered through SSE plus polling fallback.
- Explicit pinned BGE setup with standard-cache reuse, revision-specific
  download, full directory identity verification, and waiting-job resumption.
- Uploaded-book dense/BM25/specialist retrieval with exact v1 query processing,
  RRF top five, overlap-aware assembly, manifest verification, and immutable
  snapshot checksums.
- Locked P1 prompt construction through the accepted research renderer and
  exact five-field/citation-page output validation.
- Pinned `gpt-4o-2024-08-06` streaming with 768 tokens, temperature zero,
  strict structured output, zero SDK retries, and decoded answer deltas.
- Durable independent messages and answer attempts, cancellation-safe state
  transitions, restart handling, same-snapshot regeneration, sources API, and
  reconnectable attempt events.
- Responsive book-scoped chat UI with persistent transcript, chat/per-message
  backend selection, online disclosure, stop state, regeneration, and lazy
  expandable evidence excerpts.
- Exact shared Qwen revision/GGUF SHA plus official llama.cpp b10046 CPU and
  b10107 OpenCL-Adreno Windows ARM64 archive setup, safe extraction,
  build/commit verification, and extracted runtime manifest hashing.
- Resident loopback-only llama.cpp lifecycle with CPU/OpenCL strategies,
  complete Adreno layer-offload validation, explicit opt-in fallback,
  serialized streaming, cancellation, unload, and process shutdown.
- Redacted system/per-attempt diagnostics, source-PDF viewing, confirmed
  chat/book deletion with runtime eviction and owned-path checks.
- Windows launcher with frontend build, dependency/port checks, health polling,
  browser opening, and Ctrl+C process cleanup.

Still required by `docs/UX_PLAN.md`:

- A clean-machine bootstrap/distribution path for installing the compatible x64
  Python ML runtime when the repository-local runtime is absent.
- A real multi-gigabyte Qwen/llama.cpp setup and offline answer smoke run; the
  installer and provider are covered without incurring that download yet.
- An explicit paid online answer smoke run; API request construction is covered
  with an injected client and no paid verification call has been made.

This list is deliberately explicit: a staged upload is not yet an indexed book,
and the current foundations must not be described as a complete RAG app.
# Assessment collections (additive v1)

Open **Collections** in the existing app. Upload PDFs in Library, wait for
ready status, acknowledge local indexing permission, and import each as a
source. Select both sources and create a collection. Existing book chats and
their online/offline controls are unchanged.

Collection questions are independent, with durable history. They share the
assessment selector, 1,024-token context renderer and quoted claim validator.
The offline backend reuses the resident frozen Qwen runtime. Book chats keep
their 384-token contract; collection requests explicitly allow up to 768.
PDF collections use a separate `collection-local-extractive-v1` profile: a
query-ranked shortlist of literal source clauses is displayed to the model,
which selects IDs and a short synthesis. The adapter constructs exact claims
and citations, retaining both native selections and adapted output in diagnostics.
Deictic clauses retain their preceding sentence; activities/questions are not
offered as answers. Abstention and one-source answers remain possible. Source
selection and citation validity do not prove semantic completeness.

The assessment benchmark keeps its frozen online GPT-4o generator, prompt and
768-token ceiling. Local extractive PDF demonstrations are **not** benchmark
arms or evidence that unrestricted local paraphrasing has been solved.
Online PDF collections use `collection-online-extractive-v1`: the model selects
IDs from the same literal-clause shortlist, and the adapter constructs claims
and exact citations. This avoids invented sentence IDs and changed quotation
punctuation without relaxing validation. Native selections, source options,
adapted output and actual prompt/schema checksum remain in diagnostics.
The prepared PDF request shares the original ledger, provider, pricing and
fingerprint helpers; its explicit contingency dispatch leaves the frozen
benchmark dispatcher's original prompt/schema and code identity untouched.

Online collection queries require explicit permission to transmit excerpts,
use the original shared 500-attempt ledger, and consume only its 80-call
contingency allocation. Local indexing permission alone does **not** authorize
external PDF transmission. No automatic backend fallback or paid retry exists.

```powershell
.\.venv-assessment\Scripts\python.exe scripts\ingest_assessment.py --demo --authorized-demo-use
.\.venv-assessment\Scripts\python.exe scripts\ask_collection.py
.\.venv-assessment\Scripts\python.exe scripts\ask_collection.py --collection <id> --backend offline --question "<question>"
# Only when permission covers transmitting retrieved textbook excerpts:
.\.venv-assessment\Scripts\python.exe scripts\validate_assessment_demo.py --backend online --authorize-online-transmission
# Recheck retained answers and their separate source-support review; zero calls:
.\.venv-assessment\Scripts\python.exe scripts\validate_assessment_demo.py --backend online --check
```

HTTP: `GET /api/sources`, `POST /api/sources/from-book/{book_id}`,
`GET/POST /api/collections`, and
`GET/POST /api/collections/{id}/queries`. Question requests contain `question`,
`backend`, and `online_disclosure_acknowledged` (false by default).
`GET /api/collection-queries/{id}/diagnostics` retains raw response, source
snapshot, context, validation and safe failure metadata. Failed/invalid output
is never rendered as a grounded answer. Active queries close explicitly as
failed after a process restart rather than silently resuming paid work.
Public history projects answer/usage metadata in SQLite instead of loading raw
source snapshots into Python. The UI polls only during active queries; full
snapshots and prior failed attempts remain available through diagnostics.
The demo CLI's `--reuse-query <id>` can explicitly retain a prior successful
answer after rechecking its question, backend, collection and source claims.
It is marked as reuse and does not count the original attempt as a new call.
`--replay-query <id>` or `POST /api/collection-queries/{id}/replay` reapplies the
PDF adapter to retained native output without retrieval or provider dispatch.
It creates a separately labeled result and leaves the original failure intact.
Adapter v2 extracts only an unambiguous leading Yes/No when explicitly requested
by the question; numeric/entity answers and quotations are not repaired.

Citations show exact quotations and original code-point ranges. PDF links open
`GET /api/sources/{document_id}/file#page=<physical-page>` after original-byte
verification. Sentence sources open original indexed units via
`GET /api/sources/{document_id}/units/{unit_id}`. Source copies are independent
of library rows so deleting a library entry does not destroy collection history.
Quoted address/lexical validation is not proof of semantic entailment.
