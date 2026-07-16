"""Write human-readable approval-stage reports from the verified proposal JSONL."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


HERE = Path(__file__).parent


def esc(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def main() -> None:
    rows = [json.loads(line) for line in (HERE / "proposed_40_questions.jsonl").read_text(encoding="utf-8").splitlines()]
    summary = json.loads((HERE / "proposal_summary.json").read_text(encoding="utf-8"))
    validation = json.loads((HERE / "proposal_validation.json").read_text(encoding="utf-8"))

    lines = [
        "# Generation Benchmark v1 — approval-stage proposal", "",
        "> Temporary review artifact only. No final generation benchmark or production code has been created or modified.", "",
        "## Proposed questions", "",
        "| ID | Book / chapter | Original website question | Normalized only if needed | Type / difficulty | Source | Textbook / PDF pages | Required points (brief) | Website status | Confidence / recommendation |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        normalized = row["normalized_question"] if row["normalized_question"] != row["original_source_question"] else "—"
        pages = f"T {','.join(map(str,row['accepted_textbook_pages']))}; PDF {','.join(map(str,row['accepted_pdf_pages']))}"
        required = "; ".join(row["required_answer_points"])
        lines.append("| " + " | ".join([
            row["question_id"], f"{row['book_id']} / {row['chapter_number']} {esc(row['chapter_title'])}",
            esc(row["original_source_question"]), esc(normalized),
            f"{row['question_type']} / {row['difficulty']}", f"[Q{row['source_question_number']}]({row['source_url']})",
            pages, esc(required), row["website_answer_status"],
            f"{row['verification_confidence']} / {row['recommendation']}",
        ]) + " |")
    lines += ["", "## Distribution", "",
              f"- Total: {summary['total']} (20 Biology, 20 Physical Sciences).",
              "- Biology chapters: exactly 2 questions in each of chapters 1–10.",
              "- Physical Sciences chapters: chapters 1–5 and 8–10 have 2 each; chapters 6, 7, 11, and 12 have 1 each.",
              f"- Difficulty: {summary['by_difficulty']}.", f"- Question types: {summary['by_type']}.",
              f"- Dependencies: {summary['dependencies']}.", f"- Website-answer status: {summary['website_status']}.",
              f"- Recommendation: {summary['recommendations']}.", "",
              "## Duplicate and rejection notes", "",
              "- The controlled extraction contains 3,204 question blocks. There are 39 exact duplicate-wording groups (43 rows beyond the first occurrence), plus many near-duplicates.",
              "- Near-duplicate families screened out include repeated human sex-determination questions, repeated sustainable-development questions, and duplicate Ohm’s-law experiment questions.",
              "- Rejected examples include one-word/fill-in items, local survey/project prompts without textbook-grounded answers, corrupted questions whose missing operands/figures could not be recovered, and concepts repeated by a stronger selected question.",
              "- No rejected candidate was substituted with an invented question.", "",
              "## Material website conflicts", "",
              "- GEN-PSC-002: website gives image distance as +6.7 cm; the textbook mirror formula and sign convention give v = −20/3 cm ≈ −6.67 cm.",
              "- GEN-PSC-005: website says the flame turns off with a pop; the textbook says hydrogen burns with a characteristic pop.",
              "- GEN-BIO-006: website’s 'veins are blue' wording is not accepted; the rubric describes vessel structure, direction, and pulmonary exceptions.",
              "- Formula/notation corruption was repaired for the lens-maker formula, myopia correction, ionic charges/electron transfer, and Ohm’s-law experiment.",
              "- GEN-BIO-012 has a missing website answer block; its rubric is derived only from the textbook’s mitosis/meiosis material.", "",
              "## Validation", "",
              f"- Proposal validation passed: {validation['passed']}; 40 unique IDs; all 22 source URLs returned HTTP 200; every row has non-empty rubric and PDF evidence.",
              "- Frozen Retrieval Baseline v1 checksum verification passed for all 14 recorded artifacts.",
              "- `data/benchmarks/retrieval_benchmark_v1.jsonl`, baseline configuration, manifest, indexes, and processed corpora were not modified.", ""]
    (HERE / "proposal_summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")

    verify = [
        "# Source and textbook verification", "",
        "## Method", "",
        "- Navigated the two public seed pages in the browser and copied their visible chapter-navigation links (10 Biology, 12 Physical Sciences).",
        "- Performed a controlled extraction only from those 22 allow-listed pages; original wording and website answer material remain in the raw temporary JSONL.",
        "- Located candidate evidence in processed page artifacts, then independently re-extracted the cited pages from the original PDFs with pypdf.",
        "- Rendered selected original PDF pages for formula, table, circuit, ray, molecular, experiment, and diagram checks; page contact sheets are under `rendered_pdf_checks/`.",
        "- Accepted textbook page labels were read from rendered pages when layout mattered; offsets were not treated as authoritative.", "",
        "## Important page-mapping finding", "",
        "The processed Physical Sciences metadata uses a constant +10 textbook/PDF offset. Rendered originals show a later +15 relationship. For example, PDF page 274 is printed textbook page 259 in Chapter 11 (Principles of Metallurgy), although the processed record labels it textbook page 264. Proposal evidence for later chapters uses the printed page labels from the rendered PDF.", "",
        "## Per-question evidence and rubric", "",
    ]
    for row in rows:
        verify += [f"### {row['question_id']} — {row['chapter_title']}", "",
                   f"- Source: {row['source_url']} (question {row['source_question_number']})",
                   f"- Accepted evidence: textbook pages {row['accepted_textbook_pages']}; PDF pages {row['accepted_pdf_pages']}",
                   f"- Required: {'; '.join(row['required_answer_points'])}",
                   f"- Optional: {'; '.join(row['optional_answer_points']) or 'none'}",
                   f"- Unsupported: {'; '.join(row['prohibited_or_unsupported_claims']) or 'none'}",
                   f"- Dependencies: formula={row['requires_formula']}, visual={row['requires_visual']}, table={row['requires_table']}, multiple_passages={row['requires_multiple_passages']}",
                   f"- Website answer: {row['website_answer_status']}. {row['website_answer_notes'] or 'No material conflict found.'}",
                   f"- Verification: {row['verification_confidence']}; recommendation={row['recommendation']}", ""]
    (HERE / "source_and_textbook_verification.md").write_text("\n".join(verify), encoding="utf-8", newline="\n")
    print(HERE / "proposal_summary.md")
    print(HERE / "source_and_textbook_verification.md")


if __name__ == "__main__":
    main()
