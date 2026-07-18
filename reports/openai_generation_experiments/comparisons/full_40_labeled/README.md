# Full 40-question local-Qwen versus GPT-4o comparison

Open `local_vs_gpt4o_labeled_comparison.html` for the requested direct review.
Nothing is anonymized in its default view. Every question shows four answers
in this fixed order:

1. Local Qwen — Gold evidence
2. GPT-4o API — Gold evidence
3. Local Qwen — Retrieved evidence
4. GPT-4o API — Retrieved evidence

The gold pair isolates generator behavior when both models receive reviewed
benchmark evidence. The retrieved pair measures the end-to-end generation
condition when both models receive the same frozen top-5 retrieved context.
Use these like-for-like pairs when noting correctness, completeness,
grounding, clarity, citation quality, or retrieval sensitivity.

The page is self-contained and works offline. Automatic screens are visible
for navigation, but their token-overlap scores are not a substitute for human
scientific review. The optional Blind mode checkbox can hide evidence-mode
badges and automatic screens; it does not replace the explicit model names in
this labeled artifact.

## Coverage and configuration

| Item | Result |
|---|---:|
| Benchmark questions | 40 |
| Biology / Physical Sciences | 20 / 20 |
| Answers displayed | 160 |
| Completed answers per source | 40 / 40 |
| GPT-4o maximum output tokens | 768 |
| Local Qwen historical maximum output tokens | 384 |

Both generators use prompt strategy P1. Gold runs use
`gold_separate_full`; retrieved runs use
`retrieved_top5_page_order_compact`. Retrieval, evidence ordering, benchmark,
and evaluation logic are unchanged between local and online generation.

## Artifact map

- `local_vs_gpt4o_labeled_comparison.html`: explicitly labeled review page.
- `labeled_comparison_packet.jsonl`: structured source for that page.
- `comparison_metrics.json`: machine-readable completion and automatic metrics.
- `comparison_report.md`: concise metric table.
- `blinded_human_review_packet.jsonl` and `blinded_answer_key.json`: optional
  unbiased-review equivalents retained for traceability.

Regenerate the HTML without making API calls:

```powershell
$env:PYTHONPATH = "src"
temp\python-x64\python.exe scripts\build_review_packet_view.py `
  --input reports\openai_generation_experiments\comparisons\full_40_labeled\labeled_comparison_packet.jsonl `
  --output reports\openai_generation_experiments\comparisons\full_40_labeled\local_vs_gpt4o_labeled_comparison.html `
  --revealed
```
