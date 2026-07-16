# Phase G — deterministic query processing

All runs use BGE-small fixed 600/100 Hybrid RRF and gold-blind static rules.

| Run | Method | Fusion | Changed | H@1/3/5 | MRR | Natural H@1/3/5 | Canonical H@5 | p95 | Decision |
|---|---|---|---:|---:|---:|---:|---:|---:|---|
| phase_g_g0_raw | raw | False | 0 | 20/39/45 | 0.514 | 8/11/14 | 31/41 | 44.0 ms | retain |
| phase_g_g0_spelling_normalization | spelling_normalization | False | 0 | 20/39/45 | 0.514 | 8/11/14 | 31/41 | 56.4 ms | reject |
| phase_g_g0_grammar_cleanup | grammar_cleanup | False | 5 | 20/39/45 | 0.514 | 8/11/14 | 31/41 | 48.4 ms | retain |
| phase_g_g0_textbook_synonym_expansion | textbook_synonym_expansion | False | 19 | 21/43/50 | 0.551 | 8/13/16 | 34/41 | 46.7 ms | retain |
| phase_g_g0_acronym_expansion | acronym_expansion | False | 5 | 21/39/45 | 0.522 | 8/11/14 | 31/41 | 41.7 ms | retain |
| phase_g_g0_formula_symbol_normalization | formula_symbol_normalization | False | 11 | 22/38/47 | 0.530 | 8/12/15 | 32/41 | 42.1 ms | retain |
| phase_g_g1_original_plus_textbook_synonym_expansion | textbook_synonym_expansion | True | 19 | 20/42/48 | 0.528 | 8/13/16 | 32/41 | 146.5 ms | retain |
| phase_g_g1_original_plus_formula_symbol_normalization | formula_symbol_normalization | True | 11 | 22/37/45 | 0.524 | 8/11/14 | 31/41 | 125.0 ms | retain |

## Final deterministic selection

Winner: `phase_g_g0_textbook_synonym_expansion`.

Only textbook synonym expansion and formula/symbol normalization advanced to fusion. Grammar cleanup changed five queries without changing Hit@K, while acronym expansion added one overall Hit@1 but no natural-student Hit@K; neither was treated as a meaningful finalist.

Standalone synonym expansion beat original-plus-synonym fusion in quality and latency. Every transformed query and fired rule is stored beside its full ranking.
