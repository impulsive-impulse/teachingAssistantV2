# Natural Student Query Additions

Twenty reviewer-approved questions were derived from verified canonical parents. Canonical wording and gold evidence were not changed.

## Distribution

- Books: Biology 10; Physical Sciences 10.
- Styles: `cause_effect` 3; `colloquial` 4; `different_vocabulary` 3; `imperfect_grammar` 3; `misconception` 4; `short_underspecified` 3.

## Added questions and validation

| ID | Parent | Book | Style | Difficulty | Natural question | TB / PDF gold | Processed coverage | PDF coverage |
|---|---|---|---|---|---|---|---:|---:|
| BIO-023 | BIO-002 | biology | different_vocabulary | easy | How do cells get usable energy out of food? | 36 / 45 | 100.0% | 100.0% |
| BIO-024 | BIO-003 | biology | colloquial | easy | What are the million or so tiny working units in each kidney called? | 83 / 92 | 100.0% | 100.0% |
| BIO-025 | BIO-005 | biology | imperfect_grammar | medium | How food go from the mouth to the stomach, and where does breaking it down start? | 15 / 24 | 100.0% | 100.0% |
| BIO-026 | BIO-007 | biology | short_underspecified | hard | Why does blood go through the heart twice? | 58 / 67 | 100.0% | 100.0% |
| BIO-027 | BIO-008 | biology | colloquial | medium | How do kidneys turn waste in the blood into pee? | 84,85 / 93,94 | 100.0% | 100.0% |
| BIO-028 | BIO-009 | biology | misconception | hard | Does pollen turn straight into a seed? What actually happens? | 136,137 / 145,146 | 100.0% | 100.0% |
| BIO-029 | BIO-011 | biology | different_vocabulary | medium | What carries oxygen from our lungs to the rest of the body? | 36 / 45 | 100.0% | 100.0% |
| BIO-030 | BIO-014 | biology | different_vocabulary | hard | What changes when cells release energy without oxygen instead of with oxygen? | 36,40,41 / 45,49,50 | 100.0% | 100.0% |
| BIO-031 | BIO-016 | biology | misconception | hard | Do all new cells end up with only half the chromosomes? | 144,145 / 153,154 | 100.0% | 100.0% |
| BIO-032 | BIO-018 | biology | cause_effect | hard | How does saving rainwater help when wells and groundwater are running out? | 231,232 / 240,241 | 100.0% | 100.0% |
| PSC-025 | PSC-003 | physical_sciences | cause_effect | medium | If I turn up the voltage, why does more current flow through the same wire? | 199 / 209 | 100.0% | 100.0% |
| PSC-026 | PSC-004 | physical_sciences | colloquial | medium | How can moving a magnet make electricity in a wire? | 240 / 250 | 100.0% | 100.0% |
| PSC-027 | PSC-005 | physical_sciences | imperfect_grammar | medium | What formula tells where a mirror image gonna form? | 14,15 / 24,25 | 100.0% | 100.0% |
| PSC-028 | PSC-007 | physical_sciences | short_underspecified | medium | Do stronger lenses have a shorter focus? | 96 / 106 | 100.0% | 100.0% |
| PSC-029 | PSC-011 | physical_sciences | cause_effect | medium | Why do short-sighted people need a concave lens? | 92,93 / 102,103 | 100.0% | 100.0% |
| PSC-030 | PSC-012 | physical_sciences | short_underspecified | hard | Why doesn't one broken branch stop the rest of a parallel circuit? | 205,208 / 215,218 | 100.0% | 100.0% |
| PSC-031 | PSC-013 | physical_sciences | misconception | hard | Can I just use positive distances in the mirror formula? | 18 / 28 | 100.0% | 100.0% |
| PSC-032 | PSC-016 | physical_sciences | imperfect_grammar | medium | Why equation need same number of each atom on both sides? | 27,29 / 37,39 | 100.0% | 100.0% |
| PSC-033 | PSC-017 | physical_sciences | colloquial | medium | If something has pH 3, 7, or 10, what kind of liquid is each? | 47 / 57 | 100.0% | 100.0% |
| PSC-034 | PSC-018 | physical_sciences | misconception | hard | When atoms share electrons, are they actually giving them away? | 174 / 184 | 100.0% | 100.0% |

