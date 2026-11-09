# Marginalia — Local Textbook RAG

Marginalia is a Windows-local chat application for asking grounded questions
about uploaded English textbooks. A user adds a digitally generated PDF, waits
for validation and indexing, and starts independent book chats or selects a
collection to ask across documents. The additive assessment context layer is
evaluated separately on an open multi-document benchmark.

The application is built on the project's frozen research decisions:

| Layer | Frozen profile |
|---|---|
| Retrieval | Retrieval Baseline v1, including the researched formula, table, visual, and caption specialist signals |
| Online generation | `gpt-4o-2024-08-06`, retrieved top-5 context, 768-token limit |
| Offline generation | Qwen3-8B Q4_K_M through llama.cpp, retrieved top-5 context, 384-token limit |

The completed Local Model Comparison v1 tested Gemma 3 12B, gpt-oss-20b,
Phi-4 14B, and Granite 3.3 8B without changing those frozen profiles. None
passed the successive-narrowing gates, so Qwen3-8B remains the approved local
model. See `reports/local_model_comparison_v1/README.md`.

A subsequent isolated Qwen3.6-27B Q4_K_M investigation confirmed native ARM64
CPU and full Adreno OpenCL offload, but stopped at validity because latency and
memory were substantially worse than the Qwen3-8B control. See
`reports/local_model_comparison_v2_qwen36_27b/README.md`.

The first release is single-user, CPU-first, and bound to `127.0.0.1`. On the
validated Windows ARM64 hardware it can optionally run offline generation on
the Qualcomm Adreno GPU through OpenCL. It accepts English, text-layer textbook
PDFs that pass suitability checks; scans, papers, novels, reports, corrupt
PDFs, and poor extractions are rejected.

## Top-level flow

1. Upload a textbook PDF.
2. Validate its integrity, text layer, language, textbook structure, page map,
   and chapters.
3. Extract pages and specialist representations, build the frozen retrieval
   indexes, and publish the book atomically to the persistent library.
4. Create or select a chat that is permanently scoped to that book.
5. Ask a self-contained question and choose the online or offline generator.
6. Retrieve and assemble book evidence, generate a citation-constrained answer,
   and persist the message, answer attempt, diagnostics, and expandable sources.

Previous messages remain visible, but every question is retrieved and generated
independently. The application never uses the transcript as model history.

## Implementation overview

- **Backend:** FastAPI, Pydantic contracts, SQLite persistence, background
  ingestion/model-setup workers, and server-sent events for live progress.
- **Frontend:** React, TypeScript, Vite, TanStack Query, and a responsive
  persistent library/chat interface.
- **Retrieval:** uploaded-book adaptation of Retrieval Baseline v1 with pinned
  embeddings, BM25/dense fusion, specialist signals, reranking, and top-five
  context assembly.
- **Generation:** explicit per-chat and per-message provider selection. Online
  use requires disclosure acknowledgement; failures never trigger an automatic
  retry or provider switch.
- **Local runtime:** exact Qwen and Windows ARM64 llama.cpp artifacts are
  downloaded, checksum-verified, and reused. Runtime content lives under the
  Git-ignored `app_data/` directory. CPU remains the default and recommended
  production backend; `opencl_gpu` is an optional execution-only feature gate.

## Screenshots and demo

| Textbook library | Textbook upload |
|---|---|
| ![Persistent textbook library](docs/assets/screenshots/textbook-library.png) | ![Textbook PDF upload dialog](docs/assets/screenshots/textbook-upload.png) |

| Online/offline comparison | Offline textbook chat |
|---|---|
| ![Online and offline answers to the same question](docs/assets/screenshots/online-offline-comparison.png) | ![Persistent offline textbook conversation](docs/assets/screenshots/offline-chat.png) |

[Watch the end-to-end retrieval and generation demo](docs/assets/demo/e2e-retrieval-generation.mp4)

## Repository structure

```text
config/                 Frozen retrieval and generation profiles
data/                   Reviewed benchmarks and reproducible research data
docs/                   UX plan, development guide, and repository guide
frontend/               React/TypeScript web client
reports/                Experiment results and baseline decision records
scripts/                App launcher and reproducible research entry points
src/textbook_chat/       FastAPI application and production RAG runtime
src/textbook_audit/      Extraction, retrieval, and generation research code
tests/                   Unit, integration, persistence, and regression tests
app_data/                Local books, indexes, models, SQLite DB, and logs (ignored)
```

### Main application files

