"""Validate the temporary proposal without touching production benchmark assets."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import requests
from pypdf import PdfReader


HERE = Path(__file__).parent
ROOT = HERE.parents[1]


def main() -> None:
    rows = [json.loads(line) for line in (HERE / "proposed_40_questions.jsonl").read_text(encoding="utf-8").splitlines()]
    raw = [json.loads(line) for line in (HERE / "manabadi_raw_candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    raw_keys = {(row["book_id"], row["chapter_number"], row["source_url"], row["original_source_question"]) for row in raw}
    errors = []
    if len(rows) != 40:
        errors.append(f"expected 40 rows, found {len(rows)}")
    if Counter(row["book_id"] for row in rows) != Counter({"biology": 20, "physical_sciences": 20}):
        errors.append("book distribution is not 20/20")
    if len({row["question_id"] for row in rows}) != len(rows):
        errors.append("question IDs are not unique")
    for row in rows:
        key = (row["book_id"], row["chapter_number"], row["source_url"], row["original_source_question"])
        if key not in raw_keys:
            errors.append(f"{row['question_id']}: source wording/provenance missing from raw extraction")
        if not row["required_answer_points"]:
            errors.append(f"{row['question_id']}: empty required rubric")
        if not row["accepted_pdf_pages"] or not row["accepted_textbook_pages"]:
            errors.append(f"{row['question_id']}: missing textbook evidence")
    bio_chapters = Counter(row["chapter_number"] for row in rows if row["book_id"] == "biology")
    ps_chapters = Counter(row["chapter_number"] for row in rows if row["book_id"] == "physical_sciences")
    if bio_chapters != Counter({chapter: 2 for chapter in range(1, 11)}):
        errors.append(f"biology chapter distribution invalid: {bio_chapters}")
    if set(ps_chapters) != set(range(1, 13)):
        errors.append(f"physical sciences chapters missing: {set(range(1,13)) - set(ps_chapters)}")

    pdfs = {
        "biology": PdfReader(ROOT / "books" / "X Biology EM 2025-26.pdf"),
        "physical_sciences": PdfReader(ROOT / "books" / "X Physics EM 2025-26.pdf"),
    }
    for row in rows:
        reader = pdfs[row["book_id"]]
        for page in row["accepted_pdf_pages"]:
            if page < 1 or page > len(reader.pages):
                errors.append(f"{row['question_id']}: invalid PDF page {page}")
            elif not (reader.pages[page - 1].extract_text() or "").strip():
                errors.append(f"{row['question_id']}: PDF page {page} has no text layer")

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; textbook-benchmark-review/1.0)"
    url_results = {}
    for url in sorted({row["source_url"] for row in rows}):
        try:
            response = session.get(url, timeout=30)
            url_results[url] = response.status_code
            if response.status_code != 200:
                errors.append(f"source URL returned {response.status_code}: {url}")
        except requests.RequestException as exc:
            url_results[url] = str(exc)
            errors.append(f"source URL failed: {url}: {exc}")

    result = {"rows": len(rows), "unique_ids": len({row['question_id'] for row in rows}),
              "source_urls": url_results, "errors": errors, "passed": not errors}
    (HERE / "proposal_validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