## Ambiguity and accepted evidence

- `BIO-031` intentionally corrects an overgeneralization; its inherited two-page mitosis/meiosis evidence is required to distinguish the cell-division types.
- `PSC-030` is narrower than its parent. TB 205 / PDF 215 is a sufficient minimal set because it states that parallel branches provide separate current paths; the inherited TB 205 and 208 evidence remains accepted.
- `BIO-032` uses only primary TB 231–232 evidence. Parent alternatives TB 230 and 243 were not retained: TB 230 asks related questions without answering them, while TB 243 contains only generic conservation material.

## Validation summary

All 20 mappings were verified against processed page metadata and the original source PDF text layer. Every inherited answer span achieved at least 50% multiset-token coverage in both representations.


## Retrieval evaluation

### Page retrieval: canonical versus natural-student

| Slice | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|---:|
| canonical | BM25 | 41 | 36.6% | 56.1% | 68.3% | 0.491 |
| canonical | BGE-small dense | 41 | 43.9% | 68.3% | 73.2% | 0.589 |
| canonical | Hybrid RRF | 41 | 46.3% | 63.4% | 73.2% | 0.585 |
| natural_student | BM25 | 20 | 20.0% | 40.0% | 50.0% | 0.360 |
| natural_student | BGE-small dense | 20 | 25.0% | 60.0% | 65.0% | 0.441 |
| natural_student | Hybrid RRF | 20 | 20.0% | 50.0% | 65.0% | 0.399 |

### Natural-student results across retrieval units

| Unit / approach | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |
|---|---|---:|---:|---:|---:|---:|
| Page | BM25 | 20 | 20.0% | 40.0% | 50.0% | 0.360 |
| Page | BGE-small dense | 20 | 25.0% | 60.0% | 65.0% | 0.441 |
| Page | Hybrid RRF | 20 | 20.0% | 50.0% | 65.0% | 0.399 |
| Fixed chunks | BM25 | 20 | 15.0% | 35.0% | 55.0% | 0.335 |
| Fixed chunks | BGE-small dense | 20 | 15.0% | 45.0% | 55.0% | 0.342 |
| Fixed chunks | Hybrid RRF | 20 | 20.0% | 45.0% | 65.0% | 0.390 |
| Structured chunks | BM25 | 20 | 15.0% | 30.0% | 45.0% | 0.305 |
| Structured chunks | BGE-small dense | 20 | 15.0% | 40.0% | 50.0% | 0.322 |
| Structured chunks | Hybrid RRF | 20 | 10.0% | 50.0% | 55.0% | 0.312 |
| Strict Cascade | BM25 | 20 | 10.0% | 15.0% | 20.0% | 0.140 |
| Strict Cascade | BGE-small dense | 20 | 15.0% | 45.0% | 55.0% | 0.336 |
| Strict Cascade | Hybrid RRF | 20 | 25.0% | 40.0% | 55.0% | 0.365 |
| Soft Fusion | BM25 | 20 | 25.0% | 45.0% | 55.0% | 0.375 |
| Soft Fusion | BGE-small dense | 20 | 15.0% | 50.0% | 55.0% | 0.357 |
| Soft Fusion | Hybrid RRF | 20 | 35.0% | 50.0% | 60.0% | 0.463 |

### Natural-student page results by style

