# Retrieval Benchmark v1 candidate notes

> **Candidate benchmark only:** these rows are not final ground truth. A subject-matter reviewer must check questions, spans, page ranges, dependencies, and unanswerable labels before retrieval scoring.

## Generation and evidence policy

The benchmark is generated from anchored windows in the committed page-level JSONL. Answerable rows use only checked textbook records. PDF pages are derived using the project mappings: Biology `textbook + 9`; Physical Sciences `textbook + 10`. Empty-gold rows are intentional negative/weak-evidence candidates.

## Distribution

| Question type | Count |
|---|---:|
| `chemistry_concept` | 3 |
| `compare_contrast` | 3 |
| `definition` | 4 |
| `definition_law` | 4 |
| `diagram_concept` | 4 |
| `formula_concept` | 4 |
| `function_role` | 4 |
| `multi_page_synthesis` | 2 |
| `not_answerable` | 2 |
| `numerical_setup` | 3 |
| `process_explanation` | 5 |
| `weak_evidence` | 2 |

Book distribution: 20 Biology and 20 Physical Sciences questions.

## Dependency slices

- `visual_dependency` (4): PSC-009, PSC-010, PSC-011, PSC-012
- `formula_dependency` (11): PSC-001, PSC-002, PSC-003, PSC-005, PSC-006, PSC-007, PSC-008, PSC-013, PSC-014, PSC-015, PSC-016
- `table_dependency` (2): BIO-013, BIO-016

## Manual-review priorities

- Low-confidence candidates: BIO-020, PSC-020.
- Review all visual rows against the PDF page image; text extraction cannot preserve ray, circuit, anatomy, or layout relationships.
- Review formula rows against the PDF because fractions, superscripts/subscripts, Ω, arrows, and signs can be flattened or degraded.
- Review table-dependent Biology rows for row/column alignment.
- Multi-page spans intentionally quote an anchored excerpt from the first listed evidence page; the remaining pages are corroborating context and are named in the checked-page field.

## Page-mapping issue

The required constant offsets validate for every benchmark row. However, later Physical Sciences page headers visible inside extracted text sometimes drift from the project-assigned textbook page number. Candidate v1 follows the established JSONL mapping and task-required `+10` rule. Manual review should decide whether future corpus versions need discontinuous printed-page labels.

## Automated validation

**Passed.** Both CSV and JSONL were parsed after writing. All required columns exist; there are exactly 40 unique questions split 20/20 by book; all non-empty gold page lists obey the configured offsets; and every non-empty answer span occurs on its listed gold page set.

## Recommended next step

Conduct manual review in two passes: first verify evidence/page labels and negative examples against the PDFs; then review pedagogical wording, dependency flags, and difficulty. Freeze a corrected `retrieval_benchmark_v1.csv/jsonl` only after reviewer sign-off, and begin retrieval scoring against that frozen version.