| File | Purpose |
|---|---|
| `scripts/start_textbook_chat.py` | Windows launcher: builds the UI, checks dependencies and port, starts FastAPI, and opens the browser |
| `src/textbook_chat/app.py` | FastAPI factory, lifecycle, API registration, and compiled frontend hosting |
| `src/textbook_chat/services/ingestion.py` | Durable PDF validation, processing, indexing, and publication workflow |
| `src/textbook_chat/retrieval/runtime.py` | Book-scoped Retrieval Baseline v1 execution |
| `src/textbook_chat/services/chat.py` | Independent question, retrieval, generation, and streaming orchestration |
| `src/textbook_chat/generation/` | Frozen online/offline providers, prompt construction, and validation |
| `frontend/src/App.tsx` | Application shell, system readiness, diagnostics, and settings |
| `frontend/src/features/chat/ChatPage.tsx` | Chat list, renaming, provider controls, transcript, composer, and sources |

For deeper details, see [the UX plan](docs/UX_PLAN.md),
[application development guide](docs/APP_DEVELOPMENT.md), and
[repository guide](docs/REPOSITORY_GUIDE.md).

## Assessment context layer

Start with [DESIGN.md](DESIGN.md) for architecture and tradeoffs,
[EVAL.md](EVAL.md) for all measured results/failures, and
[SUBMISSION_PLAN.md](SUBMISSION_PLAN.md) for task/readiness boundaries.
The new layer provides collection-scoped source retrieval, document-aware
evidence allocation, exact token packing, claim quotations and source navigation.
It preserves the historical single-book profiles.

On the frozen 45-question HotpotQA distractor cohort, complete-document context
recall is **97.78% proposed / 88.89% dense / 80.00% hybrid**. The primary paired
coverage gain is positive. Answer F1 is 64.20% / 61.06% / 51.02%; the gain over
dense is uncertain and proposed invalid output is 26.67%. A genuine fresh
clean-clone rerun is retained separately. These are small-subset results, not
leaderboard scores or proof of semantic reliability.

**Demo boundary:** two real PDF questions have source-reviewed answers through
the authorized online path, one generated and one explicitly labeled zero-call
adapter replay. Local Qwen remains unreliable; two fresh successes under the
final PDF adapter are not established. Valid addresses alone are not completion.
Private reviewer access, rights review and the walkthrough remain separate
handoff work; no blanket submission-ready claim is made.

### Reproducible assessment setup

Use Windows x64 CPython **3.12** installed outside the checkout (tested 3.12.10),
a short checkout/environment path (at most 60 characters), Git and Node/npm.
Native Windows ARM64 is additionally required for the currently pinned local
Qwen/llama.cpp demo; the open benchmark does not need that offline runtime.

```powershell
git -c core.longpaths=true clone --config core.longpaths=true https://github.com/impulsive-impulse/teachingAssistantV2.git C:\src\teachingAssistantV2
Set-Location C:\src\teachingAssistantV2
& "C:\Python312\python.exe" scripts\setup_assessment.py --frontend
.\.venv-assessment\Scripts\python.exe scripts\ingest_assessment.py
.\.venv-assessment\Scripts\python.exe scripts\ingest_assessment.py --check
```

Replace the Python path with your separately installed x64 interpreter. The
hash-locked setup prepares exact public benchmark/BGE/tokenizer/scorer inputs,
uses no `temp` runtime/private cache, and makes no paid call. The original LFS
recording is optional, not an evaluation input. See
[requirements/README.md](requirements/README.md) for exact revisions/hashes,
restricted-network caches, edition checks and environment troubleshooting.

### Collections: authorized sources, API and CLI

Only with permission covering local indexing/demonstration of the exact
2025-26 editions:

```powershell
.\.venv-assessment\Scripts\python.exe scripts\prepare_assessment_assets.py `
  --demo-books-dir "D:\AuthorizedTextbooks" --authorized-demo-use
.\.venv-assessment\Scripts\python.exe scripts\ingest_assessment.py --demo --authorized-demo-use
.\.venv-assessment\Scripts\python.exe scripts\start_textbook_chat.py --skip-build
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765), then **Collections**.
Alternatively upload PDFs in Library, wait for ready status, acknowledge local
indexing permission and import them as sources. Create a collection containing
both sources. Citations expose the quotation, original character ranges and
verified physical PDF page. Each PDF remains one document.

For offline use, first complete the in-app verified Qwen/llama.cpp **Set up**.
It downloads multi-gigabyte model artifacts and is not included in benchmark
setup. Online requests require an explicit transmission acknowledgment and use
only shared contingency allowance; local indexing permission is not enough.

```powershell
.\.venv-assessment\Scripts\python.exe scripts\ask_collection.py
.\.venv-assessment\Scripts\python.exe scripts\ask_collection.py `
  --collection <id> --backend offline --question "<question>"
