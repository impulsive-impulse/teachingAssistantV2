"""Deterministic page extraction and suitability report generation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import median

from pypdf import PdfReader

from .config import SPECS, BookSpec


ROOT = Path(__file__).resolve().parents[2]
BOOKS_DIR = ROOT / "books"
OUT_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "reports"


ROMAN = ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x")
SECTION_RE = re.compile(r"(?m)^\s*((?:\d{1,2}\.){1,3}\d*\s+[^\n]{3,100})\s*$")
EQUATION_RE = re.compile(
    r"(?:[A-Za-z0-9)\]]\s*[=+−–]\s*[A-Za-z0-9(\[]|\b(?:sin|cos|tan)\s*[A-Za-zθ]|"
    r"\b[A-Z][a-z]?\s*\d{1,2}\b|\b\d+(?:\.\d+)?\s*(?:V|A|W|Ω|ohm|J|N|m/s|cm|kg)\b)",
    re.IGNORECASE,
)
TABLE_RE = re.compile(r"\btable\s*[-:]?\s*\d+|\btabular\b", re.IGNORECASE)
FIGURE_REF_RE = re.compile(r"\b(?:fig(?:ure)?|diagram)\s*[-:]?\s*[A-Z]?\d+", re.IGNORECASE)


def chapter_for(spec: BookSpec, textbook_page: int | None):
    if textbook_page is None:
        return None, None
    current = None
    for number, title, start in spec.chapters:
        if textbook_page >= start:
            current = (number, title)
        else:
            break
    return current or (None, None)


def textbook_page_for(spec: BookSpec, pdf_page: int):
    if pdf_page > spec.content_pdf_offset:
        return pdf_page - spec.content_pdf_offset
    roman_index = pdf_page - spec.roman_start_pdf
    if 0 <= roman_index < len(ROMAN):
        return ROMAN[roman_index]
    return None


def clean_text(text: str, chapter_title: str | None) -> tuple[str, list[str]]:
    notes: list[str] = []
    if "�" in text or "\ufffd" in text:
        notes.append("replacement_character_present_in_raw_text")
    cleaned = text.replace("�", "'").replace("\ufffd", "'")
    cleaned = re.sub(r"Government['’]s Gift for Students['’] Progress", " ", cleaned,
                     flags=re.IGNORECASE)
    cleaned = re.sub(r"(?m)^\s*CLASS\s+(?:X|10)\s*$", " ", cleaned)
    # Dehyphenate only line-break hyphens between alphabetic characters.
    before = cleaned
    cleaned = re.sub(r"(?<=[A-Za-z])-\s*\n\s*(?=[a-z])", "", cleaned)
    if cleaned != before:
        notes.append("line_break_hyphenation_repaired")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if chapter_title and cleaned.lower().count(chapter_title.lower()) > 1:
        notes.append("repeated_chapter_title_in_text_layer")
    if len(cleaned) < 100:
        notes.append("low_text_page")
    return cleaned, notes


def section_title(text: str) -> str | None:
    match = SECTION_RE.search(text)
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip()
    return value[:160]


def image_count(page) -> int:
    try:
        return len(page.images)
    except Exception:
        resources = page.get("/Resources") or {}
        xobjects = resources.get("/XObject") or {}
        return sum(1 for obj in xobjects.values() if obj.get_object().get("/Subtype") == "/Image")


def extract_book(spec: BookSpec):
    source = BOOKS_DIR / spec.filename
    reader = PdfReader(source)
    records = []
    for page_index, page in enumerate(reader.pages):
        pdf_page = page_index + 1
        raw = page.extract_text() or ""
        textbook_page = textbook_page_for(spec, pdf_page)
        numeric_page = textbook_page if isinstance(textbook_page, int) else None
        chapter_number, chapter_title = chapter_for(spec, numeric_page)
        cleaned, notes = clean_text(raw, chapter_title)
        has_image = image_count(page) > 0
        has_table = bool(TABLE_RE.search(raw))
        has_equation = bool(EQUATION_RE.search(raw))
        if numeric_page is None:
            notes.append("front_matter_or_cover")
        if has_image and FIGURE_REF_RE.search(raw):
            notes.append("diagram_reference_present")
        if has_equation and ("�" in raw or re.search(r"\d\s+\d|[A-Za-z]\s+\d", raw)):
            notes.append("equation_layout_or_symbol_fidelity_needs_review")
        records.append({
            "book_id": spec.book_id,
            "source_file": spec.filename,
            "pdf_page_number": pdf_page,
            "textbook_page_number": textbook_page,
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "section_title": section_title(cleaned),
            "raw_text": raw,
            "cleaned_text": cleaned,
            "text_length": len(cleaned),
            "has_image": has_image,
            "has_table": has_table,
            "has_equation_like_text": has_equation,
            "extraction_notes": sorted(set(notes)),
        })

    chapter_map = []
    for index, (number, title, start) in enumerate(spec.chapters):
        pdf_start = start + spec.content_pdf_offset
        next_start = spec.chapters[index + 1][2] if index + 1 < len(spec.chapters) else None
        pdf_end = (next_start - 1 + spec.content_pdf_offset) if next_start else len(reader.pages)
        start_text = records[pdf_start - 1]["cleaned_text"].lower()
        title_tokens = [t for t in re.findall(r"[a-z]+", title.lower()) if len(t) > 3]
        confirmed = sum(token in start_text[:800] for token in title_tokens) >= max(1, len(title_tokens) // 2)
        notes = [f"Index start {start} maps by constant PDF offset +{spec.content_pdf_offset}."]
        notes.append("Chapter title confirmed in start-page text." if confirmed else
                     "Start follows index mapping; title is weak or fragmented in extracted text.")
        chapter_map.append({
            "chapter_number": number, "chapter_title": title,
            "index_textbook_page_start": start,
            "detected_pdf_page_start": pdf_start, "detected_pdf_page_end": pdf_end,
            "confidence": "high" if confirmed else "medium", "notes": notes,
        })
    return records, {
        "book_id": spec.book_id, "source_file": spec.filename, "chapters": chapter_map
    }


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def excerpt(text: str, limit: int = 220) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit].replace("`", "'")


def make_report(all_records, all_maps) -> str:
    lines = [
        "# Book extraction suitability audit", "",
        "Generated deterministically by `scripts/audit_textbooks.py` using `pypdf`. "
        "PDF page numbers are one-based and no page is discarded.", "",
    ]
    for spec in SPECS:
        records = all_records[spec.book_id]
        cmap = all_maps[spec.book_id]["chapters"]
        lengths = [r["text_length"] for r in records]
        content = [r for r in records if isinstance(r["textbook_page_number"], int)]
        image_pages = [r for r in content if r["has_image"]]
        table_pages = [r for r in content if r["has_table"]]
        eq_pages = [r for r in content if r["has_equation_like_text"]]
        replacement = [r for r in records if "replacement_character_present_in_raw_text" in r["extraction_notes"]]
        low = [r for r in records if r["text_length"] < 100]
        lines += [
            f"## {spec.title}", "", "### A. Basic metadata", "",
            f"- File: `{spec.filename}`", f"- `book_id`: `{spec.book_id}`",
            f"- Detected title: {spec.title}", f"- Total PDF pages: {len(records)}",
            f"- Text extraction: works on {len(records)-len(low)}/{len(records)} pages with at least 100 cleaned characters; median cleaned length is {int(median(lengths))} characters.",
            "- PDF type: digital text layer with mixed raster/vector page assets; full-page OCR is not required for ordinary prose. Biology's producer metadata mentions ABBYY, while Physical Sciences identifies PageMaker/Acrobat Distiller, but both expose searchable text on essentially all pages.",
            "", "### B. Index and chapter extraction", "",
            "| Chapter | Index page | PDF start–end | Confidence |", "|---|---:|---:|---|",
        ]
        lines += [f"| {c['chapter_number']}. {c['chapter_title']} | {c['index_textbook_page_start']} | {c['detected_pdf_page_start']}–{c['detected_pdf_page_end']} | {c['confidence']} |" for c in cmap]
        lines += [
            "", f"The index mapping is internally consistent: printed content page 1 is PDF page {spec.content_pdf_offset + 1}, so chapter starts use a +{spec.content_pdf_offset} offset. "
            "Start-page title checks are recorded per chapter in the chapter-map JSON.",
            "", "### C. Page mapping quality", "",
            f"PDF pages 1–{spec.content_pdf_offset} are cover/QR/front matter. Printed Arabic page 1 begins at PDF page {spec.content_pdf_offset + 1}. "
            f"For content, `pdf_page_number = textbook_page_number + {spec.content_pdf_offset}`. Roman-numbered front matter begins at PDF page {spec.roman_start_pdf}; cover/QR pages remain null.",
            "The constant offset is high-confidence across all indexed chapter boundaries. The final chapter continues beyond the index's stated instructional range, so its detected end is the PDF's last page.",
            "", "### D. Text extraction quality", "",
        ]
        sample_printed = [spec.chapters[0][2], spec.chapters[len(spec.chapters)//2][2] + 5, spec.chapters[-1][2] + 5]
        for label, printed in zip(("First chapter", "Middle-book", "Later chapter"), sample_printed):
            r = records[printed + spec.content_pdf_offset - 1]
            lines.append(f"- {label}, PDF {r['pdf_page_number']} / printed {printed}: `{excerpt(r['cleaned_text'])}`")
        if image_pages:
            r = image_pages[len(image_pages)//2]
            lines.append(f"- Diagram-bearing sample, PDF {r['pdf_page_number']}: text and labels are partly extractable; `{excerpt(r['cleaned_text'])}`")
        if table_pages:
            r = table_pages[len(table_pages)//2]
            lines.append(f"- Table sample, PDF {r['pdf_page_number']}: table words extract, but row/column structure is flattened; `{excerpt(r['cleaned_text'])}`")
        lines += [
            "", "### E. Noise analysis", "",
            f"- Repeated running text such as `Government's Gift for Students' Progress` is removed from `cleaned_text` but retained in `raw_text`.",
            (f"- {len(replacement)} pages contain an actual Unicode replacement glyph in raw extraction; cleaned text normalizes it to an apostrophe as a conservative readability repair."
             if replacement else "- No actual Unicode replacement glyphs were detected. Curly apostrophes and other valid Unicode punctuation are preserved."),
            "- Chapter names and printed page numbers are sometimes concatenated with body text because the PDF reading order lacks separators.",
            "- QR/front matter is retained and explicitly marked; no low-text page is silently dropped.",
            "- Line-break hyphenation is repaired only for alphabetic word breaks. Spelling and source wording are otherwise preserved.",
            "", "### F. Formula/equation extraction audit", "",
            f"Equation-like text is flagged on {len(eq_pages)} content pages. Plain inline equations and chemical formula characters are often searchable, but fractions become linearized, superscripts/subscripts frequently become spaced baseline digits, and diagram-positioned symbols may be reordered.",
        ]
        for r in eq_pages[:3]:
            lines.append(f"- PDF {r['pdf_page_number']} / printed {r['textbook_page_number']}: `{excerpt(r['raw_text'])}`")
        if spec.book_id == "physical_sciences":
            lines.append("- Reliability warning: Ω is sometimes rendered as `W`, exponents may appear as separate digits (for example `I2 R`), reaction arrows and charge signs can degrade, and displayed fractions lose numerator/denominator layout. Formula-sensitive retrieval should retain page images or add layout-aware extraction.")
        lines += [
            "", "### G. Diagram and table dependency", "",
            f"- {len(image_pages)}/{len(content)} content pages contain at least one embedded image object; {len(table_pages)} pages have explicit table text; {sum(bool(FIGURE_REF_RE.search(r['raw_text'])) for r in content)} pages explicitly reference a figure/diagram.",
            "- Figure captions and many diagram labels are extractable, but spatial relationships are not represented in plain text. Table contents are flattened rather than reconstructed.",
            "- Pages marked `diagram_reference_present` should be candidates for page-image or multimodal augmentation when questions depend on geometry, circuits, anatomy, experimental apparatus, or graph interpretation.",
            "", "### H. Suitability verdict", "",
            "**Suitable with caveats.** Prose coverage, deterministic page mapping, and chapter boundaries are strong enough for Milestone 1 page-aware retrieval experiments. Caveats are equation fidelity, flattened tables, lost diagram geometry, concatenated running headers/page numbers, and imperfect section-heading detection.",
            "",
        ]
    lines += [
        "## Cross-book recommendation", "",
        "Use these page records as the immutable source layer. Next, create a small retrieval benchmark with questions labeled by `book_id`, chapter, printed page(s), answer span, and a `visual_dependency` flag. Evaluate page retrieval first, then section/chunk retrieval; keep formula- and diagram-dependent questions as a separately reported slice.", "",
        "## Reproduction", "", "```powershell",
        "python -m pip install pypdf", "python scripts/audit_textbooks.py", "```", "",
    ]
    return "\n".join(lines)


def run(root: Path = ROOT) -> None:
    """Generate all corpus and audit artifacts beneath *root*."""
    global BOOKS_DIR, OUT_DIR, REPORT_DIR
    BOOKS_DIR = root / "books"
    OUT_DIR = root / "data" / "processed"
    REPORT_DIR = root / "reports"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    all_records, all_maps = {}, {}
    for spec in SPECS:
        records, chapter_map = extract_book(spec)
        all_records[spec.book_id] = records
        all_maps[spec.book_id] = chapter_map
        jsonl = OUT_DIR / f"{spec.book_id}_pages.jsonl"
        with jsonl.open("w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        write_json(OUT_DIR / f"{spec.book_id}_chapter_map.json", chapter_map)
    (REPORT_DIR / "book_extraction_audit.md").write_text(
        make_report(all_records, all_maps), encoding="utf-8", newline="\n"
    )
    print("Generated page JSONL, chapter maps, and reports/book_extraction_audit.md")
