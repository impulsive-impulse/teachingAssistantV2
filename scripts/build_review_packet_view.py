"""Render a blinded or explicitly labeled JSONL packet as self-contained HTML.

Usage:
    python scripts/build_review_packet_view.py \
        --input reports/generation_experiments/blinded_human_review_packet.jsonl \
        --output reports/generation_experiments/review/blinded_human_review_packet.html
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def esc(value: Any) -> str:
    """HTML-escape any value (None -> empty string)."""
    if value is None:
        return ""
    return html.escape(str(value))


def pct(value: Any) -> str:
    """Format a decimal metric as a whole-number percentage for quick scanning."""
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return esc(value)


def bool_badge(value: Any, true_label: str = "yes", false_label: str = "no") -> str:
    """Render a boolean or unknown value as an accessible status badge."""
    if value is True:
        return f'<span class="badge good">{true_label}</span>'
    if value is False:
        return f'<span class="badge bad">{false_label}</span>'
    return f'<span class="badge neutral">{esc(value)}</span>'


def render_points(title: str, points: list[str], css_class: str) -> str:
    """Render one rubric-point group, omitting empty optional groups."""
    if not points:
        return ""
    items = "\n".join(f"<li>{esc(p)}</li>" for p in points)
    return (
        f'<div class="pointset {css_class}">'
        f"<h4>{esc(title)}</h4><ul>{items}</ul></div>"
    )


def render_evidence(evidence: list[dict[str, Any]]) -> str:
    """Render supplied evidence in collapsed blocks with page and rank metadata."""
    if not evidence:
        return '<p class="muted">No supplied evidence.</p>'
    blocks = []
    for ev in evidence:
        eid = esc(ev.get("evidence_id"))
        source = esc(ev.get("source_file"))
        # gold evidence uses pdf_page/textbook_page; retrieved may add ranges + rank.
        pdf_page = ev.get("pdf_page")
        textbook_page = ev.get("textbook_page")
        pages_bits = []
        if pdf_page is not None:
            pages_bits.append(f"pdf p.{esc(pdf_page)}")
        if textbook_page is not None:
            pages_bits.append(f"book p.{esc(textbook_page)}")
        if ev.get("retrieval_rank") is not None:
            pages_bits.append(f"rank {esc(ev.get('retrieval_rank'))}")
        if ev.get("source_chunk_id"):
            pages_bits.append(f"chunk {esc(ev.get('source_chunk_id'))}")
        meta = " &middot; ".join(pages_bits)
        text = esc(ev.get("text"))
        blocks.append(
            f'<details class="evidence">'
            f'<summary><span class="eid">{eid}</span> '
            f'<span class="muted">{source} &middot; {meta}</span></summary>'
            f'<pre class="evtext">{text}</pre>'
            f"</details>"
        )
    return "\n".join(blocks)


def render_citations(citations: list[dict[str, Any]]) -> str:
    """Render model citations as compact evidence/page chips."""
    if not citations:
        return '<span class="muted">none</span>'
    chips = []
    for c in citations:
        eid = esc(c.get("evidence_id"))
        pdf_page = esc(c.get("pdf_page"))
        book_page = esc(c.get("textbook_page"))
        chips.append(f'<span class="chip">{eid} (pdf {pdf_page} / book {book_page})</span>')
    return "".join(chips)


def render_screen(screen: dict[str, Any]) -> str:
    """Render automatic metrics separately so blind mode can hide them."""
    if not screen:
        return ""
    rows = []
    for detail in screen.get("required_point_details", []):
        matched = detail.get("matched")
        row_class = "match" if matched else "nomatch"
        rows.append(
            f'<tr class="{row_class}">'
            f"<td>{esc(detail.get('point'))}</td>"
            f"<td class='num'>{esc(detail.get('token_recall'))}</td>"
            f"<td class='center'>{bool_badge(matched, 'matched', 'missed')}</td>"
            f"</tr>"
        )
    points_table = (
        "<table class='screen-table'>"
        "<thead><tr><th>Required point</th><th>Token recall</th><th>Matched</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )

    unsupported = screen.get("unsupported_claims") or []
    unsupported_html = (
        "".join(f"<li>{esc(u)}</li>" for u in unsupported)
        if unsupported
        else '<li class="muted">none</li>'
    )

    metrics = (
        '<div class="metrics">'
        f'<span class="metric"><label>Required coverage</label>{pct(screen.get("required_point_coverage"))}</span>'
        f'<span class="metric"><label>Citation validity</label>{pct(screen.get("citation_validity"))}</span>'
        f'<span class="metric"><label>Unsupported rate</label>{pct(screen.get("unsupported_claim_rate"))}</span>'
        f'<span class="metric"><label>Structured valid</label>{bool_badge(screen.get("structured_output_valid"))}</span>'
        f'<span class="metric"><label>False "insufficient"</label>{bool_badge(screen.get("false_insufficient_evidence"), "yes", "no")}</span>'
        f'<span class="metric"><label>Word count</label>{esc(screen.get("answer_word_count"))}</span>'
        "</div>"
    )

    return (
        '<div class="screen blind-hide">'
        "<h4>Automatic screen</h4>"
        f"{metrics}"
        f"{points_table}"
        f'<div class="unsupported"><label>Unsupported claims flagged:</label>'
        f"<ul>{unsupported_html}</ul></div>"
        "</div>"
    )


def render_answer(ans: dict[str, Any]) -> str:
    """Render one answer label, its citations, metrics, and supplied evidence."""
    label = esc(ans.get("label"))
    mode = esc(ans.get("evaluation_mode"))
    mode_badge = (
        f'<span class="badge mode blind-hide mode-{mode}">{mode}</span>' if mode else ""
    )
    answer_text = esc(ans.get("answer"))
    citations = render_citations(ans.get("citations", []))
    evidence = render_evidence(ans.get("supplied_evidence", []))
    screen = render_screen(ans.get("automatic_screen", {}))
    reviewer_decision = ans.get("reviewer_decision")
    decision_html = (
        f'<span class="badge neutral">{esc(reviewer_decision)}</span>'
        if reviewer_decision
        else '<span class="muted">pending</span>'
    )
    notes = esc(ans.get("reviewer_notes")) or '<span class="muted">—</span>'

    return f"""
    <div class="answer">
      <div class="answer-head">
        <h3>{label}</h3>{mode_badge}
      </div>
      <div class="answer-body">
        <p class="answer-text">{answer_text}</p>
        <div class="answer-meta">
          <div><label>Citations</label> {citations}</div>
          <div><label>Reviewer decision</label> {decision_html}</div>
          <div><label>Reviewer notes</label> {notes}</div>
        </div>
        {screen}
        <details class="evidence-wrap">
          <summary>Supplied evidence ({len(ans.get('supplied_evidence', []))})</summary>
          {evidence}
        </details>
      </div>
    </div>
    """


def render_question(idx: int, rec: dict[str, Any]) -> str:
    """Render a complete review card for one question and all finalist answers."""
    qid = esc(rec.get("question_id"))
    question = esc(rec.get("question"))
    required = render_points(
        "Required answer points", rec.get("required_answer_points", []), "required"
    )
    optional = render_points(
        "Optional answer points", rec.get("optional_answer_points", []), "optional"
    )
    prohibited = render_points(
        "Prohibited / unsupported claims",
        rec.get("prohibited_or_unsupported_claims", []),
        "prohibited",
    )
    answers = "\n".join(render_answer(a) for a in rec.get("answers", []))

    return f"""
    <section class="question" id="q-{idx}">
      <div class="question-head">
        <span class="qnum">{idx}</span>
        <span class="qid">{qid}</span>
      </div>
      <h2 class="qtext">{question}</h2>
      <div class="pointsets">{required}{optional}{prohibited}</div>
      <div class="answers">{answers}</div>
    </section>
    """


CSS = """
:root {
  --bg: #0f1115; --panel: #171a21; --panel2: #1e222b; --line: #2a2f3a;
  --text: #e6e8ec; --muted: #8b93a1; --accent: #6ea8fe;
  --good: #2ea043; --bad: #d64545; --warn: #d9a441;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.55 -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
header.top { position: sticky; top: 0; z-index: 5; background: #0b0d11ee;
  backdrop-filter: blur(6px); border-bottom: 1px solid var(--line);
  padding: 14px 24px; display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
header.top h1 { font-size: 17px; margin: 0; font-weight: 650; }
header.top .sub { color: var(--muted); font-size: 13px; }
.toolbar { margin-left: auto; display: flex; gap: 14px; align-items: center; }
.toolbar label { font-size: 13px; color: var(--muted); cursor: pointer; user-select: none; }
main { max-width: 1080px; margin: 0 auto; padding: 24px; }
.question { background: var(--panel); border: 1px solid var(--line);
  border-radius: 12px; padding: 20px 22px; margin: 0 0 26px; }
.question-head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.qnum { background: var(--accent); color: #08111f; font-weight: 700; font-size: 12px;
  width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; }
.qid { color: var(--muted); font-size: 12px; letter-spacing: .5px; font-weight: 600; }
.qtext { font-size: 18px; margin: 4px 0 16px; }
.pointsets { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px; margin-bottom: 20px; }
.pointset { border: 1px solid var(--line); border-radius: 9px; padding: 10px 14px;
  background: var(--panel2); }
.pointset h4 { margin: 0 0 6px; font-size: 12.5px; text-transform: uppercase;
  letter-spacing: .4px; }
.pointset ul { margin: 0; padding-left: 18px; }
.pointset li { margin: 3px 0; font-size: 13.5px; }
.pointset.required h4 { color: #7ee2a8; }
.pointset.optional h4 { color: #9db4ff; }
.pointset.prohibited h4 { color: #ff9b9b; }
.answer { border: 1px solid var(--line); border-radius: 10px; margin: 14px 0;
  overflow: hidden; background: #14171e; }
.answer-head { display: flex; align-items: center; gap: 10px;
  padding: 10px 16px; background: #191d25; border-bottom: 1px solid var(--line); }
.answer-head h3 { margin: 0; font-size: 15px; }
.answer-body { padding: 14px 16px; }
.answer-text { margin: 0 0 14px; white-space: pre-wrap; }
.answer-meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px,1fr));
  gap: 8px 20px; margin-bottom: 14px; font-size: 13.5px; }
.answer-meta label, .metric label, .unsupported label { color: var(--muted);
  font-size: 11.5px; text-transform: uppercase; letter-spacing: .4px;
  display: block; margin-bottom: 2px; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 20px; font-weight: 600;
  border: 1px solid var(--line); }
.badge.good { color: #86efac; border-color: #1f5132; background: #12251a; }
.badge.bad { color: #fca5a5; border-color: #5b2020; background: #2a1414; }
.badge.neutral { color: var(--muted); }
.badge.mode { text-transform: uppercase; letter-spacing: .5px; }
.badge.mode-gold { color: #ffd479; border-color: #6b551d; background: #251f10; }
.badge.mode-retrieved { color: #8fd0ff; border-color: #1d4a6b; background: #101f28; }
.chip { display: inline-block; background: var(--panel2); border: 1px solid var(--line);
  border-radius: 6px; padding: 1px 7px; margin: 0 5px 5px 0; font-size: 12px; }
.screen { border: 1px solid var(--line); border-radius: 9px; padding: 12px 14px;
  margin: 6px 0 14px; background: var(--panel2); }
.screen h4 { margin: 0 0 10px; font-size: 12.5px; text-transform: uppercase;
  letter-spacing: .4px; color: var(--accent); }
.metrics { display: flex; flex-wrap: wrap; gap: 8px 22px; margin-bottom: 12px; }
.metric { font-size: 14px; font-weight: 600; }
.screen-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.screen-table th, .screen-table td { text-align: left; padding: 6px 8px;
  border-bottom: 1px solid var(--line); vertical-align: top; }
.screen-table th { color: var(--muted); font-weight: 600; font-size: 11.5px;
  text-transform: uppercase; letter-spacing: .3px; }
.screen-table td.num, .screen-table td.center { white-space: nowrap; }
.screen-table td.center { text-align: center; }
tr.match td:first-child { border-left: 3px solid var(--good); }
tr.nomatch td:first-child { border-left: 3px solid var(--bad); }
.unsupported { margin-top: 10px; }
.unsupported ul { margin: 4px 0 0; padding-left: 18px; font-size: 13px; }
details.evidence-wrap > summary, details.evidence > summary { cursor: pointer;
  padding: 6px 0; color: var(--accent); font-size: 13.5px; }
details.evidence-wrap { border-top: 1px solid var(--line); padding-top: 6px; }
details.evidence { border: 1px solid var(--line); border-radius: 7px;
  padding: 4px 10px; margin: 6px 0; background: #101318; }
details.evidence summary .eid { font-weight: 700; color: #cbd3e1; }
.evtext { white-space: pre-wrap; font-size: 12.5px; color: #c7cdd8;
  background: #0c0e12; border-radius: 6px; padding: 10px; margin: 8px 0 4px;
  max-height: 340px; overflow: auto; }
.muted { color: var(--muted); }
body.blind .blind-hide { display: none !important; }
"""

JS = """
const cb = document.getElementById('blindToggle');
cb.addEventListener('change', () => document.body.classList.toggle('blind', cb.checked));
const ce = document.getElementById('expandToggle');
ce.addEventListener('change', () => {
  document.querySelectorAll('details').forEach(d => d.open = ce.checked);
});
"""


def build_html(records: list[dict[str, Any]], source_name: str, revealed: bool = False) -> str:
    """Build a self-contained offline HTML document from packet records.

    ``revealed`` keeps provider labels, modes, and automatic screens visible
    by default for explicit local-vs-online gap analysis. Historical blinded
    review behavior remains the default.
    """
    sections = "\n".join(render_question(i + 1, rec) for i, rec in enumerate(records))
    total_answers = sum(len(r.get("answers", [])) for r in records)
    body_class = "" if revealed else "blind"
    heading = "Labeled local-vs-online comparison" if revealed else "Blinded human-review packet"
    checked = "" if revealed else " checked"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Review packet &middot; {esc(source_name)}</title>
<style>{CSS}</style>
</head>
<body class="{body_class}">
<header class="top">
  <h1>{heading}</h1>
  <span class="sub">{esc(source_name)} &middot; {len(records)} questions &middot; {total_answers} answers</span>
  <div class="toolbar">
    <label><input type="checkbox" id="blindToggle"{checked} /> Blind mode (hide mode &amp; auto-screen)</label>
    <label><input type="checkbox" id="expandToggle" /> Expand all evidence</label>
  </div>
</header>
<main>
{sections}
</main>
<script>{JS}</script>
</body>
</html>
"""


def main() -> None:
    """Parse JSONL, render the offline review view, and write the requested file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--revealed", action="store_true",
        help="Show explicit labels, evidence mode, and automatic screens by default.",
    )
    args = parser.parse_args()

    records: list[dict[str, Any]] = []
    with args.input.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    html_doc = build_html(records, args.input.name, revealed=args.revealed)
    # Model answers can contain spaces before newlines, and the readable HTML
    # templates contain indented blank lines. Normalize both in the derived
    # artifact so repository whitespace checks remain clean.
    html_doc = "\n".join(line.rstrip() for line in html_doc.splitlines()) + "\n"
    # Keep generated views in their documented report subtree even on a fresh checkout.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {args.output} ({len(records)} questions, {args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