.\.venv-assessment\Scripts\python.exe scripts\validate_assessment_demo.py
.\.venv-assessment\Scripts\python.exe scripts\validate_assessment_demo.py --check
# Only with separate permission to transmit retrieved excerpts to OpenAI:
.\.venv-assessment\Scripts\python.exe scripts\validate_assessment_demo.py `
  --backend online --authorize-online-transmission
.\.venv-assessment\Scripts\python.exe scripts\validate_assessment_demo.py --backend online --check
```

The demo command uses the two source-reviewed questions in
`config\assessment_demo_v1.json`. It retains failed/insufficient outputs and
does not equate two source IDs with semantic success. `--check` requires a
separate local source-review record bound to the actual answers. Book/UI
no-thinking defaults and benchmark execution remain unchanged.
`--reuse-query <id>` explicitly retains a verified successful answer.
`--replay-query <id>` reapplies the PDF adapter to saved native output without
retrieval or a provider call; the new result is labeled cached replay and the
original failure is preserved. An unambiguous Yes/No prefix is extracted only
when the question explicitly requests yes/no; quotations and answer polarity
are never invented. A replay is not fresh inference.

HTTP examples, against a running local server:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/sources
$collection = Invoke-RestMethod http://127.0.0.1:8765/api/collections `
  -Method Post -ContentType "application/json" `
  -Body '{"title":"My collection","document_ids":["<source-id-1>","<source-id-2>"]}'
Invoke-RestMethod "http://127.0.0.1:8765/api/collections/$($collection.id)/queries" `
  -Method Post -ContentType "application/json" `
  -Body '{"question":"<question>","backend":"offline","online_disclosure_acknowledged":false}'
```

`GET /api/collections/{id}/queries` returns public history;
`GET /api/collection-queries/{id}/diagnostics` retains raw/source snapshots.
`GET /api/sources/{document_id}/file#page=<physical-page>` verifies PDF bytes;
`GET /api/sources/{document_id}/units/{unit_id}` resolves original source units.
Failed/invalid output is explicit, never a grounded-answer fallback.

### Fresh inference versus zero-call replay

Committed results can be rebuilt without an API key, dataset download,
embedding model or retrieval call. The prepared public tokenizer and Python
dependencies are still needed:

```powershell
.\.venv-assessment\Scripts\python.exe scripts\evaluate_assessment.py --cached --output reports\assessment_results_v1\final
.\.venv-assessment\Scripts\python.exe scripts\evaluate_assessment.py --cached --output reports\assessment_results_v1\fresh_final
```

For **explicitly paid** new inference, put `OPENAI_API_KEY` only in local `.env`
or the process environment; never in command arguments or committed files.
After setup, this command verifies/acquires inputs, builds/reuses the public
index, executes all four arms, retains every raw row and rebuilds metrics:

```powershell
.\.venv-assessment\Scripts\python.exe scripts\evaluate_assessment.py --fresh `
  --phase final_evaluation --output app_data\assessment\runs\new-final
```

An existing owned run directory resumes that same run; a new one generates
fresh outputs. A second checkout is **not** a new 500-call approval. A separately
authorized rerun must use `--phase fresh_final_rerun` and `--ledger` pointing to
the original shared ledger. The already completed rerun need not be repeated.
Current measured total: 376 attempted calls and $1.7556450 token-based estimate,
not an invoice. The conservative 500-call cap estimate is $14.08; missing usage
would be unknown, not zero. Generation means were roughly 2-3 seconds online,
excluding startup/indexing; default local PDF runs took 136-166 seconds and
did not answer successfully. The six specifically authorized PDF calls used
$0.0437425; that approval is exhausted, and the later adapter replay was free.
Hardware/network and warm-state effects matter.

Historical single-book results remain separate. Their explicit text-only
[checksum compatibility profile](docs/HISTORICAL_ARTIFACT_IDENTITIES.md) leaves
binary hashes and original manifests unchanged. PDF redistribution remains
unauthorized, and future external transmission requires explicit per-run
permission; obtain permitted local copies rather than bundling or re-uploading
them.

## Build and run

Requirements:

- Windows 10 or 11; the frozen offline runtime currently targets Windows ARM64
- x64 Python 3.10 or newer with a compatible PyTorch runtime
- Node.js and npm

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[app,online-generation]"

Copy-Item .env.example .env
# Add OPENAI_API_KEY to .env only if online generation will be used.

cd frontend
npm ci
npm run build
cd ..

python scripts/start_textbook_chat.py
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). The launcher opens this
address automatically. Use the in-app **Set up** action to download and verify
the frozen offline model/runtime when required.

## Offline CPU and OpenCL GPU backends

The operational setting is resolved only when the resident offline
`llama-server` starts. It changes the executable/backend arguments, not the
frozen pipeline: both paths use the same `Qwen3-8B-Q4_K_M.gguf`, retrieval,
top-five context, P1 prompt, seed, temperature, 384-token limit, and answer
validator.

The checked-in default is:

```yaml
offline_generation:
  backend: cpu
  allow_fallback: false