| Query style | Retriever | N | Hit@5 | MRR |
|---|---|---:|---:|---:|
| cause_effect | BM25 | 3 | 33.3% | 0.229 |
| cause_effect | BGE-small dense | 3 | 66.7% | 0.674 |
| cause_effect | Hybrid RRF | 3 | 66.7% | 0.508 |
| colloquial | BM25 | 4 | 50.0% | 0.373 |
| colloquial | BGE-small dense | 4 | 75.0% | 0.433 |
| colloquial | Hybrid RRF | 4 | 75.0% | 0.380 |
| different_vocabulary | BM25 | 3 | 33.3% | 0.407 |
| different_vocabulary | BGE-small dense | 3 | 66.7% | 0.521 |
| different_vocabulary | Hybrid RRF | 3 | 33.3% | 0.426 |
| imperfect_grammar | BM25 | 3 | 66.7% | 0.259 |
| imperfect_grammar | BGE-small dense | 3 | 66.7% | 0.500 |
| imperfect_grammar | Hybrid RRF | 3 | 66.7% | 0.500 |
| misconception | BM25 | 4 | 75.0% | 0.453 |
| misconception | BGE-small dense | 4 | 50.0% | 0.272 |
| misconception | Hybrid RRF | 4 | 75.0% | 0.375 |
| short_underspecified | BM25 | 3 | 33.3% | 0.402 |
| short_underspecified | BGE-small dense | 3 | 66.7% | 0.302 |
| short_underspecified | Hybrid RRF | 3 | 66.7% | 0.218 |

### Natural-student page top-five misses

| Question | Retriever | Accepted rank | Automatic category |
|---|---|---:|---|
| BIO-023 | BM25 | 7 | relevant page ranked below top 5 |
| BIO-023 | BGE-small dense | 16 | relevant page ranked below top 5 |
| BIO-023 | Hybrid RRF | 9 | relevant page ranked below top 5 |
| BIO-026 | BM25 | 6 | multi page evidence dilution |
| BIO-027 | BM25 | 10 | multi page evidence dilution |
| BIO-029 | BM25 | 13 | relevant page ranked below top 5 |
| BIO-029 | Hybrid RRF | 6 | relevant page ranked below top 5 |
| BIO-032 | BM25 | 6 | multi page evidence dilution |
| PSC-025 | BM25 | 47 | formula or symbol extraction mismatch |
| PSC-025 | BGE-small dense | 43 | formula or symbol extraction mismatch |
| PSC-025 | Hybrid RRF | 42 | formula or symbol extraction mismatch |
| PSC-026 | BM25 | 7 | relevant page ranked below top 5 |
| PSC-026 | BGE-small dense | 30 | relevant page ranked below top 5 |
| PSC-026 | Hybrid RRF | 14 | relevant page ranked below top 5 |
| PSC-027 | BM25 | 9 | formula or symbol extraction mismatch |
| PSC-027 | BGE-small dense | 6 | formula or symbol extraction mismatch |
| PSC-027 | Hybrid RRF | 6 | formula or symbol extraction mismatch |
| PSC-028 | BM25 | 25 | formula or symbol extraction mismatch |
| PSC-028 | BGE-small dense | 14 | formula or symbol extraction mismatch |
| PSC-028 | Hybrid RRF | 14 | formula or symbol extraction mismatch |
| PSC-031 | BM25 | 9 | formula or symbol extraction mismatch |
| PSC-031 | BGE-small dense | 9 | formula or symbol extraction mismatch |
| PSC-031 | Hybrid RRF | 6 | formula or symbol extraction mismatch |
| PSC-034 | BGE-small dense | 7 | multi page evidence dilution |

The natural-student slice is harder than the canonical slice for every page retriever. Page dense and page Hybrid tie at 65.0% Hit@5; fixed-chunk Hybrid also reaches 65.0%, while soft-fusion Hybrid leads hierarchical variants at 60.0%. The largest cross-method page failures are `PSC-025`, `PSC-026`, and `PSC-028`; their natural wording removes or changes the textbook's strongest lexical anchors.
