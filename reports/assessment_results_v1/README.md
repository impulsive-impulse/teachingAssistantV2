# Assessment results v1

These are new, bounded HotpotQA multi-document experiments, not the historical
single-textbook v1 research and not official leaderboard scores.

`development_initial` retains the first complete 15-question/four-arm run.
Exact quote checks rejected frequent punctuation changes and ellipses.
`development_confirmation` retains the same questions after a shared prompt
revision emphasizing literal contiguous quotes. No validator was relaxed.
The initial run used 50 paid attempts; confirmation used 52 diagnostic attempts
from the declared contingency allocation. Both are retained, not selected
winning rows. Known token-based cost estimate: $0.4593725, not an invoice.

The retrieval-only grid selected six documents, three units per source, title
link weight 0.2 and weak dense threshold 0.25. The complete pipeline/code
freeze is `config/assessment_freeze_v1.json`, before final effectiveness is
seen. All subsequent final arms use the same quote prompt/schema, model,
768 output tokens and 1,024 context-token budget.

An accounting flaw discovered during development allowed independent sampling
of an invalid hybrid output for the otherwise identical bypass ablation.
Temperature zero does not guarantee server-level determinism. Final execution
reuses all terminal provider responses within its run, including invalid
claims, so hybrid and its equivalent ablation must have identical predictions.
The earlier independently sampled development outputs remain unchanged.

Raw JSON is losslessly gzip-compressed, with per-row semantic checksums.
Snapshots include original sources, exact source spans, selected evidence,
context and raw provider responses. `run.json` lists every expected question;
`references.json` contains evaluation-only labels, not model input. The runner
rejects missing rows and altered checksums.

```powershell
.\.venv-assessment\Scripts\python.exe scripts\evaluate_assessment.py --cached --output reports\assessment_results_v1\development_confirmation
```

Cached replay needs the prepared public tokenizer and Python dependencies,
but no API key, source dataset download, embedding model or retrieval call.
Do not call cached replay a fresh model evaluation.

**Attribution and rights:** source questions, answers, original Wikipedia
paragraphs and supporting annotations are from Yang et al. (2018), *HotpotQA:
A Dataset for Diverse, Explainable Multi-hop Question Answering*,
https://aclanthology.org/D18-1259/, https://hotpotqa.github.io/.
Dataset and these derived benchmark artifacts are
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
Changes: deterministic selection/splitting/order, source mapping, contexts,
generated predictions and evaluation records. The original scorer is separately
Apache-2.0. No copyrighted demonstration PDF or extracted PDF text is bundled.

## Held-out outcome

All 45 held-out questions and four arms are retained under `final/`.
Complete-document context recall: **97.78% proposed, 88.89% dense, 80.00%
hybrid/ablation**. Paired 95% intervals for proposed gains are +2.22 to +17.78
percentage points over dense and +6.67 to +28.89 over hybrid.
Answer F1 is 64.20%/61.06%/51.02%; the gain over dense is uncertain
(-8.24 to +15.29 points). Proposed invalid output is 26.67%, not hidden.
Hybrid and its equivalent bypass ablation have identical raw predictions.
The additional BM25-only reference reaches 55.56% complete-document recall.

`final_analysis.json` retains paired intervals and measured operations.
The exact preselected source-review packets, opaque card IDs, rubric and all
60 recorded judgments are retained. Ten held-out questions x four arms give
25 supported, 3 partial, 7 invalid and 5 abstained cards; the proposed arm has
7 supported, 1 partial, 1 invalid and 1 abstained. Development includes valid
addresses attached to unsupported dates and incomplete intermediate chains.
These are **assistant source inspections**, not independent human signoff.
Claim-support judgments concern original source units; altered quotations can
still make an otherwise factually supported response invalid.

Final evaluation used **134** new paid attempts; 46 identical logical outputs
reused within that run. Development and diagnostics used 102. Known total
token-based estimate before the reserved fresh rerun: **$1.0855075**. Actual
invoiced dollars are not available. Zero calls are required for report replay.
