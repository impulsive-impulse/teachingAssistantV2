"""Pure validation result types used outside the HTTP layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationSignal:
    """One observable signal and its role in the suitability decision."""

    name: str
    observed: bool
    detail: str
    category: str


@dataclass(frozen=True)
class ChapterRecord:
    """A chapter boundary reconciled from outline and source-page text."""

    chapter_number: int
    chapter_title: str
    textbook_page_start: int
    pdf_page_start: int
    pdf_page_end: int
    detection_sources: list[str]
    confidence: str


@dataclass
class ValidationResult:
    """Accepted book structure plus the complete explainable gate report."""

    accepted: bool
    error_code: str | None
    user_message: str | None
    title: str
    page_count: int
    searchable_page_count: int
    content_pdf_offset: int | None
    page_mapping_method: str | None
    page_mapping_confidence: str | None
    chapters: list[ChapterRecord] = field(default_factory=list)
    pages: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    signals: list[ValidationSignal] = field(default_factory=list)
    removal_rules: list[str] = field(default_factory=list)

    def report(self, policy: dict[str, Any]) -> dict[str, Any]:
        """Return the non-sensitive processing report persisted for diagnostics."""

        return {
            "accepted": self.accepted,
            "error_code": self.error_code,
            "user_message": self.user_message,
            "title": self.title,
            "page_count": self.page_count,
            "searchable_page_count": self.searchable_page_count,
            "content_pdf_offset": self.content_pdf_offset,
            "page_mapping_method": self.page_mapping_method,
            "page_mapping_confidence": self.page_mapping_confidence,
            "chapters": [asdict(chapter) for chapter in self.chapters],
            "metrics": self.metrics,
            "signals": [asdict(signal) for signal in self.signals],
            "removal_rules": self.removal_rules,
            "policy": policy,
        }
