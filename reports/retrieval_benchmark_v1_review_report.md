# Retrieval Benchmark v1 — Review Report

Reviewed `retrieval_benchmark_v1_candidates.jsonl` (40 rows) against the extracted page-level text of the original Biology and Physical Sciences PDFs. Output: `retrieval_benchmark_v1_reviewed.jsonl`.

## Method

- Each gold PDF page was checked against its **printed textbook page number** read from the page text (not merely the +9 / +10 offset). All 40 rows' printed page numbers matched their `gold_textbook_pages`, so `page_mapping_verified=true` for every answerable row.

- Every non-empty answer span was located on its gold page(s); chapter/section labels, and dependency flags (visual/formula/table, multi-page/multi-chunk) were checked.

- Negative rows were confirmed unanswerable via full-book keyword scans.

## Summary

- Verified, no change: **32**
- Verified with fixes: **4**
- Negative rows confirmed unanswerable: **4**

## Corrections applied

| Question | Field | Change |
|---|---|---|
| BIO-008 | gold_section_title | `2. Renal tubule` → `4.3 Mechanism of urine formation` |
| BIO-018 | gold_textbook_pages / gold_pdf_pages | `[231,243]/[240,252]` → `[231,232]/[240,241]` (243 was a summary page; 232 covers groundwater recharge) |
| PSC-007 | gold_section_title | `5.3.3 Presbyopia` → `5.3.4 Power of lens` |
| PSC-014 | gold_section_title | noisy running header → `Equivalent resistance of a parallel connection` |

## Notes on dependency flags

- Table rows BIO-013 and BIO-016 correctly carry `table_dependency=true`; their spans sit inside tables and appear interleaved with the page watermark in raw text.

- BIO-017's second evidence page (pdf 123) is Table-2 (Endocrine glands); it is corroborating tabular context, so `evidence_minimal=false`.

- Physical Sciences formula/visual flags (PSC-005/006/008/013/014 formula; PSC-009/010/011/012 visual) were reviewed and retained.

## Per-row review notes

| Question | Status | Confidence | Notes |
|---|---|---|---|
| BIO-001 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-002 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-003 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-004 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-005 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-006 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-007 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-008 | verified_with_fixes | high | Section title corrected from the noisy header '2. Renal tubule' to '4.3 Mechanism of urine formation', which is the section that lists the four stages and is quoted in the answer span. Pages 84-85 (pdf 93-94) both required and confirmed. |
| BIO-009 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-010 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-011 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-012 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-013 | verified | high | Answer span is drawn from Table-3 (Major plant hormones and their action); table_dependency=true is correct. Span text is present on the page but interleaved with the page watermark in the raw extraction. |
| BIO-014 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-015 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| BIO-016 | verified | high | Comparison relies on Table-1 (Mitosis) plus the meiosis text on pdf 153-154; table_dependency=true confirmed. Span present but interleaved with watermark text in raw extraction. |
| BIO-017 | verified | high | Multi-page synthesis: pdf 109 (nervous coordination intro) + pdf 123 which is Table-2 Endocrine glands (hormonal control). Evidence is corroborating rather than a single minimal span; pdf 123 is tabular. Labels retained. |
| BIO-018 | verified_with_fixes | medium | Original second gold page 243 (pdf 252) is a chapter-summary/questions page that only mentions 'water harvesting' in passing. Replaced with page 232 (pdf 241), which directly covers groundwater recharge structures continuing the Kothapally case study on page 231. Page 230 (pdf 239) is a strong alternative. |
| BIO-019 | confirmed_unanswerable | high | Confirmed genuinely not answerable: no incidence/epidemiology statistics for Telangana kidney disease appear anywhere in the Biology book (keyword scan for 'incidence' returned nothing). not_answerable label correct. |
| BIO-020 | confirmed_unanswerable | high | Confirmed weak/unsafe evidence: the excretion chapter describes urination-related conditions but a single symptom cannot support a patient diagnosis. weak_evidence label correct. |
| PSC-001 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-002 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-003 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-004 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-005 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-006 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-007 | verified_with_fixes | high | Section title corrected from '5.3.3 Presbyopia' to '5.3.4 Power of lens', the section that defines lens power and its relation to focal length as quoted in the span. |
| PSC-008 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-009 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-010 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-011 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-012 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-013 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-014 | verified_with_fixes | high | Section title corrected from the noisy running header to 'Equivalent resistance of a parallel connection', the sub-section that sets up the three-resistor parallel equation quoted in the span. |
| PSC-015 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-016 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-017 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-018 | verified | high | Printed textbook page number on the gold PDF page matches gold_textbook_pages; chapter, section and answer span verified against extracted page text. |
| PSC-019 | confirmed_unanswerable | high | Confirmed genuinely not answerable: the book defines kWh but contains no utility tariff (keyword scan for 'tariff' returned nothing). not_answerable label correct. |
| PSC-020 | confirmed_unanswerable | high | Confirmed weak evidence: pH and indicators are explained, but no observation/measurement is supplied for the unknown sample, so an exact pH is unrecoverable. weak_evidence label correct. |

## Post-baseline review addendum — 2026-07-13

The canonical `retrieval_benchmark_v1.jsonl` now contains **46 rows**: 22
Biology and 24 Physical Sciences questions. Of these, 41 are answerable and 5
are confirmed negative or weak-evidence questions. The original candidates and
reviewed snapshot remain the historical 40-row source set.

Two spans flagged by hierarchical automatic gold mapping were manually checked:

| Question | Review outcome |
|---|---|
| BIO-003 | Narrowed to the complete minimal nephron definition on textbook page 83 / PDF 92. Removed unrelated text from the following nephron-structure section. |
| PSC-007 | Moved gold evidence from textbook page 95 / PDF 105 to the actual formula on textbook page 96 / PDF 106 and retained section 5.3.4. |

Six qualitative post-baseline queries were added as conversational retrieval
stress cases:

| Question | Status | Evidence |
|---|---|---|
| BIO-021 — How do plants eat? | verified | Autotrophic Nutrition, textbook 1 / PDF 10 |
| BIO-022 — How do green plants feed itself without eating anything? | verified | Photosynthesis, textbook 2 / PDF 11 |
| PSC-021 — how do atomic relationship happen? | verified, medium confidence | Bond formation, textbook 164 / PDF 174; ambiguity retained deliberately |
| PSC-022 — Why does pencil look bent when placed in water | confirmed weak evidence | Related refraction material exists, but no self-contained passage directly explains the stated phenomenon |
| PSC-023 — Why does a car mirror make vehicles behind us look smaller | verified | Convex-mirror diminished virtual image, textbook 13 / PDF 23 |
| PSC-024 — Two chemically opposite solutions cancel each other | verified | Neutralization, textbook 40 / PDF 50 |

All seven answerable corrected/added rows map to one hierarchy paragraph with
100% contiguous normalized answer-span coverage. PSC-022 remains unscored as a
negative. Page, chunk, and hierarchical evaluations were regenerated after the
update.