```

Edit `config/runtime.yaml`, or override it for one process:

```powershell
# Recommended/default CPU path
$env:TEXTBOOK_CHAT_OFFLINE_BACKEND = "cpu"
$env:TEXTBOOK_CHAT_OFFLINE_ALLOW_FALLBACK = "false"
python scripts/start_textbook_chat.py

# Validated Qualcomm Adreno OpenCL path
$env:TEXTBOOK_CHAT_OFFLINE_BACKEND = "opencl_gpu"
$env:TEXTBOOK_CHAT_OFFLINE_ALLOW_FALLBACK = "false"
python scripts/start_textbook_chat.py
```

Use the in-app offline setup after switching backends. The model is shared and
is not duplicated. CPU runtime files remain under
`app_data/models/llama.cpp/bin`; OpenCL runtime files are stored separately
under `app_data/models/llama.cpp/opencl_gpu/bin`. The OpenCL package is the
official native Windows ARM64 llama.cpp b10107 Adreno build and must contain
`llama-server.exe` and `ggml-opencl.dll`; setup verifies the release archive
checksum, executable build/commit, and every extracted file.

Inspect `GET /api/system/diagnostics` or `GET /api/system/offline/runtime` after
loading. The offline diagnostic reports:

- requested and active backend;
- llama.cpp build;
- selected device;
- offloaded and expected layer counts;
- initialization status and whether fallback occurred.

On `opencl_gpu`, startup succeeds only if the current llama.cpp log names
`Qualcomm(R) Adreno(TM) X1-85 GPU`, enables the Adreno kernels, and reports
`37/37` Qwen3-8B layers offloaded. Missing DLLs, an unsupported device,
incomplete offload, or startup failure produces an actionable error. It never
silently falls back. If `allow_fallback: true` is deliberately configured, the
GPU error and CPU fallback decision are both logged and exposed in diagnostics.

The validated hardware is Windows 11 ARM64 on Snapdragon X Elite X1E80100 with
Adreno X1-85. Qwen3-8B generated valid output with complete GPU offload, but
measured generation performance was currently similar to CPU (9.72 versus
9.53 tokens/s in the controlled proof). CPU therefore remains recommended.

Troubleshooting and rollback:

1. Confirm the OpenCL runtime setup completed and `ggml-opencl.dll` is present.
2. Load the provider, then inspect `/api/system/offline/runtime` for the exact
   initialization error and `logs/llama/llama_server.stderr.log` for device and
   offload lines.
3. Keep fallback disabled while diagnosing so a GPU failure cannot be hidden.
4. Roll back immediately by setting `backend: cpu` in `config/runtime.yaml` or
   `TEXTBOOK_CHAT_OFFLINE_BACKEND=cpu`, restart the API, and run offline setup
   only if the verified CPU runtime is absent. No frontend rebuild is needed.

For frontend development, run the API and Vite server in separate terminals:

```powershell
# Terminal 1
$env:PYTHONPATH = "src"
python -m uvicorn textbook_chat.app:app --host 127.0.0.1 --port 8765

# Terminal 2
cd frontend
npm run dev
```

Run the application checks with:

```powershell
python -m pytest -q
cd frontend
npm run typecheck
npm run build
```

## Workflow

```mermaid
flowchart TD
    A["Upload textbook PDF"] --> B["Validate PDF and textbook suitability"]
    B -->|Rejected| C["Show a stable rejection reason"]
    B -->|Accepted| D["Extract pages, structure, and specialist signals"]
    D --> E["Build and verify book-specific retrieval artifacts"]
    E --> F["Publish book to the persistent library"]
    F --> G["Select book and create or rename a chat"]
    G --> H["Ask an independent, self-contained question"]
    H --> I["Run book-scoped Retrieval Baseline v1"]
    I --> J["Assemble the top-five evidence context"]
    J --> K{"Selected provider"}
    K -->|Online| L["GPT-4o with disclosure acknowledgement"]
    K -->|Offline| M["Local Qwen through llama.cpp"]
    L --> N["Validate grounded structured output"]
    M --> N
    N --> O["Display answer and expandable sources"]
```
