"""Conservative local validation and structure detection for textbook PDFs.

No OCR, remote classifier, benchmark labels, or book-specific hard-coded
metadata is used here. The validator accepts only files whose text layer,
instructional structure, page provenance, and chapter boundaries can all be
established automatically with high confidence.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any, Callable, Iterable

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError

from textbook_audit.pipeline import EQUATION_RE, FIGURE_REF_RE, TABLE_RE, section_title

from .models import ChapterRecord, ValidationResult, ValidationSignal
from .policy import IngestionPolicy


Progress = Callable[[str, int, int], None]
WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?")
ROMAN_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
GENERIC_OUTLINE_RE = re.compile(r"^(?:lesson|chapter|unit)?[-_\s]*\d+\.pdf$|^\d+\.pdf$", re.IGNORECASE)
CHAPTER_MARKER_RE = re.compile(r"\b(?:chapter|unit|lesson)\s*[-:]?\s*(\d{1,3})?\b", re.IGNORECASE)
HEADING_NUMBER_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,2})\s+([A-Za-z][^\n]{2,100})$")
EXERCISE_RE = re.compile(
    r"\b(exercises?|review questions?|learning objectives?|learning outcomes?|activities|"
    r"worked examples?|summary|check your progress|think and discuss)\b",
    re.IGNORECASE,
)
PAPER_RE = re.compile(r"\babstract\b.*\b(?:methods?|methodology)\b.*\bresults?\b", re.IGNORECASE | re.DOTALL)
REPORT_RE = re.compile(r"\bexecutive summary\b.*\bfindings\b", re.IGNORECASE | re.DOTALL)
REFERENCE_RE = re.compile(r"(?m)^\s*references\s*$", re.IGNORECASE)
TOC_RE = re.compile(r"\b(?:table of contents|contents|index)\b", re.IGNORECASE)
ENGLISH_COMMON_WORDS = frozenset(
    "the of and to in is are was were for with from by as this that these those it its "
    "we you they can may chapter activity example question answer explain describe define "
    "what how why when which students learning".split()
)


class TextbookValidationError(ValueError):
    """An expected gate rejection with stable code and safe user language."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.user_message = message


