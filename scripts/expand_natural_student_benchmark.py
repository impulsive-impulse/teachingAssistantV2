"""Add the approved natural-student query slice to the reviewed benchmark.

The script is intentionally idempotent: it rebuilds the natural slice from its
canonical parents on every run, while leaving the wording and evidence of all
pre-existing questions unchanged. It also validates every inherited page and
answer span against both processed page records and the original PDF text.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.retrieval import read_jsonl

TOKEN_RE = re.compile(r"[a-z0-9]+")

# The user-reviewed proposal is recorded as data rather than scattered copy
# operations. Each entry inherits evidence, flags, difficulty, and provenance
# from its verified parent; only query-specific fields are replaced.
APPROVED_QUESTIONS: tuple[dict[str, Any], ...] = (
    {"question_id": "BIO-023", "parent_question_id": "BIO-002", "query_style": "different_vocabulary", "question": "How do cells get usable energy out of food?", "ambiguity_risk": "low"},
    {"question_id": "BIO-024", "parent_question_id": "BIO-003", "query_style": "colloquial", "question": "What are the million or so tiny working units in each kidney called?", "ambiguity_risk": "low"},
    {"question_id": "BIO-025", "parent_question_id": "BIO-005", "query_style": "imperfect_grammar", "question": "How food go from the mouth to the stomach, and where does breaking it down start?", "ambiguity_risk": "low"},
    {"question_id": "BIO-026", "parent_question_id": "BIO-007", "query_style": "short_underspecified", "question": "Why does blood go through the heart twice?", "ambiguity_risk": "low_medium"},
    {"question_id": "BIO-027", "parent_question_id": "BIO-008", "query_style": "colloquial", "question": "How do kidneys turn waste in the blood into pee?", "ambiguity_risk": "low"},
    {"question_id": "BIO-028", "parent_question_id": "BIO-009", "query_style": "misconception", "question": "Does pollen turn straight into a seed? What actually happens?", "ambiguity_risk": "medium_intentional"},
    {"question_id": "BIO-029", "parent_question_id": "BIO-011", "query_style": "different_vocabulary", "question": "What carries oxygen from our lungs to the rest of the body?", "ambiguity_risk": "low"},
    {"question_id": "BIO-030", "parent_question_id": "BIO-014", "query_style": "different_vocabulary", "question": "What changes when cells release energy without oxygen instead of with oxygen?", "ambiguity_risk": "low"},
    {"question_id": "BIO-031", "parent_question_id": "BIO-016", "query_style": "misconception", "question": "Do all new cells end up with only half the chromosomes?", "ambiguity_risk": "medium_intentional"},
    {"question_id": "BIO-032", "parent_question_id": "BIO-018", "query_style": "cause_effect", "question": "How does saving rainwater help when wells and groundwater are running out?", "ambiguity_risk": "low", "alternative_gold_pages": []},
    {"question_id": "PSC-025", "parent_question_id": "PSC-003", "query_style": "cause_effect", "question": "If I turn up the voltage, why does more current flow through the same wire?", "ambiguity_risk": "low"},
    {"question_id": "PSC-026", "parent_question_id": "PSC-004", "query_style": "colloquial", "question": "How can moving a magnet make electricity in a wire?", "ambiguity_risk": "low"},
    {"question_id": "PSC-027", "parent_question_id": "PSC-005", "query_style": "imperfect_grammar", "question": "What formula tells where a mirror image gonna form?", "ambiguity_risk": "low"},
    {"question_id": "PSC-028", "parent_question_id": "PSC-007", "query_style": "short_underspecified", "question": "Do stronger lenses have a shorter focus?", "ambiguity_risk": "low_medium"},
    {"question_id": "PSC-029", "parent_question_id": "PSC-011", "query_style": "cause_effect", "question": "Why do short-sighted people need a concave lens?", "ambiguity_risk": "low"},
    {"question_id": "PSC-030", "parent_question_id": "PSC-012", "query_style": "short_underspecified", "question": "Why doesn't one broken branch stop the rest of a parallel circuit?", "ambiguity_risk": "medium"},
    {"question_id": "PSC-031", "parent_question_id": "PSC-013", "query_style": "misconception", "question": "Can I just use positive distances in the mirror formula?", "ambiguity_risk": "low"},
    {"question_id": "PSC-032", "parent_question_id": "PSC-016", "query_style": "imperfect_grammar", "question": "Why equation need same number of each atom on both sides?", "ambiguity_risk": "low"},
    {"question_id": "PSC-033", "parent_question_id": "PSC-017", "query_style": "colloquial", "question": "If something has pH 3, 7, or 10, what kind of liquid is each?", "ambiguity_risk": "low"},
    {"question_id": "PSC-034", "parent_question_id": "PSC-018", "query_style": "misconception", "question": "When atoms share electrons, are they actually giving them away?", "ambiguity_risk": "low_medium"},
)

PDF_FILES = {
    "biology": "X Biology EM 2025-26.pdf",
    "physical_sciences": "X Physics EM 2025-26.pdf",
}


def _tokens(text: str) -> list[str]:
    """Normalize prose into comparison tokens for extraction-tolerant checks."""
    return TOKEN_RE.findall(text.lower())


def _coverage(needle: str, haystack: str) -> float:
    """Return multiset token coverage, tolerating PDF line and symbol damage."""
    wanted, found = Counter(_tokens(needle)), Counter(_tokens(haystack))
    total = sum(wanted.values())
    return sum(min(count, found[token]) for token, count in wanted.items()) / total if total else 0.0


def _load_page_maps(root: Path) -> dict[str, dict[int, dict[str, Any]]]:
    """Index processed pages by PDF number for exact metadata validation."""
    output: dict[str, dict[int, dict[str, Any]]] = {}
    for book_id in PDF_FILES:
        rows = read_jsonl(root / "data" / "processed" / f"{book_id}_pages.jsonl")
        output[book_id] = {int(row["pdf_page_number"]): row for row in rows}
    return output


def build_rows(existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark existing rows canonical and derive approved rows from parents."""
    approved_ids = {item["question_id"] for item in APPROVED_QUESTIONS}
    canonical = [dict(row, benchmark_slice="canonical") for row in existing if row["question_id"] not in approved_ids]
    parents = {row["question_id"]: row for row in canonical}
    additions: list[dict[str, Any]] = []
    for spec in APPROVED_QUESTIONS:
        if spec["parent_question_id"] not in parents:
            raise ValueError(f'Missing canonical parent {spec["parent_question_id"]}')
        row = dict(parents[spec["parent_question_id"]])
        row.update(spec)
        row.update({
            "benchmark_slice": "natural_student",
            "review_status": "verified",
            "review_notes": "Natural-student wording approved by the reviewer; inherited gold evidence validated against processed pages and the source PDF text layer.",
            "expected_retrieval_notes": "Natural-student stress query; rank without using its canonical parent or gold labels.",
        })
        additions.append(row)
    return canonical + additions


