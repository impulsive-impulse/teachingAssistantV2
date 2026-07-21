# Marginalia — Local Textbook RAG

Marginalia is a Windows-local chat application for asking grounded questions
about uploaded English textbooks. A user adds a digitally generated PDF, waits
for validation and indexing, selects that book, and starts independent
book-scoped conversations.

The application is built on the project's frozen research decisions:

| Layer | Frozen profile |
|---|---|
| Retrieval | Retrieval Baseline v1, including the researched formula, table, visual, and caption specialist signals |
| Online generation | `gpt-4o-2024-08-06`, retrieved top-5 context, 768-token limit |
| Offline generation | Qwen3-8B Q4_K_M through llama.cpp, retrieved top-5 context, 384-token limit |

The first release is single-user, CPU-only, and bound to `127.0.0.1`. It
accepts English, text-layer textbook PDFs that pass suitability checks; scans,
papers, novels, reports, corrupt PDFs, and poor extractions are rejected.

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
  Git-ignored `app_data/` directory.

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
