"""Regression tests for deterministic, meaning-preserving query processing."""

from textbook_audit.query_processing import (
    acronym_expansion,
    formula_symbol_normalization,
    grammar_cleanup,
    process_query,
    select_phase_g_winner,
    spelling_normalization,
    textbook_synonym_expansion,
)


def test_spelling_and_grammar_rules_are_conservative() -> None:
    """Surface cleanup changes known errors but leaves clean queries alone."""
    assert spelling_normalization("Why electricty move?").text == "Why electricity move?"
    assert not spelling_normalization("Why does current flow?").changed
    assert grammar_cleanup("How food go from here?").text == "How does food go from here?"
    assert grammar_cleanup("What formula tells where a mirror image gonna form?").text.endswith(
        "going to form?")


def test_synonyms_require_every_trigger_and_preserve_original_query() -> None:
    """Domain aliases are additive and do not fire on a single generic word."""
    query = "How do plants eat?"
    result = textbook_synonym_expansion(query)
    assert result.text.startswith(query)
    assert "photosynthesis" in result.text
    assert not textbook_synonym_expansion("What did I eat?").changed


def test_acronym_and_formula_normalization_add_auditable_aliases() -> None:
    """Curriculum abbreviations and quantities retain the original wording."""
    acronym = acronym_expansion("What does 60 W over one hour mean?")
    assert acronym.text.startswith("What does 60 W") and "watt" in acronym.text
    formula = formula_symbol_normalization("How do voltage and current relate?")
    assert "potential difference V" in formula.text
    assert "electric current I" in formula.text


def test_dispatch_rejects_unknown_processors() -> None:
    """The CLI cannot silently invent an unregistered transformation."""
    try:
        process_query("unknown", "question")
    except ValueError as error:
        assert "unknown query processor" in str(error)
    else:
        raise AssertionError("unknown processor should fail")


def test_final_selection_compares_screen_and_fusion_runs() -> None:
    """A stronger direct expansion must not be hidden by fusion-only selection."""
    def record(name: str, natural_h3: int, natural_mrr: float) -> dict:
        """Build a compact Phase G record for cross-stage winner selection."""
        natural = {"hit_at_1_count": 8, "hit_at_3_count": natural_h3,
                   "hit_at_5_count": 16, "mrr": natural_mrr}
        overall = {"hit_at_1_count": 20, "hit_at_3_count": 42,
                   "hit_at_5_count": 48, "mrr": 0.53}
        return {"run_id": name, "metrics": {"natural_student": natural,
                                               "overall": overall}}
    direct = record("direct", 13, 0.56)
    fusion = record("fusion", 13, 0.54)
    assert select_phase_g_winner([fusion, direct])["run_id"] == "direct"
