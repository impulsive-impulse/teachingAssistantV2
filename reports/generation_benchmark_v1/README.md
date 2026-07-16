# Generation Benchmark v1

Generation Benchmark v1 is the approved 40-question, textbook-grounded answer-generation benchmark for:

- Telangana SCERT Class 10 Biology: 20 questions, exactly two from each of 10 chapters.
- Telangana SCERT Class 10 Physical Sciences: 20 questions, with all 12 chapters represented.

The canonical artifact is [`data/benchmarks/generation_benchmark_v1.jsonl`](../../data/benchmarks/generation_benchmark_v1.jsonl). Its row contract is [`data/benchmarks/schemas/generation_benchmark_v1.schema.json`](../../data/benchmarks/schemas/generation_benchmark_v1.schema.json).

## Approval and authority

The 40-question proposal was approved in the Codex task before the final JSONL was created. Manabadi supplied candidate question wording and provenance only. The original SCERT PDFs are authoritative for accepted evidence and answer rubrics:

- `books/X Biology EM 2025-26.pdf`
- `books/X Physics EM 2025-26.pdf`

Website answer passages are not stored in the final benchmark. Each row instead contains independently checkable required points, optional points, unsupported claims, accepted printed/PDF pages, and page-level evidence references.

## Controlled website extraction

The extraction started from the two user-supplied public seed pages. Their visible chapter navigation yielded an allow-list of 10 Biology and 12 Physical Sciences pages. No authentication, CAPTCHA, unrelated crawling, or guessed URL enumeration was used.

Reproduce the approval-stage extraction with:

```powershell
temp\python-x64\python.exe -m pip install --target `
  reports\generation_benchmark_v1_review\_deps requests lxml pymupdf pillow

temp\python-x64\python.exe `
  reports\generation_benchmark_v1_review\extract_manabadi_candidates.py

temp\python-x64\python.exe `
  reports\generation_benchmark_v1_review\rank_textbook_evidence.py

temp\python-x64\python.exe `
  reports\generation_benchmark_v1_review\render_verification_pages.py
```

The script requests only the 22 reviewed URLs embedded in its allow-list. It preserves original wording, question number, preliminary type, source URL, resolved URL, and website answer material in the temporary review pool. The current review extraction contains 3,204 question blocks; screening removed trivial, incomplete, unsupported, duplicate, and near-duplicate candidates.

## Textbook verification

Candidate evidence was first located in the committed processed page artifacts, then checked independently against the original PDFs. Verification used both the PDF text layer and rendered pages when formulas, signs, charges, tables, diagrams, circuits, ray paths, or experiment layouts mattered.

Relevant review artifacts are:

- [`source_and_textbook_verification.md`](../generation_benchmark_v1_review/source_and_textbook_verification.md)
- [`ranked_textbook_evidence.md`](../generation_benchmark_v1_review/ranked_textbook_evidence.md)
- [`rendered_pdf_checks/`](../generation_benchmark_v1_review/rendered_pdf_checks/)
- [`proposal_summary.md`](../generation_benchmark_v1_review/proposal_summary.md)

Rendered inspection found that later Physical Sciences processed-page metadata drifts by five printed pages. For example, original PDF page 274 is printed textbook page 259 in Chapter 11, while the processed row labels it textbook page 264. The final benchmark records the printed page labels read from the original PDF, not a constant offset.

## Website-answer corrections

Across the final 40 rows, the website-answer statuses are:

- supported: 28;
- partially supported: 5;
- formatting corrupted: 6;
- contradicted: 1.

The contradicted answer is `GEN-PSC-002`: Manabadi reports image distance as `+6.7 cm`, while the textbook mirror formula and sign convention give `v = -20/3 cm ≈ -6.67 cm`. Other corrections include the hydrogen pop test, artery/vein wording, lens-maker minus signs and subscripts, ionic charges, the myopia formula, and Ohm's-law notation.

## Deterministic build and validation

Rebuild the final JSONL from the approved proposal:

```powershell
temp\python-x64\python.exe scripts\build_generation_benchmark_v1.py
```

Validate the canonical file directly:

```powershell
temp\python-x64\python.exe -m textbook_audit.generation_benchmark
```

Run the focused tests:

```powershell
temp\python-x64\python.exe -m pytest -q tests\test_generation_benchmark_v1.py
```

The validation contract checks schema fields, canonical JSONL serialization, exact 40/20/20 counts, chapter distribution, unique IDs, source provenance, evidence/page presence, answer-rubric completeness, near-duplicates, formula metadata, and the immutable retrieval assets.

## Retrieval immutability

Generation Benchmark v1 is independent of the frozen retrieval benchmark. The following existing SHA-256 values remain enforced in tests:

- `data/benchmarks/retrieval_benchmark_v1.jsonl`: `d333768b9c645cf0048a38356bfea69aa4a9e7220010e2cdf6340b91af38c046`
- `config/retrieval_baseline_v1.yaml`: `736fb9325794caead4439316b6ca546bd782cd7029b4f9f7788f545c5b43baa6`

The baseline manifest verifier also checks every source PDF, processed corpus, index, configuration, and retrieval benchmark recorded by Retrieval Baseline v1.
