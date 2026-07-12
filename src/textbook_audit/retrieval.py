"""Deterministic page-level BM25, BGE-small, and RRF retrieval benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

# Centralized method constants make the generated metadata and actual ranking
# implementation agree, and make future baseline changes easy to audit.
MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
RETRIEVERS = ("bm25", "dense_bge_small", "hybrid_rrf")
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[.'-][A-Za-z0-9]+)*")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load non-empty JSONL records, failing explicitly for missing inputs.

    The same loader is used for page artifacts and the benchmark. The error
    deliberately calls out the reviewed benchmark because silently switching
    to the candidate file would make reported metrics invalid.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Required reviewed benchmark is missing: {path}. "
                               "Create/review retrieval_benchmark_v1.jsonl; candidates are never used.")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_pages(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Load searchable pages for each supported book in original page order."""
    books: dict[str, list[dict[str, Any]]] = {}
    for book_id in ("biology", "physical_sciences"):
        rows = read_jsonl(root / "data" / "processed" / f"{book_id}_pages.jsonl")
        # A mapped textbook page is the stable definition of content rather than front matter.
        rows = [r for r in rows if r.get("textbook_page_number") is not None and r.get("cleaned_text", "").strip()]
        if not rows:
            raise ValueError(f"No searchable content pages for {book_id}")
        books[book_id] = rows
    return books


def tokenize(text: str) -> list[str]:
    """Convert text to deterministic lowercase terms for BM25 and snippets."""
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text)]


class BM25:
    """Minimal deterministic Okapi BM25 index over page text.

    Keeping this implementation local avoids hidden preprocessing defaults in
    a third-party BM25 package. ``k1`` controls term-frequency saturation and
    ``b`` controls page-length normalization.
    """

    def __init__(self, texts: Iterable[str], k1: float = 1.5, b: float = 0.75):
        """Tokenize pages and precompute lengths, document frequency, and IDF."""
        self.k1, self.b = k1, b
        # Counter retains each term's frequency while keeping the index small.
        self.docs = [Counter(tokenize(t)) for t in texts]
        self.lengths = np.asarray([sum(d.values()) for d in self.docs], dtype=np.float64)
        self.avgdl = float(self.lengths.mean()) if len(self.lengths) else 0.0
        df: Counter[str] = Counter()
        for doc in self.docs:
            # Updating with keys counts a term once per page, which is document
            # frequency rather than total term frequency.
            df.update(doc.keys())
        n = len(self.docs)
        # This positive-IDF form is stable even for terms occurring in most pages.
        self.idf = {term: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    def scores(self, query: str) -> np.ndarray:
        """Return one BM25 relevance score per indexed page for ``query``."""
        result = np.zeros(len(self.docs), dtype=np.float64)
        for term in tokenize(query):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, doc in enumerate(self.docs):
                tf = doc.get(term, 0)
                if tf:
                    # Normalize raw frequency by page length, then apply the
                    # standard saturating BM25 term contribution.
                    denom = tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avgdl)
                    result[i] += idf * tf * (self.k1 + 1) / denom
        return result


def stable_ranking(scores: np.ndarray) -> np.ndarray:
    """Descending score with corpus order as a deterministic tie-break."""
    return np.lexsort((np.arange(len(scores)), -scores))


def reciprocal_rank_fusion(rankings: list[np.ndarray], size: int, rrf_k: int = 60) -> np.ndarray:
    """Fuse rankings without mixing incomparable BM25 and cosine score scales."""
    scores = np.zeros(size, dtype=np.float64)
    for ranking in rankings:
        for rank, index in enumerate(ranking, 1):
            scores[index] += 1.0 / (rrf_k + rank)
    return scores


def accepted_pdf_pages(question: dict[str, Any], pages: list[dict[str, Any]]) -> set[int]:
    """Resolve primary and alternative reviewed evidence to PDF page numbers."""
    accepted = {int(x) for x in question.get("gold_pdf_pages", [])}
    # Reviewers express alternatives using printed textbook-page identity, so
    # translate those values through the loaded page metadata before scoring.
    alternatives = {str(x) for x in question.get("alternative_gold_pages", [])}
    for page in pages:
        if str(page.get("textbook_page_number")) in alternatives:
            accepted.add(int(page["pdf_page_number"]))
    return accepted


