# Assessment input and environment setup

This is the reproducible assessment profile, not a replacement for the
historical textbook research environments. It prepares inputs and exercises the
local encoder/token counter. It does **not** ingest a multi-document collection,
run answer generation, or establish evaluation gains.

## Prerequisites

- Windows 10/11 and a separately installed **x64 CPython 3.12**. The profile is
  tested with Python 3.12.10. On an ARM64 Windows host, the Python process must
  still be x64; the bootstrap checks `sysconfig.get_platform()`, not the host
  architecture. It never discovers or selects `temp\python-x64`.
- Node.js/npm when `--frontend` is requested. Node 24.15.0/npm 11.12.1 were used
  to prepare the frontend lock. All existing package versions are preserved.
- Git and, if the existing recording is wanted, Git LFS.
- HTTPS access to public package/model/data hosts, or explicit verified package
  caches as described below. Certificate verification must remain enabled.

Use a short checkout path and a per-clone Windows long-path setting. The
checkout and environment paths must each be at most 60 characters for this
profile. Git's setting does not enable long paths for Python; the pinned Torch
wheel includes long third-party license paths. The bootstrap rejects overly
long locations before installing anything. `--venv C:\ta-env` can place the
dedicated environment somewhere shorter without changing the checkout.

```powershell
git -c core.longpaths=true clone --config core.longpaths=true https://github.com/impulsive-impulse/teachingAssistantV2.git C:\src\teachingAssistantV2
Set-Location C:\src\teachingAssistantV2
```

The existing MP4 is stored with Git LFS. `git lfs pull` acquires that recording;
it is not an input to the assessment or a prerequisite for setup. A source-only
clone can use `GIT_LFS_SKIP_SMUDGE=1` for its clone process. Do not treat an LFS
pointer file as the recording itself.

## One-command setup

Run the script with the ordinary x64 Python installed outside this repository.
Replace this example executable path with that installation's path:

```powershell
& "C:\Python312\python.exe" scripts\setup_assessment.py --frontend
```

The command:

1. Creates a dedicated `.venv-assessment`, with no system site-packages. It
   refuses to modify an existing environment without its project/profile marker.
2. Installs the complete hash-pinned Windows/Python/CPU dependency lock. The
   Torch wheel is pinned to a public CPU artifact, not a CUDA build.
3. Installs this repository editable without re-resolving dependencies or using
   an isolated, unpinned build environment; then checks dependency compatibility.
4. Acquires and verifies every public assessment input listed below.
5. Loads the real encoder on CPU for two synthetic, non-benchmark strings and
   checks finite, normalized 384-dimensional output. It tests the real
   `o200k_base` encoder's round trip with network access denied.
6. Optionally installs the locked frontend and builds it. `--frontend` runs
   `npm ci`, so it replaces that checkout's `frontend\node_modules`.

The script does not alter global Python/npm settings, switch Git branches,
overwrite `.env`, select another generator, or make a paid model call. It
removes inherited Python/package configuration and model/API tokens from its
child processes. Public PyPI/npm are the default package sources.

An input receipt is written under `app_data\assessment\input_readiness.json`.
The environment's marker becomes `ready` only after all requested steps
succeed. Receipts are local diagnostics, not a substitute for re-verification.

## Exact inputs

`config\assessment_assets_v1.json` is the inventory. Source identities already
frozen in T01 or Retrieval Baseline v1 are referenced rather than replaced.

| Input | Acquisition and identity | Local destination |
|---|---|---|
| HotpotQA dev distractor mirror | Pinned Hugging Face commit, 27,452,575 bytes, exact SHA-256; recomputes the frozen 60-question selection | `data\retrieval\cache\assessment_protocol_v1\hotpotqa-validation.parquet` |
| BGE-small-en-v1.5 | Pinned commit, exactly 11 files/134,505,940 bytes; each file and the historical aggregate identity are verified | `app_data\models\embeddings\...` |
| `o200k_base` data | Explicit public data URL, size/SHA-256 and tiktoken's URL-derived cache key | `app_data\models\tokenizers` |
| Official HotpotQA scorer and license | Pinned upstream commit and separate size/SHA-256 checks | `data\retrieval\cache\assessment_protocol_v1\evaluator` |
| Authorized demo PDFs | Explicit local import, edition-specific size/SHA-256 and physical page counts | `books` |

The BGE inventory excludes the upstream duplicate pickle/ONNX weights and
`.gitattributes`. Downloading every upstream repository file does not reproduce
the frozen 11-file identity. The application **Set up** action shares this
curated downloader and still respects a custom application-data directory.

