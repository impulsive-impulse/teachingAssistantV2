# Blinded generation-answer review

This folder contains the human-readable, offline view of the finalist review
packet. Open `blinded_human_review_packet.html` in a browser. It starts in blind
mode, which hides evaluation mode and automatic scores; leave that enabled
while making the initial scientific and grounding judgment.

The HTML is deliberately read-only. Record decisions in a separate reviewed
JSONL copy rather than changing the generated source packet. Do not open
`../blinded_answer_key.json` until every answer has been judged.

Regenerate the view from the canonical JSONL packet:

```powershell
temp\python-x64\python.exe scripts\build_review_packet_view.py `
  --input reports\generation_experiments\blinded_human_review_packet.jsonl `
  --output reports\generation_experiments\review\blinded_human_review_packet.html
```

The page is self-contained and makes no network requests. For each of the 24
holdout questions it shows all four anonymous finalist answers, rubric points,
citations, supplied evidence, and—when blind mode is disabled—the deterministic
automatic screen.
