"""Regression tests for Phase H representations and gold-blind activation."""

from pathlib import Path

from textbook_audit.embedding_bakeoff import searchable_pages
from textbook_audit.specialist_retrieval import (
    SPECIALISTS,
    build_specialist_corpora,
    formula_representation,
    normalize_formula_text,
    specialist_activated,
    table_representation,
    visual_caption_context,
)


ROOT = Path(__file__).resolve().parents[1]


def test_static_specialist_activation_uses_query_text() -> None:
    """Branch activation is deterministic and does not require benchmark flags."""
    assert specialist_activated("formula", "Which mirror formula should I use?")
    assert specialist_activated("table", "How do mitosis and meiosis differ?")
    assert specialist_activated("visual", "Draw the principal rays in the diagram")
    assert not specialist_activated("visual", "What is photosynthesis?")


def test_refined_activation_removes_broad_cross_branch_triggers() -> None:
    """V2 targets explicit formula/table cues and uses untouched query wording."""
    assert specialist_activated("formula", "How is power related to focal length?", "v2")
    assert specialist_activated("formula", "Energy used by a 60 W appliance", "v2")
    assert not specialist_activated("formula", "How does a concave lens correct myopia?", "v2")
    assert specialist_activated("table", "How do mitosis and meiosis differ?", "v2")
    assert not specialist_activated("table", "How do arteries and veins differ?", "v2")
    assert not specialist_activated("formula", "State the laws of reflection", "v2")
    assert specialist_activated("formula", "State the laws of reflection", "v3")


def test_formula_normalization_preserves_equation_structure_and_aliases() -> None:
    """Unicode and units are normalized without flattening line boundaries."""
    result = normalize_formula_text("V = I × R\n1 Ω = 1 V")
    assert "V = I  x  R" in result
    assert "ohm Ω" in result
    assert "\n" in result


def test_specialist_representations_are_nonempty_on_reviewed_source_pages() -> None:
    """Formula, table, and caption extractors preserve inspectable source text."""
    pages = searchable_pages(ROOT)
    formula_page = next(page for page in pages["physical_sciences"]
                        if page["pdf_page_number"] == 209)
    table_page = next(page for page in pages["biology"]
                      if page["pdf_page_number"] == 126)
    visual_page = next(page for page in pages["physical_sciences"]
                       if page["pdf_page_number"] == 18)
    assert "V = IR" in formula_representation(formula_page, True)
    assert "Header:" in table_representation(table_page, "table_rows_with_headers")
    assert "fig-8" in visual_caption_context(visual_page).lower()


def test_all_specialist_corpora_cover_both_books_deterministically() -> None:
    """Every representation has stable IDs and source-page metadata per book."""
    first = build_specialist_corpora(searchable_pages(ROOT))
    second = build_specialist_corpora(searchable_pages(ROOT))
    assert tuple(first) == SPECIALISTS
    for method in SPECIALISTS:
        assert set(first[method]) == {"biology", "physical_sciences"}
        for book in first[method]:
            assert [item["chunk_id"] for item in first[method][book]] == [
                item["chunk_id"] for item in second[method][book]]
            assert all(item["pdf_pages"] and item["text"] for item in first[method][book])