Known files are reused only after verification. Wrong hashes, extra model
files, missing files, and unsafe paths fail explicitly. Each new file is
verified in an owned temporary file and published without overwriting a
concurrent writer. Failed transfers remove only their own temporary file.
Completed verified files can be reused on a subsequent invocation; partial
individual files are not resumed.

## Demo PDFs and permissions

The Telangana textbooks' copyright notice, on physical PDF page 4, reserves
reproduction, storage in retrieval systems, and transmission to permission.
The project must have permission covering indexing and demonstration. That
does **not** automatically authorize distributing the original PDFs or their
derived text.

Do not bundle or re-upload these binaries. Obtain authorized local copies of
the **2025-26 edition** through the publisher's
[SCERT portal](https://scert.telangana.gov.in/) or an authorized source. An
updated edition is not an interchangeable input.

| File | Physical pages | SHA-256 |
|---|---:|---|
| `X Biology EM 2025-26.pdf` | 257 | `b88c63972c1eaf379ced00ff6d93fc953a594281535bcf86c51e184e170c6ba7` |
| `X Physics EM 2025-26.pdf` | 327 | `db9e53ca92f83f40498314c6bc6f9ae29d538f60464668d4aeb933bfd7af8f59` |

Supply both flags only when this use is authorized:

```powershell
& "C:\Python312\python.exe" scripts\setup_assessment.py --frontend `
  --demo-books-dir "D:\AuthorizedTextbooks" --authorized-demo-use
```

Without those flags the open-benchmark setup works independently, and the
receipt reports the demo scope as **not requested**, not ready. Missing or
different-edition PDFs produce an actionable error. Existing historical
derived-text artifacts and submission sharing still require a separate rights
review; this setup does not retroactively grant redistribution permission.

## Rechecking without acquisition

```powershell
.\.venv-assessment\Scripts\python.exe scripts\prepare_assessment_assets.py --check --smoke

# Include the already imported authorized demonstration corpus:
.\.venv-assessment\Scripts\python.exe scripts\prepare_assessment_assets.py `
  --check --smoke --demo-books-dir .\books --authorized-demo-use
```

`--check` does not download/copy input files or rewrite the input receipt.
`--smoke` uses the prepared local model/tokenizer, with network connections
denied. Neither command invokes the answer generator. Later context-layer
commands must set `TIKTOKEN_CACHE_DIR` to this prepared cache rather than rely
on the user's implicit tokenizer cache.

```powershell
$env:TIKTOKEN_CACHE_DIR = (Resolve-Path app_data\models\tokenizers).Path
```

## Shared source ingestion after setup

```powershell
# Verify/acquire the frozen benchmark inputs and build local CPU embeddings:
.\.venv-assessment\Scripts\python.exe scripts\ingest_assessment.py

# Verify an existing compiled corpus without downloads or index changes:
.\.venv-assessment\Scripts\python.exe scripts\ingest_assessment.py --check

# Only with the previously confirmed PDF indexing/demonstration permission:
.\.venv-assessment\Scripts\python.exe scripts\ingest_assessment.py `
  --demo --authorized-demo-use
```

The benchmark writes `app_data\assessment\inputs-v1\runtime` for inference and
`app_data\assessment\inputs-v1\evaluation` for reference answers/support labels.
The runtime loader never opens the evaluation directory. Each question retains
only its original ten context documents, and its projection is checked against
the frozen T01 fingerprint. The global 600-document vector cache is reused
through explicit per-question subset scopes, not searched as a full-corpus
benchmark.

PDF imports copy only authorized local inputs into owned ignored storage,
register immutable source records, and build a two-document collection. The
PDFs remain separate sources; unverified printed labels are omitted. Original
PDFs and their derived text must not be newly committed or redistributed
without separate permission. Ingestion makes no paid API call and does not
establish answer quality or evaluation gains.

Run the standard development-only retrieval references after ingestion:

```powershell
.\.venv-assessment\Scripts\python.exe scripts\evaluate_retrieval_baselines.py
```

The local JSON output retains all three methods' packed evidence, source maps,
and custom context coverage. It does not run the generator or use held-out
rows to choose settings. The official scorer is vendored with its original
Apache license and pinned byte identity, so report rebuilding will not depend
on an ignored downloaded scorer file.

## Restricted-network package installation

An explicitly chosen HTTPS mirror can be used with `--index-url`. The exact
dependency hashes remain mandatory; no trusted-host or TLS-disable setting is
accepted. Do not put credentials in command-line URLs or commit machine-specific
mirror configuration.

Alternatively, supply a new wheelhouse and npm cache containing the exact
verified artifacts:

```powershell
& "C:\Python312\python.exe" scripts\setup_assessment.py `
  --wheelhouse "D:\VerifiedPackages\python" `
  --frontend --npm-cache "D:\VerifiedPackages\npm" --npm-offline
```

The wheelhouse mode rewrites pinned direct wheel URLs to local files in a
temporary environment-owned requirements file while retaining their hashes.
It does not change the committed lock or silently fetch a missing CPU wheel.
The npm lock pins public registry URLs and SHA-512 integrity for every artifact.
An offline cache must contain the locked artifacts, including the optional
packages for the actual Node process architecture.

Public inputs still need acquisition on the first run. A fully disconnected
run requires their previously verified project-local copies and
`prepare_assessment_assets.py --check`; package-offline mode alone is not a
claim that the initial data/model acquisition is offline.

## Maintaining the dependency lock

`assessment_constraints.txt` holds the selected profile versions.
`assessment-windows-py312-cpu.lock` pins the full dependency/build closure and
allowed artifact hashes. Changing the profile requires re-resolving and
rechecking it; do not hand-edit hashes or substitute a new embedding revision.

Generate the lock with pip-tools 7.6.2 in a separate x64 Python 3.12 builder:

```powershell
pip-compile pyproject.toml --extra assessment --extra app --extra online-generation `
  --extra dev --all-build-deps --constraint requirements\assessment_constraints.txt `
  --generate-hashes --allow-unsafe --strip-extras --no-emit-index-url --no-emit-trusted-host `
  --output-file requirements\assessment-windows-py312-cpu.lock
```

No private index, user cache path, or API key belongs in the committed lock.
pip-tools calls build packages such as setuptools "unsafe" and normally omits
them; `--allow-unsafe` includes their exact versions and hashes. It does not
disable verification or TLS. They are necessary for the deliberately
non-isolated editable installation.
`ujson` 6.0.0 is the compatible scorer dependency selected for this profile;
using a newer release is not necessary to preserve the official scorer.

## Completed T02 verification

A fresh short-path Git clone was tested with an independent official x64
CPython 3.12.10 runtime. The clone initially contained no ignored Python
runtime, PDFs, model/data caches, virtual environment, or frontend packages.

| Check | Observed result |
|---|---|
| Python dependency/build closure | 69 pinned packages; PyPI artifacts verified against official release hashes, plus the pinned public CPU Torch wheel |
| Frontend lock | All 126 artifact versions unchanged; fresh tarballs checked against the original integrity values and SHA-512-pinned in the new lock |
| Benchmark acquisition | Exact pinned source downloaded; all 60 frozen selections reproduced |
| BGE acquisition | All 11 files downloaded afresh; historical aggregate identity reproduced |
| Local model/tokenizer | Actual CPU encoder returned finite normalized 384-dimensional vectors; actual `o200k_base` round trip passed with network connections denied |
| Authorized local PDF import | Both exact hashes and 257/327 physical page counts verified |
| Frontend | Installed from a newly populated offline cache; TypeScript/Vite build completed |
| Read-only recheck | All prepared inputs and offline smoke passed again; input receipt unchanged |
| Focused regression tests | 92 passed; one historical home-cache-dependent test skipped because that cache was absent |
| Paid model calls | Zero |

The dependency lock's SHA-256 is
`9f87064bddbf311f74b542305680243797a72261a07114c7d69d56e1287f1daf`.
The existing single-book behavior, frozen input identities, benchmark question
selection, and historical research artifacts were not replaced.

On this machine, fresh direct requests to the public Python artifact and npm
hosts failed during TLS handshakes. Verification therefore used newly acquired,
hash-checked package artifacts through reachable credential-free mirror
transport, then installed them into the clean clone. It did not reuse the old
private package/model caches or disable certificate checks. The default direct
public-host network route remains unverified on this restricted machine; the
explicit mirror/wheelhouse/cache options make that limitation visible.

An initial deep-path environment failed on Torch's third-party license paths.
The final short-path run succeeded without changing Windows settings; the
bootstrap now checks the measured path constraint up front. Neither this
record nor the setup claims multi-document retrieval or an evaluation gain.

## Licenses and remaining boundaries

HotpotQA's dataset is CC BY-SA 4.0; its scorer is Apache 2.0 and its license is
cached beside it. The pinned BGE model and tiktoken are MIT; the model's pinned
README and tiktoken license link are retained in the inventory. Preserve
attribution and the applicable terms when redistributing permitted inputs or
derived artifacts.

This setup does not fetch the optional Qwen/ARM64 llama.cpp provider or old
experimental indexes. Those have separate historical setup procedures. It also
does not silently repair historical CRLF-dependent checksum claims; their
documented versioned migration remains T15.