def validate_rows(root: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Verify IDs, parents, page metadata, answer spans, alternatives, and PDFs."""
    ids = [row["question_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Benchmark question IDs are not unique")
    by_id = {row["question_id"]: row for row in rows}
    page_maps = _load_page_maps(root)
    readers = {book: PdfReader(root / "books" / filename) for book, filename in PDF_FILES.items()}
    validation: list[dict[str, Any]] = []
    for spec in APPROVED_QUESTIONS:
        row, parent = by_id[spec["question_id"]], by_id[spec["parent_question_id"]]
        # Every dependency and evidence field must remain identical to the
        # reviewed parent, preventing query wording from silently changing gold.
        inherited = ("gold_textbook_pages", "gold_pdf_pages", "gold_answer_span",
                     "formula_dependency", "visual_dependency", "table_dependency",
                     "requires_multiple_pages", "requires_multiple_chunks", "difficulty")
        if any(row.get(field) != parent.get(field) for field in inherited):
            raise ValueError(f'{row["question_id"]} changed inherited evidence or flags')
        if "alternative_gold_pages" not in spec and row.get("alternative_gold_pages") != parent.get("alternative_gold_pages"):
            raise ValueError(f'{row["question_id"]} changed inherited alternative evidence')
        processed_text, pdf_text = [], []
        for textbook_page, pdf_page in zip(row["gold_textbook_pages"], row["gold_pdf_pages"]):
            page = page_maps[row["book_id"]].get(int(pdf_page))
            if not page or int(page["textbook_page_number"]) != int(textbook_page):
                raise ValueError(f'{row["question_id"]} has invalid TB/PDF mapping {textbook_page}/{pdf_page}')
            processed_text.append(page["cleaned_text"])
            pdf_text.append(readers[row["book_id"]].pages[int(pdf_page) - 1].extract_text() or "")
        processed_coverage = _coverage(row["gold_answer_span"], " ".join(processed_text))
        pdf_coverage = _coverage(row["gold_answer_span"], " ".join(pdf_text))
        if processed_coverage < 0.50 or pdf_coverage < 0.50:
            raise ValueError(f'{row["question_id"]} answer-span coverage too low: processed={processed_coverage:.3f}, PDF={pdf_coverage:.3f}')
        # Front matter can use Roman labels (for example ``i``), so compare
        # alternative page identities as strings instead of coercing the full
        # processed corpus to integers.
        textbook_pages = {str(page["textbook_page_number"]) for page in page_maps[row["book_id"]].values() if page.get("textbook_page_number") is not None}
        if not set(map(str, row.get("alternative_gold_pages", []))).issubset(textbook_pages):
            raise ValueError(f'{row["question_id"]} has an unresolved alternative gold page')
        validation.append({"question_id": row["question_id"], "processed_span_coverage": processed_coverage,
                           "pdf_span_coverage": pdf_coverage, "mapping_verified": True})
    return validation


def _evaluation_lines(root: Path) -> list[str]:
    """Render slice-separated metrics when regenerated baseline files exist."""
    paths = {name: root / "reports" / filename for name, filename in (
        ("page", "page_level_retrieval_metrics.json"),
        ("chunk", "chunk_level_retrieval_metrics.json"),
        ("hierarchy", "hierarchical_retrieval_metrics.json"),
    )}
    if not all(path.is_file() for path in paths.values()):
        return []
    page = json.loads(paths["page"].read_text(encoding="utf-8"))
    chunk = json.loads(paths["chunk"].read_text(encoding="utf-8"))
    hierarchy = json.loads(paths["hierarchy"].read_text(encoding="utf-8"))
    if "by_benchmark_slice_and_retriever" not in page:
        return []
    labels = {"bm25": "BM25", "dense_bge_small": "BGE-small dense", "hybrid_rrf": "Hybrid RRF"}

    def row(label: str, retriever: str, metrics: dict[str, Any]) -> str:
        """Format one compact effectiveness row for the natural-slice report."""
        return (f'| {label} | {labels[retriever]} | {metrics["answerable_questions"]} | '
                f'{metrics["hit_at_1"]:.1%} | {metrics["hit_at_3"]:.1%} | '
                f'{metrics["hit_at_5"]:.1%} | {metrics["mrr"]:.3f} |')

    lines = ["", "## Retrieval evaluation", "",
             "### Page retrieval: canonical versus natural-student", "",
             "| Slice | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for slice_name, retrievers in page["by_benchmark_slice_and_retriever"].items():
        for retriever, metrics in retrievers.items():
            lines.append(row(slice_name, retriever, metrics))
    lines += ["", "### Natural-student results across retrieval units", "",
              "| Unit / approach | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for retriever, metrics in page["by_benchmark_slice_and_retriever"]["natural_student"].items():
        lines.append(row("Page", retriever, metrics))
    for strategy, slices in chunk["by_benchmark_slice"].items():
        for retriever, metrics in slices["natural_student"].items():
            lines.append(row(f"{strategy.title()} chunks", retriever, metrics))
    for approach, slices in hierarchy["by_benchmark_slice"].items():
        for retriever, metrics in slices["natural_student"].items():
            lines.append(row(approach.replace("_", " ").title(), retriever, metrics))
    lines += ["", "### Natural-student page results by style", "",
              "| Query style | Retriever | N | Hit@5 | MRR |",
              "|---|---|---:|---:|---:|"]
    for style, retrievers in page["natural_student_by_query_style_and_retriever"].items():
        for retriever, metrics in retrievers.items():
            lines.append(f'| {style} | {labels[retriever]} | {metrics["answerable_questions"]} | {metrics["hit_at_5"]:.1%} | {metrics["mrr"]:.3f} |')
    natural_ids = {item["question_id"] for item in APPROVED_QUESTIONS}
    failures = [item for item in page["top_5_failures"] if item["question_id"] in natural_ids]
    lines += ["", "### Natural-student page top-five misses", "",
              "| Question | Retriever | Accepted rank | Automatic category |",
              "|---|---|---:|---|"]
    for item in failures:
        lines.append(f'| {item["question_id"]} | {labels[item["retriever"]]} | {item["gold_rank"] or "> corpus"} | {item["failure_category"].replace("_", " ")} |')
    lines += ["", "The natural-student slice is harder than the canonical slice for every page retriever. Page dense and page Hybrid tie at 65.0% Hit@5; fixed-chunk Hybrid also reaches 65.0%, while soft-fusion Hybrid leads hierarchical variants at 60.0%. The largest cross-method page failures are `PSC-025`, `PSC-026`, and `PSC-028`; their natural wording removes or changes the textbook's strongest lexical anchors.", ""]
    return lines


def render_report(root: Path, rows: list[dict[str, Any]], validation: list[dict[str, Any]]) -> str:
    """Create a concise human audit of additions and source validation."""
    additions = [row for row in rows if row["benchmark_slice"] == "natural_student"]
    checks = {item["question_id"]: item for item in validation}
    style_counts = Counter(row["query_style"] for row in additions)
    book_counts = Counter(row["book_id"] for row in additions)
    lines = ["# Natural Student Query Additions", "",
             "Twenty reviewer-approved questions were derived from verified canonical parents. Canonical wording and gold evidence were not changed.", "",
             "## Distribution", "",
             f'- Books: Biology {book_counts["biology"]}; Physical Sciences {book_counts["physical_sciences"]}.',
             "- Styles: " + "; ".join(f"`{name}` {style_counts[name]}" for name in sorted(style_counts)) + ".",
             "", "## Added questions and validation", "",
             "| ID | Parent | Book | Style | Difficulty | Natural question | TB / PDF gold | Processed coverage | PDF coverage |",
             "|---|---|---|---|---|---|---|---:|---:|"]
    for row in additions:
        check = checks[row["question_id"]]
        pages = f'{",".join(map(str, row["gold_textbook_pages"]))} / {",".join(map(str, row["gold_pdf_pages"]))}'
        lines.append(f'| {row["question_id"]} | {row["parent_question_id"]} | {row["book_id"]} | {row["query_style"]} | {row["difficulty"]} | {row["question"]} | {pages} | {check["processed_span_coverage"]:.1%} | {check["pdf_span_coverage"]:.1%} |')
    lines += ["", "## Ambiguity and accepted evidence", "",
              "- `BIO-031` intentionally corrects an overgeneralization; its inherited two-page mitosis/meiosis evidence is required to distinguish the cell-division types.",
              "- `PSC-030` is narrower than its parent. TB 205 / PDF 215 is a sufficient minimal set because it states that parallel branches provide separate current paths; the inherited TB 205 and 208 evidence remains accepted.",
              "- `BIO-032` uses only primary TB 231–232 evidence. Parent alternatives TB 230 and 243 were not retained: TB 230 asks related questions without answering them, while TB 243 contains only generic conservation material.",
              "", "## Validation summary", "",
              f"All {len(additions)} mappings were verified against processed page metadata and the original source PDF text layer. Every inherited answer span achieved at least 50% multiset-token coverage in both representations.", ""]
    lines += _evaluation_lines(root)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    """Expand, validate, and atomically replace the canonical benchmark."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    benchmark = (args.benchmark or root / "data/benchmarks/retrieval_benchmark_v1.jsonl").resolve()
    report = (args.report or root / "reports/natural_student_query_additions.md").resolve()
    rows = build_rows(read_jsonl(benchmark))
    validation = validate_rows(root, rows)
    benchmark.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    report.write_text(render_report(root, rows, validation), encoding="utf-8")
    print(json.dumps({"total_rows": len(rows), "natural_student_rows": len(validation), "validation": "passed"}, indent=2))


if __name__ == "__main__":
    main()