class TextbookValidator:
    """Validate one staged PDF and produce normalized page/chapter records."""

    def __init__(self, policy: IngestionPolicy, maximum_pages: int):
        self.policy = policy
        self.maximum_pages = maximum_pages

    def validate(
        self,
        source: Path,
        book_id: str,
        source_filename: str,
        progress: Progress | None = None,
    ) -> ValidationResult:
        notify = progress or (lambda _stage, _current, _total: None)
        try:
            reader = PdfReader(source, strict=True)
            if reader.is_encrypted:
                raise TextbookValidationError("pdf_encrypted", "Password-protected PDFs are not supported.")
            page_count = len(reader.pages)
            if page_count < self.policy.minimum_pdf_pages:
                raise TextbookValidationError(
                    "pdf_too_short", "This file is too short to establish a reliable textbook structure."
                )
            if page_count > self.maximum_pages:
                raise TextbookValidationError(
                    "pdf_too_large", "This PDF exceeds the configured local page limit."
                )
            raw_pages = self._extract_pages(reader, notify)
            title = self._infer_title(reader, raw_pages, source_filename)
            repeated = _repeated_running_lines(raw_pages, self.policy)
            cleaned_pages = [_clean_page(text, repeated) for text in raw_pages]
            outline = _outline_chapters(reader)
            metrics = self._text_metrics(cleaned_pages, outline)
            self._require_text_layer(metrics)
            language_metrics = self._language_metrics(cleaned_pages)
            metrics.update(language_metrics)
            self._require_english(language_metrics)
            signals = self._textbook_signals(cleaned_pages, outline)
            self._require_textbook(signals)
            offset, mapping_method, mapping_confidence, chapters = self._map_structure(
                cleaned_pages, outline
            )
            records = self._page_records(
                reader, raw_pages, cleaned_pages, book_id, source_filename, offset, chapters
            )
            searchable = [page for page in records if _is_searchable(page, chapters)]
            if len(searchable) < self.policy.minimum_instructional_pages:
                raise TextbookValidationError(
                    "insufficient_instructional_text",
                    "Not enough mapped instructional text was found to build a textbook index.",
                )
            metrics.update({
                "searchable_pages": len(searchable),
                "formula_pages": sum(page["has_equation_like_text"] for page in searchable),
                "table_pages": sum(page["has_table"] for page in searchable),
                "image_pages": sum(page["has_image"] for page in searchable),
                "chapter_count": len(chapters),
            })
            return ValidationResult(
                accepted=True,
                error_code=None,
                user_message=None,
                title=title,
                page_count=page_count,
                searchable_page_count=len(searchable),
                content_pdf_offset=offset,
                page_mapping_method=mapping_method,
                page_mapping_confidence=mapping_confidence,
                chapters=chapters,
                pages=records,
                metrics=metrics,
                signals=signals,
                removal_rules=[f"exact repeated running line: {line}" for line in sorted(repeated)],
            )
        except TextbookValidationError:
            raise
        except (PdfReadError, FileNotDecryptedError, OSError, ValueError, KeyError) as exc:
            raise TextbookValidationError(
                "pdf_corrupt", "The PDF is corrupt or contains pages that cannot be extracted reliably."
            ) from exc

    def _extract_pages(self, reader: PdfReader, progress: Progress) -> list[str]:
        output: list[str] = []
        total = len(reader.pages)
        for index, page in enumerate(reader.pages, 1):
            try:
                output.append(page.extract_text() or "")
            except Exception as exc:
                raise TextbookValidationError(
                    "page_extraction_failed", f"PDF page {index} could not be extracted reliably."
                ) from exc
            progress("extracting_pages", index, total)
        return output

    def _infer_title(self, reader: PdfReader, pages: list[str], filename: str) -> str:
        metadata_title = str(getattr(reader.metadata, "title", "") or "").strip()
        metadata_is_working_file = bool(
            re.search(r"\.(?:pdf|pmd|docx?)$|initial pages|^untitled$|^microsoft word$", metadata_title, re.IGNORECASE)
        )
        if 3 <= len(metadata_title) <= 200 and not metadata_is_working_file:
            return " ".join(metadata_title.split())
        candidates = []
        class_label = None
        for line in "\n".join(pages[:4]).splitlines():
            value = " ".join(line.split()).strip(" -–—")
            if 4 <= len(value) <= 100 and sum(char.isalpha() for char in value) >= 4:
                if re.fullmatch(r"(?:class|grade)\s*(?:[ivxlcdm]+|\d+)", value, re.IGNORECASE):
                    class_label = value.title()
                    continue
                candidates.append(value)
        if candidates:
            # Cover titles tend to be concise and use title/upper case.
            scored = sorted(candidates, key=lambda value: (-_title_score(value), len(value)))
            if _title_score(scored[0]) > 0:
                title = _collapse_repetition(scored[0])
                return f"{title} – {class_label}"[:200] if class_label else title[:200]
        return re.sub(r"[_-]+", " ", Path(filename).stem).strip()[:200] or "Untitled textbook"

    def _text_metrics(
        self, pages: list[str], outline: list[tuple[str, int]] | None = None
    ) -> dict[str, Any]:
        """Measure likely body pages so blank covers do not cause false rejection."""

        body_start = min((page for _title, page in (outline or [])), default=1)
        body_pages = pages[max(0, body_start - 1):] or pages
        lengths = [len(page.strip()) for page in body_pages]
        text_pages = [length >= self.policy.minimum_text_characters_per_page for length in lengths]
        combined = "".join(body_pages)
        characters = max(len(combined), 1)
        return {
            "likely_instructional_page_start": body_start,
            "likely_instructional_pages_measured": len(body_pages),
            "pages_with_text": sum(text_pages),
            "near_empty_pages": len(body_pages) - sum(text_pages),
            "text_page_ratio": sum(text_pages) / len(body_pages),
            "median_text_characters": float(median(lengths)),
            "total_extracted_characters": len(combined),
            "alphabetic_character_ratio": sum(char.isalpha() for char in combined) / characters,
            "replacement_character_ratio": (combined.count("�") + combined.count("\ufffd")) / characters,
        }

    def _require_text_layer(self, metrics: dict[str, Any]) -> None:
        if metrics["text_page_ratio"] < self.policy.minimum_text_page_ratio:
            raise TextbookValidationError(
                "scanned_or_image_only", "This PDF appears to be scanned. OCR is not supported."
            )
        if metrics["median_text_characters"] < self.policy.minimum_median_text_characters:
            raise TextbookValidationError(
                "insufficient_instructional_text", "The PDF does not contain enough extractable instructional text."
            )
        if metrics["replacement_character_ratio"] > self.policy.maximum_replacement_character_ratio:
            raise TextbookValidationError(
                "corrupt_text_extraction", "The PDF text extraction contains too many corrupted characters."
            )
        if metrics["alphabetic_character_ratio"] < self.policy.minimum_alphabetic_character_ratio:
            raise TextbookValidationError(
                "corrupt_text_extraction", "The extracted text is not reliable enough to build an index."
            )

    def _language_metrics(self, pages: list[str]) -> dict[str, Any]:
        prose = [page for page in pages if len(WORD_RE.findall(page)) >= 40]
        if not prose:
            return {"latin_letter_ratio": 0.0, "english_common_word_ratio": 0.0, "language_samples": 0}
        indexes = sorted({0, len(prose) // 4, len(prose) // 2, 3 * len(prose) // 4, len(prose) - 1})
        sample = "\n".join(prose[index][:6000] for index in indexes)
        letters = [char for char in sample if char.isalpha()]
        latin = sum("LATIN" in unicodedata.name(char, "") for char in letters)
        words = [word.lower().replace("’", "'") for word in WORD_RE.findall(sample)]
        common = sum(word in ENGLISH_COMMON_WORDS for word in words)
        return {
            "latin_letter_ratio": latin / max(len(letters), 1),
            "english_common_word_ratio": common / max(len(words), 1),
            "language_samples": len(indexes),
        }

    def _require_english(self, metrics: dict[str, Any]) -> None:
        if (
            metrics["latin_letter_ratio"] < self.policy.minimum_latin_letter_ratio
            or metrics["english_common_word_ratio"] < self.policy.minimum_english_common_word_ratio
        ):
            raise TextbookValidationError(
                "not_english", "This file does not appear to be an English instructional textbook."
            )

    def _textbook_signals(
        self, pages: list[str], outline: list[tuple[str, int]]
    ) -> list[ValidationSignal]:
        combined = "\n".join(pages)
        beginning = "\n".join(pages[: max(5, len(pages) // 8)])
        signals = [
            ValidationSignal("table_of_contents", bool(TOC_RE.search(beginning)),
                             "A contents/index heading was detected.", "positive"),
            ValidationSignal("multi_chapter_outline", len(outline) >= self.policy.minimum_chapters,
                             f"{len(outline)} instructional outline entries were detected.", "positive"),
            ValidationSignal("chapter_headings", len(CHAPTER_MARKER_RE.findall(combined)) >= 2,
                             "Repeated chapter, unit, or lesson markers were detected.", "positive"),
            ValidationSignal("instructional_features", len(EXERCISE_RE.findall(combined)) >= 3,
                             "Exercises, activities, examples, summaries, or objectives recur.", "positive"),
            ValidationSignal("hierarchical_sections", len(HEADING_NUMBER_RE.findall(combined)) >= 3,
                             "Repeated hierarchical numbered sections were detected.", "positive"),
            ValidationSignal("research_paper_structure", bool(PAPER_RE.search(combined[:50000]) and REFERENCE_RE.search(combined)),
                             "Abstract/method/results/reference structure was checked.", "negative"),
            ValidationSignal("report_structure", bool(REPORT_RE.search(combined[:50000])),
                             "Executive-summary/findings report structure was checked.", "negative"),
        ]
        return signals

    def _require_textbook(self, signals: list[ValidationSignal]) -> None:
        positives = sum(signal.observed for signal in signals if signal.category == "positive")
        negatives = sum(signal.observed for signal in signals if signal.category == "negative")
        if positives < self.policy.minimum_textbook_positive_signals or negatives:
            raise TextbookValidationError(
                "not_textbook", "This file does not appear to be an English instructional textbook."
            )

    def _map_structure(
        self, pages: list[str], outline: list[tuple[str, int]]
    ) -> tuple[int, str, str, list[ChapterRecord]]:
        candidates = [(title, page) for title, page in outline if page >= 1]
        if len(candidates) < self.policy.minimum_chapters:
            candidates = _body_chapter_candidates(pages)
        candidates = _deduplicate_starts(candidates)
        if len(candidates) < self.policy.minimum_chapters:
            raise TextbookValidationError(
                "chapter_map_unreliable", "A reliable chapter and printed-page map could not be detected."
            )
        first_pdf = candidates[0][1]
        if first_pdf <= 1 or not TOC_RE.search("\n".join(pages[:first_pdf])):
            raise TextbookValidationError(
                "page_map_unreliable", "A reliable chapter and printed-page map could not be detected."
            )
        # The strict v1 adapter accepts this offset only when a contents page is
        # present before a multi-chapter instructional outline and each start is
        # confirmed in page text. It never invents nonnumeric front-matter pages.
        offset = first_pdf - 1
        chapter_records: list[ChapterRecord] = []
        confirmed = 0
        for index, (outline_title, pdf_start) in enumerate(candidates):
            pdf_end = candidates[index + 1][1] - 1 if index + 1 < len(candidates) else len(pages)
            detected_title = _chapter_title_from_page(pages[pdf_start - 1], outline_title, index + 1)
            title_tokens = _meaningful_tokens(detected_title)
            page_tokens = set(_meaningful_tokens(pages[pdf_start - 1][:1800]))
            is_confirmed = bool(title_tokens) and len(set(title_tokens) & page_tokens) >= max(1, len(set(title_tokens)) // 2)
            confirmed += is_confirmed
            chapter_records.append(ChapterRecord(
                chapter_number=index + 1,
                chapter_title=detected_title,
                textbook_page_start=pdf_start - offset,
                pdf_page_start=pdf_start,
                pdf_page_end=pdf_end,
                detection_sources=["pdf_outline" if outline else "body_heading", "source_page_heading", "contents_precedes_body"],
                confidence="high" if is_confirmed else "medium",
            ))
        if confirmed / len(chapter_records) < self.policy.minimum_chapter_confirmation_ratio:
            raise TextbookValidationError(
                "chapter_map_unreliable", "A reliable chapter and printed-page map could not be detected."
            )
        return offset, "contents_outline_constant_offset", "high", chapter_records

    def _page_records(
        self,
        reader: PdfReader,
        raw_pages: list[str],
        cleaned_pages: list[str],
        book_id: str,
        filename: str,
        offset: int,
        chapters: list[ChapterRecord],
    ) -> list[dict[str, Any]]:
        records = []
        for index, (raw, cleaned) in enumerate(zip(raw_pages, cleaned_pages), 1):
            chapter = next((chapter for chapter in chapters if chapter.pdf_page_start <= index <= chapter.pdf_page_end), None)
            numeric_page = index - offset if chapter is not None else None
            notes = []
            if numeric_page is None:
                notes.append("front_matter_or_non_instructional")
            if "�" in raw or "\ufffd" in raw:
                notes.append("replacement_character_present_in_raw_text")
            has_image = _page_has_image(reader.pages[index - 1])
            if has_image and FIGURE_REF_RE.search(raw):
                notes.append("diagram_reference_present")
            records.append({
                "book_id": book_id,
                "source_file": filename,
                "pdf_page_number": index,
                "textbook_page_number": numeric_page,
                "chapter_number": chapter.chapter_number if chapter else None,
                "chapter_title": chapter.chapter_title if chapter else None,
                "section_title": section_title(cleaned),
                "raw_text": raw,
                "cleaned_text": cleaned,
                "text_length": len(cleaned),
                "has_image": has_image,
                "has_table": bool(TABLE_RE.search(raw)),
                "has_equation_like_text": bool(EQUATION_RE.search(raw)),
                "extraction_notes": notes,
            })
        return records


def _outline_chapters(reader: PdfReader) -> list[tuple[str, int]]:
    output: list[tuple[str, int]] = []

    def visit(items: Iterable[Any]) -> None:
        for item in items:
            if isinstance(item, list):
                visit(item)
                continue
            title = " ".join(str(getattr(item, "title", "")).split()).strip()
            try:
                page = reader.get_destination_page_number(item) + 1
            except Exception:
                continue
            if page > 1 and not re.search(r"initial|front matter|contents|index", title, re.IGNORECASE):
                output.append((title, page))

    outline = getattr(reader, "outline", [])
    if isinstance(outline, list):
        visit(outline)
    return output


def _body_chapter_candidates(pages: list[str]) -> list[tuple[str, int]]:
    output = []
    for pdf_page, text in enumerate(pages, 1):
        if CHAPTER_MARKER_RE.search(text):
            output.append((_chapter_title_from_page(text, "", len(output) + 1), pdf_page))
    return output


def _deduplicate_starts(candidates: list[tuple[str, int]]) -> list[tuple[str, int]]:
    return [(title, page) for page, title in sorted({page: title for title, page in candidates}.items())]


def _chapter_title_from_page(text: str, outline_title: str, ordinal: int) -> str:
    outline = Path(outline_title).name
    if outline and not GENERIC_OUTLINE_RE.match(outline):
        return re.sub(r"\s+", " ", re.sub(r"\.pdf$", "", outline, flags=re.IGNORECASE)).strip()[:160]
    lines = [" ".join(line.split()).strip() for line in text.splitlines() if line.strip()]
    strict_marker = re.compile(r"^[^A-Za-z]{0,2}(?:chapter|unit|lesson)\b(?:\s*[-:]?\s*(?:\d{1,3})?)?\s*(.*)$", re.IGNORECASE)
    for index in range(min(40, len(lines)) - 1, -1, -1):
        line = lines[index]
        marker = strict_marker.match(line)
        if marker:
            inline_title = marker.group(1).strip(" -–—\x00-\x1f")
            if sum(char.isalpha() for char in inline_title) >= 3:
                return _normalize_heading(inline_title, ordinal)[:160]
            after = lines[index + 1] if index + 1 < len(lines) else ""
            before = lines[index - 1] if index else ""
            before_two = lines[index - 2] if index >= 2 else ""
            if _plausible_heading(after):
                return _normalize_heading(after, ordinal)[:160]
            joined_before = f"{before_two} {before}".strip()
            if _plausible_heading(joined_before):
                return _normalize_heading(joined_before, ordinal)[:160]
            if _plausible_heading(before):
                return _normalize_heading(before, ordinal)[:160]
    return f"Chapter {ordinal}"


def _title_score(value: str) -> float:
    letters = [char for char in value if char.isalpha()]
    if not letters:
        return -10
    upper_ratio = sum(char.isupper() for char in letters) / len(letters)
    words = value.split()
    return (2 if 1 <= len(words) <= 10 else 0) + upper_ratio - len(value) / 300


def _collapse_repetition(value: str) -> str:
    """Collapse producer-generated cover text repeated without separators."""

    compact = value.strip()
    for size in range(3, len(compact) // 2 + 1):
        unit = compact[:size]
        repetitions = len(compact) // size
        if repetitions >= 2 and unit * repetitions == compact:
            return unit.strip()
    return compact


def _normalize_heading(value: str, ordinal: int) -> str:
    value = re.sub(rf"\s*{ordinal}\s*$", "", value).strip(" -–—\x00-\x1f")
    return re.sub(r"\s+", " ", value)


def _plausible_heading(value: str) -> bool:
    words = value.split()
    return (
        1 <= len(words) <= 12
        and 3 <= len(value) <= 120
        and sum(char.isalpha() for char in value) >= 3
        and not re.search(r"[?.!]$|\b(?:table|activity|figure|fig)\s*-?\s*\d+", value, re.IGNORECASE)
    )


def _meaningful_tokens(text: str) -> list[str]:
    return [word.lower() for word in WORD_RE.findall(text) if len(word) > 3]


def _line_key(line: str) -> str:
    return " ".join(line.split()).strip()


def _repeated_running_lines(pages: list[str], policy: IngestionPolicy) -> set[str]:
    counts: Counter[str] = Counter()
    for text in pages:
        candidates = {_line_key(line) for line in text.splitlines()[:3] + text.splitlines()[-3:]}
        counts.update(value for value in candidates if 4 <= len(value) <= policy.maximum_repeated_line_length)
    minimum = max(3, int(len(pages) * policy.repeated_line_page_ratio))
    return {line for line, count in counts.items() if count >= minimum and not line.isdigit()}


def _clean_page(text: str, repeated: set[str]) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = _line_key(raw_line)
        if not line or line in repeated:
            continue
        lines.append(line)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"(?<=[A-Za-z])-\s*\n\s*(?=[a-z])", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _page_has_image(page: Any) -> bool:
    try:
        resources = page.get("/Resources") or {}
        xobjects = resources.get("/XObject") or {}
        return any(obj.get_object().get("/Subtype") == "/Image" for obj in xobjects.values())
    except Exception:
        return False


def _is_searchable(page: dict[str, Any], chapters: list[ChapterRecord]) -> bool:
    return (
        page.get("textbook_page_number") is not None
        and bool(page.get("cleaned_text", "").strip())
        and any(
            chapter.pdf_page_start <= page["pdf_page_number"] <= chapter.pdf_page_end
            for chapter in chapters
        )
    )