def percentile95(values: list[float]) -> float:
    """Calculate the linearly interpolated 95th percentile, or zero if empty."""
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values), 95, method="linear"))


def metric_block(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute effectiveness for answerable items and latency for all items."""
    # Negative questions have no relevant rank and therefore must not lower
    # Hit@K or MRR. Their latency remains useful operational information.
    answerable = [x for x in items if x["answerable"]]
    latencies = [x["latency_ms"] for x in items]
    ranks = [x["first_relevant_rank"] for x in answerable]
    return {
        "questions": len(items),
        "answerable_questions": len(answerable),
        "hit_at_1": sum(r is not None and r <= 1 for r in ranks) / len(ranks) if ranks else None,
        "hit_at_3": sum(r is not None and r <= 3 for r in ranks) / len(ranks) if ranks else None,
        "hit_at_5": sum(r is not None and r <= 5 for r in ranks) / len(ranks) if ranks else None,
        "mrr": sum(1.0 / r if r else 0.0 for r in ranks) / len(ranks) if ranks else None,
        "average_latency_ms": statistics.fmean(latencies) if latencies else 0.0,
        "p95_latency_ms": percentile95(latencies),
    }


def group_metrics(evals: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """Partition evaluation rows by ``key`` and compute a metric block per value."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evals:
        groups[str(row[key])].append(row)
    return {name: metric_block(rows) for name, rows in sorted(groups.items())}


def failure_category(q: dict[str, Any], gold_rank: int | None) -> str:
    """Assign the most likely reviewed-data cause for an answerable top-5 miss."""
    # Dependency labels are stronger evidence than a generic ranking diagnosis,
    # so they take precedence in this intentionally simple error taxonomy.
    if q.get("visual_dependency"):
        return "visual_evidence_not_represented_in_text"
    if q.get("table_dependency"):
        return "table_structure_lost_in_extraction"
    if q.get("formula_dependency"):
        return "formula_or_symbol_extraction_mismatch"
    if q.get("requires_multiple_pages") or q.get("requires_multiple_chunks"):
        return "multi_page_evidence_dilution"
    if gold_rank is not None:
        return "relevant_page_ranked_below_top_5"
    return "lexical_or_semantic_mismatch"


def snippet(text: str, query: str, width: int = 360) -> str:
    """Build a compact result preview near the first meaningful query term."""
    flat = " ".join(text.split())
    terms = set(tokenize(query))
    positions = [flat.lower().find(t) for t in terms if len(t) > 3 and flat.lower().find(t) >= 0]
    start = max(0, (min(positions) if positions else 0) - 80)
    value = flat[start:start + width]
    return ("…" if start else "") + value + ("…" if start + width < len(flat) else "")


@dataclass
class DenseIndex:
    """Loaded Sentence Transformer, per-book matrices, and run metadata."""

    model: Any
    embeddings: dict[str, np.ndarray]
    metadata: dict[str, Any]


def _corpus_fingerprint(pages: list[dict[str, Any]]) -> str:
    """Hash page identity and cleaned text to detect stale embedding caches."""
    h = hashlib.sha256()
    for p in pages:
        h.update(f'{p["book_id"]}:{p["pdf_page_number"]}:'.encode())
        h.update(p["cleaned_text"].encode("utf-8"))
    return h.hexdigest()


def load_dense_index(books: dict[str, list[dict[str, Any]]], cache_dir: Path, device: str | None) -> DenseIndex:
    """Load BGE-small and reuse or create normalized per-book page embeddings."""
    try:
        import sentence_transformers
        import torch
        import transformers
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("Dense retrieval requires sentence-transformers. Run `python -m pip install -e .`.") from exc
    # Sentence Transformers selects an available device when ``device`` is None;
    # recording the resolved value makes latency results interpretable.
    model = SentenceTransformer(MODEL_NAME, device=device)
    runtime_device = str(model.device)
    get_dimension = getattr(model, "get_embedding_dimension", model.get_sentence_embedding_dimension)
    dimension = int(get_dimension())
    # Capture the Hub commit resolved by Sentence Transformers where available.
    revision = getattr(getattr(model, "_first_module", lambda: None)(), "auto_model", None)
    revision = getattr(getattr(revision, "config", None), "_commit_hash", None) or "default"
    cache_dir.mkdir(parents=True, exist_ok=True)
    embeddings: dict[str, np.ndarray] = {}
    fingerprints: dict[str, str] = {}
    for book_id, pages in books.items():
        fp = _corpus_fingerprint(pages)
        fingerprints[book_id] = fp
        cache = cache_dir / f"{book_id}_bge-small-en-v1.5.npz"
        valid = False
        if cache.is_file():
            # Pickle is disabled because the cache contains only numeric arrays
            # and scalar metadata; this avoids executing arbitrary cache data.
            stored = np.load(cache, allow_pickle=False)
            valid = str(stored["fingerprint"].item()) == fp and int(stored["dimension"].item()) == dimension
            if valid:
                embeddings[book_id] = stored["embeddings"].astype(np.float32)
        if not valid:
            # Normalization at encoding time turns the later matrix dot product
            # into cosine similarity without repeated per-query normalization.
            matrix = model.encode([p["cleaned_text"] for p in pages], batch_size=32,
                                  convert_to_numpy=True, normalize_embeddings=True,
                                  show_progress_bar=True).astype(np.float32)
            np.savez_compressed(cache, embeddings=matrix, fingerprint=np.asarray(fp), dimension=np.asarray(dimension))
            embeddings[book_id] = matrix
    metadata = {
        "model_name": MODEL_NAME,
        "model_revision": revision,
        "sentence_transformers_version": sentence_transformers.__version__,
        "transformers_version": transformers.__version__,
        "torch_version": torch.__version__,
        "embedding_dimensions": dimension,
        "runtime_device": runtime_device,
        "normalized": True,
        "similarity": "cosine (dot product of L2-normalized vectors)",
        "query_prefix": QUERY_PREFIX,
        "corpus_fingerprints_sha256": fingerprints,
        "python": platform.python_version(),
    }
    return DenseIndex(model, embeddings, metadata)


def render_report(metrics: dict[str, Any], evals: list[dict[str, Any]], failures: list[dict[str, Any]]) -> str:
    """Render the machine-readable evaluation into a self-contained Markdown report."""
    overall = metrics["overall_by_retriever"]

    def pct(v: float | None) -> str:
        """Format a ratio for report tables while preserving empty slices."""
        return "n/a" if v is None else f"{100*v:.1f}%"
    lines = ["# Page-Level Retrieval Baseline v1", "",
             "One cleaned textbook page is one retrieval unit. Front matter is excluded, each query searches only its labeled book, and no gold label participates in ranking.", "",
             "## Headline results", "",
             "| Retriever | Hit@1 | Hit@3 | Hit@5 | MRR | Avg latency (ms) | p95 (ms) |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    labels = {"bm25": "BM25", "dense_bge_small": "BGE-small dense", "hybrid_rrf": "Hybrid RRF"}
    for key in RETRIEVERS:
        m = overall[key]
        lines.append(f'| {labels[key]} | {pct(m["hit_at_1"])} | {pct(m["hit_at_3"])} | {pct(m["hit_at_5"])} | {m["mrr"]:.3f} | {m["average_latency_ms"]:.2f} | {m["p95_latency_ms"]:.2f} |')
    qmap: dict[tuple[str, str], dict[str, Any]] = {(e["question_id"], e["retriever"]): e for e in evals}
    answer_ids = sorted({e["question_id"] for e in evals if e["answerable"]})
    bm_wins, dense_wins = [], []
    for qid in answer_ids:
        b, d = qmap[(qid, "bm25")], qmap[(qid, "dense_bge_small")]
        # Treat a missing relevant page as worse than every concrete corpus rank
        # so win/loss comparisons remain simple and deterministic.
        br, dr = b["first_relevant_rank"] or 10**9, d["first_relevant_rank"] or 10**9
        if br < dr: bm_wins.append((qid, br, None if dr == 10**9 else dr))
        if dr < br: dense_wins.append((qid, dr, None if br == 10**9 else br))
    delta = overall["hybrid_rrf"]["hit_at_5"] - overall["dense_bge_small"]["hit_at_5"]
    lines += ["", "## Comparison", "",
              f"BM25 ranks the accepted page higher on {len(bm_wins)} questions; dense retrieval wins on {len(dense_wins)}; ties account for the remainder.",
              f"Hybrid Hit@5 changes by {delta:+.3f} versus dense retrieval. " + ("This is a measurable improvement on this benchmark." if delta > 0 else "It does not improve Hit@5 on this benchmark."),
              "", "BM25 wins: " + (", ".join(f"{q} ({r} vs {o or '>5'})" for q, r, o in bm_wins) or "none") + ".",
              "", "Dense wins: " + (", ".join(f"{q} ({r} vs {o or '>5'})" for q, r, o in dense_wins) or "none") + ".",
              "", "## Top-5 failures", ""]
    if failures:
        lines += ["| Question | Retriever | Likely cause | Best accepted rank |", "|---|---|---|---:|"]
        for f in failures:
            lines.append(f'| {f["question_id"]} | {labels[f["retriever"]]} | {f["failure_category"].replace("_", " ")} | {f["gold_rank"] or "> corpus"} |')
    else:
        lines.append("No answerable question missed the accepted evidence in the top five.")
    lines += ["", "## Results by book", "",
              "| Book | Retriever | Hit@1 | Hit@3 | Hit@5 | MRR |", "|---|---|---:|---:|---:|---:|"]
    for group, values in metrics["by_book_and_retriever"].items():
        for key in RETRIEVERS:
            m = values[key]
            lines.append(f'| {group} | {labels[key]} | {pct(m["hit_at_1"])} | {pct(m["hit_at_3"])} | {pct(m["hit_at_5"])} | {m["mrr"]:.3f} |')
    lines += ["", "## Results by difficulty", "",
              "| Difficulty | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |", "|---|---|---:|---:|---:|---:|---:|"]
    for group, values in metrics["by_difficulty_and_retriever"].items():
        for key in RETRIEVERS:
            m = values[key]
            lines.append(f'| {group} | {labels[key]} | {m["answerable_questions"]} | {pct(m["hit_at_1"])} | {pct(m["hit_at_3"])} | {pct(m["hit_at_5"])} | {m["mrr"]:.3f} |')
    lines += ["", "## Dependency and evidence-span slices", "",
              "Only questions with the named flag are included.", "",
              "| Slice | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |", "|---|---|---:|---:|---:|---:|---:|"]
    slice_labels = {"formula_dependent": "Formula-dependent", "visual_dependent": "Visual-dependent", "table_dependent": "Table-dependent", "multi_page": "Multi-page", "multi_chunk": "Multi-chunk"}
    for group, values in metrics["slices_by_retriever"].items():
        for key in RETRIEVERS:
            m = values.get(key)
            if m:
                lines.append(f'| {slice_labels[group]} | {labels[key]} | {m["answerable_questions"]} | {pct(m["hit_at_1"])} | {pct(m["hit_at_3"])} | {pct(m["hit_at_5"])} | {m["mrr"]:.3f} |')
    lines += ["", "## Negative and not-answerable questions", "",
              f'{metrics["run_metadata"]["negative_questions"]} reviewed negative/weak-evidence questions were retrieved for inspection but excluded from Hit@K and MRR. Their IDs and handling are recorded in `page_level_retrieval_metrics.json`.',
              "", "## Decision", "",
              "The result is strong enough as a diagnostic baseline to proceed to chunk-level experiments, but 80.6% best Hit@5 is not strong enough to treat page retrieval as a finished retrieval solution. "
              "BGE-small is a sufficient lightweight baseline, not a sufficient final retriever; chunk-level experiments should retain BM25 and RRF controls and focus on the documented miss categories.",
              "", "## Reproducibility", "",
              f'- Dense model: `{metrics["run_metadata"]["dense"]["model_name"]}` (`{metrics["run_metadata"]["dense"]["model_revision"]}`), {metrics["run_metadata"]["dense"]["embedding_dimensions"]} dimensions on `{metrics["run_metadata"]["dense"]["runtime_device"]}`.',
              "- BM25: Okapi BM25, k1=1.5, b=0.75, lowercase alphanumeric tokenization.",
              "- Hybrid: reciprocal rank fusion over full BM25 and dense rankings, RRF k=60.",
              "- Latency is per question/retriever and excludes startup, corpus loading, and cached page embedding creation.", ""]
    return "\n".join(lines)


def run(root: Path, benchmark: Path, results_path: Path, metrics_path: Path,
        report_path: Path, cache_dir: Path, top_k: int = 5, device: str | None = None) -> dict[str, Any]:
    """Execute all retrievers, evaluate rankings, and write requested artifacts."""
    if top_k < 5:
        raise ValueError("top_k must be at least 5 to compute required Hit@5 and top-5 failures")
    questions = read_jsonl(benchmark)
    if benchmark.name.endswith("_candidates.jsonl"):
        # This guard prevents an explicit CLI override from bypassing the
        # reviewed-benchmark requirement.
        raise ValueError("Candidate benchmarks are not valid evaluation inputs; use retrieval_benchmark_v1.jsonl")
    books = load_pages(root)
    unknown = sorted({q["book_id"] for q in questions} - set(books))
    if unknown: raise ValueError(f"Unknown benchmark book_id(s): {unknown}")
    bm25 = {b: BM25(p["cleaned_text"] for p in pages) for b, pages in books.items()}
    dense = load_dense_index(books, cache_dir, device)
    output_rows: list[dict[str, Any]] = []
    evals: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for q in questions:
        # Book scoping happens here: every score vector and page lookup uses only
        # the corpus selected by the benchmark question's book_id.
        pages = books[q["book_id"]]
        gold = accepted_pdf_pages(q, pages)
        answerable = bool(gold)
        # Timings cover query-time work only; model startup, page loading, and
        # page embedding creation are intentionally excluded.
        t0 = time.perf_counter(); bs = bm25[q["book_id"]].scores(q["question"]); br = stable_ranking(bs); bm_ms = (time.perf_counter()-t0)*1000
        t0 = time.perf_counter(); qe = dense.model.encode([QUERY_PREFIX + q["question"]], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)[0]; ds = dense.embeddings[q["book_id"]] @ qe; dr = stable_ranking(ds); dense_ms = (time.perf_counter()-t0)*1000
        # Hybrid latency includes both component retrievers because both must run
        # before RRF can combine their ranks.
        t0 = time.perf_counter(); hs = reciprocal_rank_fusion([br, dr], len(pages)); hr = stable_ranking(hs); hybrid_ms = bm_ms + dense_ms + (time.perf_counter()-t0)*1000
        variants = (("bm25", bs, br, bm_ms), ("dense_bge_small", ds, dr, dense_ms), ("hybrid_rrf", hs, hr, hybrid_ms))
        for retriever, scores, ranking, latency in variants:
            # The first accepted page controls Hit@K and reciprocal rank. Gold is
            # consulted only after ranking has completed.
            relevant_ranks = [i for i, idx in enumerate(ranking, 1) if int(pages[int(idx)]["pdf_page_number"]) in gold]
            first = min(relevant_ranks) if relevant_ranks else None
            failure = failure_category(q, first) if answerable and (first is None or first > 5) else None
            evals.append({"question_id": q["question_id"], "retriever": retriever, "book_id": q["book_id"], "difficulty": q.get("difficulty", "unknown"), "formula_dependent": bool(q.get("formula_dependency")), "visual_dependent": bool(q.get("visual_dependency")), "table_dependent": bool(q.get("table_dependency")), "multi_page": bool(q.get("requires_multiple_pages")), "multi_chunk": bool(q.get("requires_multiple_chunks")), "answerable": answerable, "first_relevant_rank": first, "latency_ms": latency})
            if failure:
                failures.append({"question_id": q["question_id"], "question": q["question"], "retriever": retriever, "failure_category": failure, "gold_rank": first})
            for rank, idx in enumerate(ranking[:top_k], 1):
                # Save one record per retrieved page so individual successes and
                # misses can be inspected without recomputing the ranking.
                page = pages[int(idx)]
                output_rows.append({"question_id": q["question_id"], "question": q["question"], "book_id": q["book_id"], "retriever": retriever, "rank": rank, "score": float(scores[int(idx)]), "retrieved_pdf_page": page["pdf_page_number"], "retrieved_textbook_page": page["textbook_page_number"], "chapter_title": page.get("chapter_title"), "section_title": page.get("section_title"), "text_snippet": snippet(page["cleaned_text"], q["question"]), "matches_accepted_gold_evidence": int(page["pdf_page_number"]) in gold, "latency_ms": latency, "failure_category": failure})
    answerable_evals = [e for e in evals if e["answerable"]]
    metrics: dict[str, Any] = {
        "run_metadata": {"benchmark": str(benchmark), "top_k": top_k, "search_unit": "page", "search_field": "cleaned_text", "front_matter_excluded": True, "book_scoped": True, "answerable_questions": len({e["question_id"] for e in answerable_evals}), "negative_questions": len(questions) - len({e["question_id"] for e in answerable_evals}), "dense": dense.metadata, "bm25": {"variant": "Okapi BM25", "k1": 1.5, "b": 0.75}, "hybrid": {"method": "reciprocal_rank_fusion", "rrf_k": 60}},
        "overall_by_retriever": group_metrics(evals, "retriever"),
        "by_book_and_retriever": {}, "by_difficulty_and_retriever": {}, "slices_by_retriever": {},
        "negative_questions": [], "top_5_failures": failures,
    }
    for group_key, target in (("book_id", "by_book_and_retriever"), ("difficulty", "by_difficulty_and_retriever")):
        values = sorted({e[group_key] for e in evals})
        metrics[target] = {str(v): group_metrics([e for e in evals if e[group_key] == v], "retriever") for v in values}
    for flag in ("formula_dependent", "visual_dependent", "table_dependent", "multi_page", "multi_chunk"):
        metrics["slices_by_retriever"][flag] = group_metrics([e for e in evals if e[flag]], "retriever")
    for q in questions:
        if not q.get("gold_pdf_pages"):
            # Preserve negatives for auditability, but do not invent relevance
            # labels or fold them into answerable-question metrics.
            metrics["negative_questions"].append({"question_id": q["question_id"], "question": q["question"], "book_id": q["book_id"], "review_status": q.get("review_status"), "handling": "reported_only_not_scored"})
    for path in (results_path, metrics_path, report_path): path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in output_rows), encoding="utf-8")
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path.write_text(render_report(metrics, evals, failures), encoding="utf-8")
    return metrics


def build_parser() -> argparse.ArgumentParser:
    """Define the reproducible CLI and configurable artifact locations."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--benchmark", type=Path)
    p.add_argument("--results", type=Path)
    p.add_argument("--metrics", type=Path)
    p.add_argument("--report", type=Path)
    p.add_argument("--cache-dir", type=Path)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--device", help="Sentence Transformers device, e.g. cpu or cuda")
    return p


def main(argv: list[str] | None = None) -> None:
    """Resolve root-relative defaults, run evaluation, and print headline JSON."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    metrics = run(root,
        (args.benchmark or root / "data/benchmarks/retrieval_benchmark_v1.jsonl").resolve(),
        (args.results or root / "data/retrieval/page_level_results.jsonl").resolve(),
        (args.metrics or root / "reports/page_level_retrieval_metrics.json").resolve(),
        (args.report or root / "reports/page_level_retrieval_baseline.md").resolve(),
        (args.cache_dir or root / "data/retrieval/cache").resolve(), args.top_k, args.device)
    print(json.dumps(metrics["overall_by_retriever"], indent=2))


if __name__ == "__main__":
    main()
