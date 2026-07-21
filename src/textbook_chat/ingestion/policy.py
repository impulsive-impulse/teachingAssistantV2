"""Versioned conservative acceptance thresholds for uploaded textbooks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


INGESTION_POLICY_VERSION = "upload-policy-v1"
RUNTIME_PROFILE_VERSION = "retrieval-v1-derived-v1"


@dataclass(frozen=True)
class IngestionPolicy:
    """Operational validation policy, separate from frozen research values.

    Thresholds intentionally favor rejection because release one has no OCR or
    manual correction path. Every value is persisted in the processing report
    so acceptance decisions remain explainable and reproducible.
    """

    version: str = INGESTION_POLICY_VERSION
    minimum_pdf_pages: int = 20
    minimum_instructional_pages: int = 15
    minimum_text_characters_per_page: int = 100
    minimum_median_text_characters: int = 250
    minimum_text_page_ratio: float = 0.90
    maximum_replacement_character_ratio: float = 0.01
    minimum_alphabetic_character_ratio: float = 0.45
    minimum_latin_letter_ratio: float = 0.90
    minimum_english_common_word_ratio: float = 0.015
    minimum_textbook_positive_signals: int = 2
    minimum_chapters: int = 2
    minimum_chapter_confirmation_ratio: float = 0.70
    maximum_repeated_line_length: int = 180
    repeated_line_page_ratio: float = 0.30

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
