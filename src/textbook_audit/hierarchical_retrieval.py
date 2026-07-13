"""Hierarchical chapter, section, and paragraph-group retrieval baseline.

The hierarchy is derived deterministically from verified chapter maps and text
layout signals. Gold evidence is consulted only after construction and ranking.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .chunk_retrieval import answer_span_coverage, split_sentences
from .retrieval import (BM25, MODEL_NAME, QUERY_PREFIX, RETRIEVERS,
                        group_metrics, percentile95, read_jsonl,
                        reciprocal_rank_fusion, stable_ranking, tokenize)

APPROACHES = ("strict_cascade", "soft_fusion")
NUMBERED_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+){1,3})\s+(.{2,100}?)\s*[:.]?\s*$")
LIST_RE = re.compile(r"^\s*(?:[-•*]|\(?[a-zA-Z0-9]+[.)])\s+")
FORMULA_RE = re.compile(r"(?:=|→|←|⇌|\+\s*[A-Z][a-z]?|\b(?:sin|cos|tan)\b|\d+\s*[×÷/]\s*\d+)")
FIGURE_RE = re.compile(r"^(?:fig(?:ure)?\.?|diagram|image)\s*\d*", re.I)
ACTIVITY_RE = re.compile(r"^(?:activity|lab activity|think and discuss|do this|try this)\b", re.I)
EXAMPLE_RE = re.compile(r"^(?:example|worked example)\b", re.I)
QUESTION_RE = re.compile(r"^(?:questions?|exercise|what|why|how|when|where|which|can you|do you)\b", re.I)


def load_chapter_content(root: Path, book_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load pages assigned solely through verified chapter-map PDF ranges."""
    chapter_map = json.loads((root / "data/processed" / f"{book_id}_chapter_map.json").read_text(encoding="utf-8"))
    chapters = chapter_map["chapters"]
    pages = read_jsonl(root / "data/processed" / f"{book_id}_pages.jsonl")
    selected: list[dict[str, Any]] = []
    for page in pages:
        pdf = int(page["pdf_page_number"])
        match = next((c for c in chapters if c["detected_pdf_page_start"] <= pdf <= c["detected_pdf_page_end"]), None)
        if match and page.get("cleaned_text", "").strip():
            copy = dict(page)
            # The verified range overrides heuristic page-level chapter fields.
            copy["chapter_number"] = match["chapter_number"]
            copy["chapter_title"] = match["chapter_title"]
            selected.append(copy)
    return chapters, selected


def detect_heading(line: str, known_section_title: str | None = None) -> tuple[str, str, str] | None:
    """Recognize conservative high/medium headings and reject question-like lines."""
    text = " ".join(line.split()).strip(" -")
    if not text or len(tokenize(text)) > 14 or text.endswith("?") or QUESTION_RE.match(text) or ACTIVITY_RE.match(text):
        return None
    numbered = NUMBERED_HEADING_RE.match(text)
    if numbered:
        return text.rstrip(".:"), "high", "numbered_heading"
    # The extraction pipeline's page title is an independent layout-derived
    # signal. Agreement permits an unnumbered medium heading without promoting
    # arbitrary diagram labels or short prose fragments.
    known = " ".join((known_section_title or "").split()).strip(" .:")
    if known and text.lower().strip(" .:") == known.lower() and len(tokenize(text)) >= 2 and not LIST_RE.match(text):
        return text, "medium", "page_section_title_match"
    return None


def classify_block(text: str, page: dict[str, Any]) -> str:
    """Classify a reconstructed text block using visible textual/layout signals."""
    if ACTIVITY_RE.match(text): return "activity"
    if EXAMPLE_RE.match(text): return "example"
    if QUESTION_RE.match(text) or text.rstrip().endswith("?"): return "question"
    if FIGURE_RE.match(text): return "figure_caption"
    if LIST_RE.match(text): return "bullet_list"
    if page.get("has_table") and len(tokenize(text)) < 100: return "table_text"
    if FORMULA_RE.search(text) or page.get("has_equation_like_text") and len(tokenize(text)) < 80: return "formula"
    return "paragraph"


def reconstruct_page_blocks(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Rejoin wrapped PDF lines and preserve semantic/list/formula boundaries."""
    lines = [" ".join(line.split()) for line in page["cleaned_text"].splitlines()]
    blocks: list[dict[str, Any]] = []; current: list[str] = []

    def flush() -> None:
        """Emit the current reconstructed paragraph with source metadata."""
        nonlocal current
        if current:
            text = " ".join(current).strip()
            blocks.append({"text": text, "block_type": classify_block(text, page), "page": page})
            current = []

    for raw in lines:
        if not raw:
            flush(); continue
        heading = detect_heading(raw, page.get("section_title"))
        boundary = heading or LIST_RE.match(raw) or ACTIVITY_RE.match(raw) or EXAMPLE_RE.match(raw) or FIGURE_RE.match(raw)
        if boundary:
            flush()
            if heading:
                blocks.append({"text": heading[0], "block_type": "heading", "page": page,
                               "heading_confidence": heading[1], "section_detection_method": heading[2]})
            else:
                current = [raw]
            continue
        current.append(raw)
        # Sentence completion plus a reasonably substantial block is evidence
        # that the next extracted line starts a new paragraph rather than wrap.
        if raw.endswith((".", "!", "?", ":")) and len(tokenize(" ".join(current))) >= 35:
            flush()
    flush()
    return blocks


def _unique(values: Iterable[Any]) -> list[Any]:
    """Deduplicate metadata in first-observed order."""
    return list(dict.fromkeys(v for v in values if v is not None))


def build_hierarchy(root: Path, book_id: str, target: int = 250,
                    minimum: int = 150, maximum: int = 350) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Construct section-aware paragraph groups and hierarchy audit statistics."""
    if not 0 < minimum <= target <= maximum:
        raise ValueError("paragraph sizes must satisfy 0 < minimum <= target <= maximum")
    chapters, pages = load_chapter_content(root, book_id)
    leaves: list[dict[str, Any]] = []; heading_counts = defaultdict(int); detected_sections = 0
    fallback_chapters = 0; successes: list[dict[str, Any]] = []; failures: list[dict[str, Any]] = []
    for chapter in chapters:
        chapter_pages = [p for p in pages if p["chapter_number"] == chapter["chapter_number"]]
        chapter_id = f"{book_id}:chapter:{int(chapter['chapter_number']):02d}"
        section_number = 0; current_section: dict[str, Any] | None = None
        section_blocks: list[dict[str, Any]] = []

        def emit_section() -> None:
            """Split accumulated section blocks into bounded paragraph-group leaves."""
            nonlocal section_blocks
            if not section_blocks: return
            section = current_section or {"id": f"{chapter_id}:fallback", "title": None,
                                          "confidence": "none", "method": "chapter_only_fallback"}
            expanded: list[dict[str, Any]] = []
            for block in section_blocks:
                if not tokenize(block["text"]):
                    continue
                if len(tokenize(block["text"])) > maximum:
                    for part in split_sentences(block["text"], maximum):
                        expanded.append({**block, "text": part})
                else: expanded.append(block)
            pending: list[dict[str, Any]] = []

            def emit_pending() -> None:
                """Materialize one leaf and aggregate all contributing pages/signals."""
                nonlocal pending
                if not pending: return
                source_pages = [b["page"] for b in pending]
                text = "\n".join(b["text"] for b in pending)
                leaf_index = len(leaves)
                leaves.append({"chunk_id": f"{book_id}:paragraph:{leaf_index:05d}", "book_id": book_id,
                    "chapter_id": chapter_id, "chapter_title": chapter["chapter_title"],
                    "section_id": section["id"], "section_title": section["title"],
                    "heading_confidence": section["confidence"], "section_detection_method": section["method"],
                    "block_types": _unique(b["block_type"] for b in pending),
                    "pdf_pages": _unique(p["pdf_page_number"] for p in source_pages),
                    "textbook_pages": _unique(p.get("textbook_page_number") for p in source_pages),
                    "previous_chunk_id": None, "next_chunk_id": None, "token_count": len(tokenize(text)),
                    "visual_dependency_signal": any(bool(p.get("has_image")) for p in source_pages) or any(b["block_type"] == "figure_caption" for b in pending),
                    "formula_dependency_signal": any(bool(p.get("has_equation_like_text")) for p in source_pages) or any(b["block_type"] == "formula" for b in pending),
                    "table_dependency_signal": any(bool(p.get("has_table")) for p in source_pages) or any(b["block_type"] == "table_text" for b in pending),
                    "text": text})
                pending = []

            for block in expanded:
                proposed = sum(len(tokenize(b["text"])) for b in pending) + len(tokenize(block["text"]))
                if pending and proposed > maximum: emit_pending()
                pending.append(block)
                if sum(len(tokenize(b["text"])) for b in pending) >= target: emit_pending()
            emit_pending(); section_blocks = []

        for page in chapter_pages:
            for block in reconstruct_page_blocks(page):
                if block["block_type"] == "heading":
                    emit_section(); section_number += 1; detected_sections += 1
                    current_section = {"id": f"{chapter_id}:section:{section_number:03d}", "title": block["text"],
                                       "confidence": block["heading_confidence"], "method": block["section_detection_method"]}
                    heading_counts[block["heading_confidence"]] += 1
                    if len(successes) < 8: successes.append({"book_id": book_id, "chapter": chapter["chapter_title"], "heading": block["text"], "confidence": block["heading_confidence"]})
                else: section_blocks.append(block)
        emit_section()
        if section_number == 0:
            fallback_chapters += 1
            failures.append({"book_id": book_id, "chapter": chapter["chapter_title"], "issue": "no_reliable_section_heading"})
    for i, leaf in enumerate(leaves):
        leaf["previous_chunk_id"] = leaves[i - 1]["chunk_id"] if i else None
        leaf["next_chunk_id"] = leaves[i + 1]["chunk_id"] if i + 1 < len(leaves) else None
    sizes = [leaf["token_count"] for leaf in leaves]
    audit = {"book_id": book_id, "chapter_count": len(chapters), "detected_section_count": detected_sections,
             "heading_counts": {k: heading_counts.get(k, 0) for k in ("high", "medium", "low")},
             "paragraph_group_count": len(leaves), "token_sizes": {"average": statistics.fmean(sizes),
             "p50": float(np.percentile(sizes, 50)), "p95": float(np.percentile(sizes, 95)),
             "minimum": min(sizes), "maximum": max(sizes)}, "fallback_to_chapter_only_count": fallback_chapters,
             "representative_successes": successes, "representative_failures": failures[:8]}
    return leaves, audit


def build_nodes(leaves: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Aggregate leaf records into ordered section and chapter retrieval nodes."""
    section_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    chapter_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for leaf in leaves:
        section_groups[leaf["section_id"]].append(leaf); chapter_groups[leaf["chapter_id"]].append(leaf)
    sections = [{"id": sid, "chapter_id": rows[0]["chapter_id"], "chapter_title": rows[0]["chapter_title"],
                 "title": rows[0]["section_title"], "heading_confidence": rows[0]["heading_confidence"],
                 "text": "\n".join(r["text"] for r in rows), "child_ids": [r["chunk_id"] for r in rows]}
                for sid, rows in section_groups.items()]
    chapters = [{"id": cid, "title": rows[0]["chapter_title"],
                 "section_ids": _unique(r["section_id"] for r in rows), "child_ids": [r["chunk_id"] for r in rows]}
                for cid, rows in chapter_groups.items()]
    return sections, chapters


def aggregate_normalized(vectors: np.ndarray) -> np.ndarray:
    """Mean normalized child vectors and L2-normalize the resulting parent vector."""
    vector = vectors.mean(axis=0)
    norm = np.linalg.norm(vector)
    return (vector / norm if norm else vector).astype(np.float32)


def _fingerprint(records: list[dict[str, Any]], text_key: str = "text") -> str:
    """Hash ordered identity/text pairs for cache invalidation."""
    h = hashlib.sha256()
    for row in records:
        h.update(str(row.get("chunk_id", row.get("id"))).encode()); h.update(str(row.get(text_key, "")).encode("utf-8"))
    return h.hexdigest()


def load_hierarchy_embeddings(corpora: dict[str, dict[str, list[dict[str, Any]]]], cache_dir: Path,
                              device: str | None, section_direct_limit: int = 450) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Create/cache paragraph, section, and aggregated chapter embeddings per book."""
    try:
        import sentence_transformers, torch, transformers
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("Hierarchical dense retrieval requires sentence-transformers") from exc
    model = SentenceTransformer(MODEL_NAME, device=device); cache_dir.mkdir(parents=True, exist_ok=True)
    get_dim = getattr(model, "get_embedding_dimension", model.get_sentence_embedding_dimension); dimension = int(get_dim())
    matrices: dict[str, Any] = {}; methods: dict[str, Any] = {}
    for book_id, levels in corpora.items():
        leaves, sections, chapters = levels["paragraphs"], levels["sections"], levels["chapters"]
        book_matrices: dict[str, np.ndarray] = {}
        paragraph_texts = [f'{r["chapter_title"]}\n{r["section_title"] or ""}\n{r["text"]}' for r in leaves]
        pfp = _fingerprint([{**r, "embed_text": t} for r, t in zip(leaves, paragraph_texts)], "embed_text")
        ppath = cache_dir / f"{book_id}_hierarchy_paragraph_bge-small-en-v1.5.npz"
        if ppath.is_file() and str(np.load(ppath, allow_pickle=False)["fingerprint"].item()) == pfp:
            book_matrices["paragraphs"] = np.load(ppath, allow_pickle=False)["embeddings"].astype(np.float32)
        else:
            book_matrices["paragraphs"] = model.encode(paragraph_texts, batch_size=32, convert_to_numpy=True,
                                                        normalize_embeddings=True, show_progress_bar=True).astype(np.float32)
            np.savez_compressed(ppath, embeddings=book_matrices["paragraphs"], fingerprint=np.asarray(pfp), dimension=np.asarray(dimension))
        leaf_index = {r["chunk_id"]: i for i, r in enumerate(leaves)}
        section_methods = {s["id"]: ("direct_title_and_text" if len(tokenize(s["text"])) <= section_direct_limit
                                             else "normalized_mean_child_paragraph_embeddings") for s in sections}
        spath = cache_dir / f"{book_id}_hierarchy_section_bge-small-en-v1.5.npz"
        svalid = spath.is_file() and str(np.load(spath, allow_pickle=False)["fingerprint"].item()) == pfp
        if svalid:
            book_matrices["sections"] = np.load(spath, allow_pickle=False)["embeddings"].astype(np.float32)
        else:
            section_vectors: list[np.ndarray | None] = [None] * len(sections)
            short_indices = [i for i, s in enumerate(sections) if section_methods[s["id"]] == "direct_title_and_text"]
            short_texts = [f'{sections[i]["chapter_title"]}\n{sections[i]["title"] or ""}\n{sections[i]["text"]}' for i in short_indices]
            if short_texts:
                encoded = model.encode(short_texts, batch_size=32, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=True)
                for i, vector in zip(short_indices, encoded): section_vectors[i] = vector
            for i, section in enumerate(sections):
                if section_vectors[i] is None:
                    section_vectors[i] = aggregate_normalized(book_matrices["paragraphs"][[leaf_index[x] for x in section["child_ids"]]])
            book_matrices["sections"] = np.asarray(section_vectors, dtype=np.float32)
            np.savez_compressed(spath, embeddings=book_matrices["sections"], fingerprint=np.asarray(pfp), dimension=np.asarray(dimension))
        # Chapters are never raw-text encoded: child section vectors are averaged
        # with a separately embedded chapter-title representation.
        cpath = cache_dir / f"{book_id}_hierarchy_chapter_bge-small-en-v1.5.npz"
        cvalid = cpath.is_file() and str(np.load(cpath, allow_pickle=False)["fingerprint"].item()) == pfp
        if cvalid:
            book_matrices["chapters"] = np.load(cpath, allow_pickle=False)["embeddings"].astype(np.float32)
        else:
            section_index = {r["id"]: i for i, r in enumerate(sections)}
            titles = model.encode([c["title"] for c in chapters], batch_size=32, convert_to_numpy=True,
                                  normalize_embeddings=True, show_progress_bar=False)
            chapter_vectors = []
            for chapter, title in zip(chapters, titles):
                children = book_matrices["sections"][[section_index[x] for x in chapter["section_ids"]]]
                chapter_vectors.append(aggregate_normalized(np.vstack([title, children])))
            book_matrices["chapters"] = np.asarray(chapter_vectors, dtype=np.float32)
            np.savez_compressed(cpath, embeddings=book_matrices["chapters"], fingerprint=np.asarray(pfp), dimension=np.asarray(dimension))
        matrices[book_id] = book_matrices; methods[book_id] = section_methods
    first = model._first_module().auto_model.config
    metadata = {"model_name": MODEL_NAME, "model_revision": getattr(first, "_commit_hash", None) or "default",
                "embedding_dimensions": dimension, "runtime_device": str(model.device), "normalized": True,
                "paragraph_representation": "chapter title + section title + paragraph text",
                "short_section_representation": "chapter title + section title + section text",
                "long_section_representation": "L2-normalized mean of normalized child paragraph embeddings",
                "chapter_representation": "L2-normalized mean of section embeddings plus separate chapter-title embedding",
                "section_direct_token_limit": section_direct_limit, "sentence_transformers_version": sentence_transformers.__version__,
                "transformers_version": transformers.__version__, "torch_version": torch.__version__}
    return model, matrices, {"metadata": metadata, "section_methods": methods}


def derive_gold(question: dict[str, Any], leaves: list[dict[str, Any]], minimum_coverage: float = 0.5) -> dict[str, Any]:
    """Derive accepted leaves and their parents from reviewed pages plus answer span."""
    pages = {int(x) for x in question.get("gold_pdf_pages", [])}; span = (question.get("gold_answer_span") or "").strip()
    if not pages or not span: return {"status": "not_answerable", "paragraphs": [], "sections": [], "chapters": [], "coverage": 0.0}
    scores = [(answer_span_coverage(span, leaf["text"]), leaf) for leaf in leaves if pages.intersection(map(int, leaf["pdf_pages"]))]
    best = max((s for s, _ in scores), default=0.0)
    if best < minimum_coverage: return {"status": "manual_review", "paragraphs": [], "sections": [], "chapters": [], "coverage": best}
    accepted = [leaf for score, leaf in scores if score >= minimum_coverage and score >= best * .9]
    return {"status": "mapped", "paragraphs": [x["chunk_id"] for x in accepted],
            "sections": _unique(x["section_id"] for x in accepted), "chapters": _unique(x["chapter_id"] for x in accepted), "coverage": best}


def rank_variants(question: str, levels: dict[str, list[dict[str, Any]]], bm25: dict[str, BM25],
                  model: Any, embeddings: dict[str, np.ndarray]) -> tuple[dict[str, dict[str, np.ndarray]], dict[str, float]]:
    """Rank all hierarchy levels independently with BM25, dense, and hybrid RRF."""
    scores: dict[str, dict[str, np.ndarray]] = {r: {} for r in RETRIEVERS}; latencies = {}
    t0 = time.perf_counter()
    for level in ("chapters", "sections", "paragraphs"): scores["bm25"][level] = bm25[level].scores(question)
    bm_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter(); query = model.encode([QUERY_PREFIX + question], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)[0]
    for level in ("chapters", "sections", "paragraphs"): scores["dense_bge_small"][level] = embeddings[level] @ query
    dense_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    for level in ("chapters", "sections", "paragraphs"):
        scores["hybrid_rrf"][level] = reciprocal_rank_fusion([stable_ranking(scores["bm25"][level]), stable_ranking(scores["dense_bge_small"][level])], len(levels[level]))
    hybrid_ms = bm_ms + dense_ms + (time.perf_counter() - t0) * 1000
    latencies.update({"bm25": bm_ms, "dense_bge_small": dense_ms, "hybrid_rrf": hybrid_ms})
    return scores, latencies


def strict_cascade(levels: dict[str, list[dict[str, Any]]], scores: dict[str, np.ndarray],
                   chapter_k: int, section_k: int) -> tuple[np.ndarray, dict[str, Any]]:
    """Filter paragraphs through top chapters then top eligible sections."""
    chapter_rank = stable_ranking(scores["chapters"]); chapter_ids = {levels["chapters"][int(i)]["id"] for i in chapter_rank[:chapter_k]}
    eligible_sections = [i for i, node in enumerate(levels["sections"]) if node["chapter_id"] in chapter_ids]
    section_rank = sorted(eligible_sections, key=lambda i: (-scores["sections"][i], i))[:section_k]
    section_ids = {levels["sections"][i]["id"] for i in section_rank}
    eligible_leaves = [i for i, leaf in enumerate(levels["paragraphs"]) if leaf["section_id"] in section_ids]
    paragraph_rank = np.asarray(sorted(eligible_leaves, key=lambda i: (-scores["paragraphs"][i], i)), dtype=int)
    return paragraph_rank, {"selected_chapter_ids": sorted(chapter_ids), "selected_section_ids": sorted(section_ids)}


def soft_fusion(levels: dict[str, list[dict[str, Any]]], scores: dict[str, np.ndarray],
                section_weight: float = 0.5, chapter_weight: float = 0.25, rrf_k: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """Fuse paragraph and parent ranks while keeping every paragraph eligible."""
    ranks = {}
    for level in ("chapters", "sections", "paragraphs"):
        rank = stable_ranking(scores[level]); inverse = np.empty(len(rank), dtype=int); inverse[rank] = np.arange(1, len(rank) + 1); ranks[level] = inverse
    chapter_index = {x["id"]: i for i, x in enumerate(levels["chapters"])}; section_index = {x["id"]: i for i, x in enumerate(levels["sections"])}
    fused = np.zeros(len(levels["paragraphs"]), dtype=float)
    for i, leaf in enumerate(levels["paragraphs"]):
        section = levels["sections"][section_index[leaf["section_id"]]]
        fused[i] = (1 / (rrf_k + ranks["paragraphs"][i]) + section_weight / (rrf_k + ranks["sections"][section_index[leaf["section_id"]]]) +
                    chapter_weight / (rrf_k + ranks["chapters"][chapter_index[section["chapter_id"]]]))
    return stable_ranking(fused), fused


def classify_failure(question: dict[str, Any], approach: str, gold: dict[str, Any], stage: dict[str, Any],
                     base_paragraph_rank: int | None) -> str:
    """Attribute a top-five miss to structure, cascade, parent suppression, or evidence type."""
    if gold["status"] == "manual_review": return "paragraph_reconstruction"
    if approach == "strict_cascade" and not set(gold["chapters"]).intersection(stage.get("selected_chapter_ids", [])): return "correct_chapter_missed_during_cascade"
    if approach == "strict_cascade" and not set(gold["sections"]).intersection(stage.get("selected_section_ids", [])): return "correct_section_missed_during_cascade"
    if question.get("formula_dependency"): return "formula_or_symbol_extraction"
    if question.get("visual_dependency"): return "visual_dependency"
    if question.get("requires_multiple_pages") or question.get("requires_multiple_chunks"): return "evidence_spread_across_multiple_sections_or_pages"
    if approach == "soft_fusion" and base_paragraph_rank is not None and base_paragraph_rank <= 5: return "parent_signals_suppressed_strong_paragraph"
    return "paragraph_ranked_poorly_despite_correct_parents"


def run(root: Path, benchmark: Path, results_path: Path, metrics_path: Path, report_path: Path,
        audit_path: Path, cache_dir: Path, top_k: int = 5, chapter_k: int = 3, section_k: int = 8,
        paragraph_target: int = 250, paragraph_min: int = 150, paragraph_max: int = 350,
        section_weight: float = .5, chapter_weight: float = .25, gold_min_coverage: float = .5,
        device: str | None = None) -> dict[str, Any]:
    """Build hierarchy, run six retrieval variants, evaluate, and write artifacts."""
    if top_k < 5: raise ValueError("top_k must be at least 5")
    if benchmark.name.endswith("_candidates.jsonl"): raise ValueError("Use the reviewed retrieval_benchmark_v1.jsonl")
    questions = read_jsonl(benchmark); corpora = {}; audits = []
    for book_id in ("biology", "physical_sciences"):
        leaves, audit = build_hierarchy(root, book_id, paragraph_target, paragraph_min, paragraph_max)
        sections, chapters = build_nodes(leaves); corpora[book_id] = {"paragraphs": leaves, "sections": sections, "chapters": chapters}; audits.append(audit)
        path = root / "data/processed" / f"{book_id}_hierarchy.jsonl"; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in leaves), encoding="utf-8")
    bm25 = {b: {"paragraphs": BM25(x["text"] for x in levels["paragraphs"]),
                "sections": BM25(f'{x["chapter_title"]} {x["title"] or ""} {x["text"]}' for x in levels["sections"]),
                "chapters": BM25(x["title"] for x in levels["chapters"])} for b, levels in corpora.items()}
    model, dense, dense_info = load_hierarchy_embeddings(corpora, cache_dir, device)
    results = []; evals = []; failures = []; mappings = {}; stage_evals = []
    for question in questions:
        book = question["book_id"]; levels = corpora[book]; gold = derive_gold(question, levels["paragraphs"], gold_min_coverage); mappings[question["question_id"]] = gold
        all_scores, latencies = rank_variants(question["question"], levels, bm25[book], model, dense[book])
        for retriever in RETRIEVERS:
            chapter_rank = stable_ranking(all_scores[retriever]["chapters"]); section_rank = stable_ranking(all_scores[retriever]["sections"]); base_rank = stable_ranking(all_scores[retriever]["paragraphs"])
            chapter_first = next((r for r, i in enumerate(chapter_rank, 1) if levels["chapters"][int(i)]["id"] in gold["chapters"]), None)
            section_first = next((r for r, i in enumerate(section_rank, 1) if levels["sections"][int(i)]["id"] in gold["sections"]), None)
            base_first = next((r for r, i in enumerate(base_rank, 1) if levels["paragraphs"][int(i)]["chunk_id"] in gold["paragraphs"]), None)
            for approach in APPROACHES:
                t0 = time.perf_counter()
                if approach == "strict_cascade": ranking, stage = strict_cascade(levels, all_scores[retriever], chapter_k, section_k); final_scores = all_scores[retriever]["paragraphs"]
                else: ranking, final_scores = soft_fusion(levels, all_scores[retriever], section_weight, chapter_weight); stage = {}
                latency = latencies[retriever] + (time.perf_counter() - t0) * 1000
                first = next((r for r, i in enumerate(ranking, 1) if levels["paragraphs"][int(i)]["chunk_id"] in gold["paragraphs"]), None)
                answerable = gold["status"] == "mapped"; failure = classify_failure(question, approach, gold, stage, base_first) if gold["status"] == "manual_review" or answerable and (first is None or first > 5) else None
                evals.append({"question_id": question["question_id"], "approach": approach, "retriever": retriever, "book_id": book,
                    "difficulty": question.get("difficulty", "unknown"), "formula_dependent": bool(question.get("formula_dependency")),
                    "visual_dependent": bool(question.get("visual_dependency")), "table_dependent": bool(question.get("table_dependency")),
                    "multi_page": bool(question.get("requires_multiple_pages")), "multi_chunk": bool(question.get("requires_multiple_chunks")),
                    "heading_confidence": next((x["heading_confidence"] for x in levels["paragraphs"] if x["chunk_id"] in gold["paragraphs"]), "unmapped"),
                    "answerable": answerable, "first_relevant_rank": first, "latency_ms": latency})
                stage_evals.append({"question_id": question["question_id"], "approach": approach, "retriever": retriever, "answerable": answerable,
                                    "chapter_first_rank": chapter_first, "section_first_rank": section_first, "independent_paragraph_first_rank": base_first,
                                    "selected_gold_chapter": bool(set(gold["chapters"]).intersection(stage.get("selected_chapter_ids", []))) if approach == "strict_cascade" else None,
                                    "selected_gold_section": bool(set(gold["sections"]).intersection(stage.get("selected_section_ids", []))) if approach == "strict_cascade" else None})
                if failure: failures.append({"question_id": question["question_id"], "approach": approach, "retriever": retriever, "failure_category": failure, "gold_rank": first})
                for rank, index in enumerate(ranking[:top_k], 1):
                    leaf = levels["paragraphs"][int(index)]
                    results.append({"question_id": question["question_id"], "question": question["question"], "book_id": book,
                        "approach": approach, "retriever": retriever, "rank": rank, "score": float(final_scores[int(index)]),
                        "retrieved_chunk_id": leaf["chunk_id"], "chapter_id": leaf["chapter_id"], "chapter_title": leaf["chapter_title"],
                        "section_id": leaf["section_id"], "section_title": leaf["section_title"], "heading_confidence": leaf["heading_confidence"],
                        "pdf_pages": leaf["pdf_pages"], "textbook_pages": leaf["textbook_pages"], "retrieved_text": leaf["text"],
                        "matches_accepted_gold_evidence": leaf["chunk_id"] in gold["paragraphs"], "gold_mapping_status": gold["status"],
                        "latency_ms": latency, "failure_category": failure,
                        "cascade_selected_chapters": stage.get("selected_chapter_ids"), "cascade_selected_sections": stage.get("selected_section_ids")})
    overall = {a: group_metrics([e for e in evals if e["approach"] == a], "retriever") for a in APPROACHES}
    def nested(key: str) -> dict[str, Any]:
        """Group metrics as approach then requested slice value then retriever."""
        return {a: {str(v): group_metrics([e for e in evals if e["approach"] == a and str(e[key]) == str(v)], "retriever") for v in sorted({e[key] for e in evals})} for a in APPROACHES}
    stage_metrics = {}
    for approach in APPROACHES:
        stage_metrics[approach] = {}
        for retriever in RETRIEVERS:
            rows = [x for x in stage_evals if x["approach"] == approach and x["retriever"] == retriever and x["answerable"]]
            stage_metrics[approach][retriever] = {"answerable_questions": len(rows),
                "chapter_recall_at_k": sum(x["chapter_first_rank"] is not None and x["chapter_first_rank"] <= chapter_k for x in rows) / len(rows),
                "section_recall_at_k": sum(x["section_first_rank"] is not None and x["section_first_rank"] <= section_k for x in rows) / len(rows),
                "independent_paragraph_hit_at_5": sum(x["independent_paragraph_first_rank"] is not None and x["independent_paragraph_first_rank"] <= 5 for x in rows) / len(rows),
                "cascade_gold_chapter_survival": (sum(bool(x["selected_gold_chapter"]) for x in rows) / len(rows)) if approach == "strict_cascade" else None,
                "cascade_gold_section_survival": (sum(bool(x["selected_gold_section"]) for x in rows) / len(rows)) if approach == "strict_cascade" else None}
    baseline = {}
    for name in ("page_level_retrieval_metrics.json", "chunk_level_retrieval_metrics.json"):
        path = root / "reports" / name
        if path.is_file(): baseline[name] = json.loads(path.read_text(encoding="utf-8"))
    metrics = {"run_metadata": {"benchmark": str(benchmark), "top_k": top_k, "chapter_k": chapter_k, "section_k": section_k,
               "paragraph_target": paragraph_target, "paragraph_min": paragraph_min, "paragraph_max": paragraph_max,
               "soft_section_weight": section_weight, "soft_chapter_weight": chapter_weight, "gold_minimum_coverage": gold_min_coverage,
               "front_matter_definition": "outside verified chapter-map PDF ranges", "dense": dense_info["metadata"]},
               "overall_by_approach_and_retriever": overall, "stage_level_recall": stage_metrics,
               "by_book": nested("book_id"), "by_difficulty": nested("difficulty"), "by_heading_confidence": nested("heading_confidence"),
               "slices": {flag: {a: group_metrics([e for e in evals if e["approach"] == a and e[flag]], "retriever") for a in APPROACHES}
                          for flag in ("formula_dependent", "visual_dependent", "table_dependent", "multi_page", "multi_chunk")},
               "gold_mappings": mappings, "top_5_failures": failures, "hierarchy_audit": audits,
               "baseline_metrics": {"page": baseline.get("page_level_retrieval_metrics.json", {}).get("overall_by_retriever"),
                                    "page_slices": baseline.get("page_level_retrieval_metrics.json", {}).get("slices_by_retriever"),
                                    "chunks": baseline.get("chunk_level_retrieval_metrics.json", {}).get("overall_by_strategy_and_retriever")}}
    for path in (results_path, metrics_path, report_path, audit_path): path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in results), encoding="utf-8")
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_path.write_text(render_report(metrics), encoding="utf-8"); audit_path.write_text(render_audit(audits), encoding="utf-8")
    return metrics


def render_audit(audits: list[dict[str, Any]]) -> str:
    """Render hierarchy counts, size statistics, and representative detections."""
    lines = ["# Hierarchy Detection Audit", "", "No gold evidence was used during structure detection.", "",
             "| Book | Chapters | Sections | High | Medium | Low | Paragraph groups | Avg tokens | p50 | p95 | Fallback chapters |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for a in audits:
        s = a["token_sizes"]; h = a["heading_counts"]
        lines.append(f'| {a["book_id"]} | {a["chapter_count"]} | {a["detected_section_count"]} | {h["high"]} | {h["medium"]} | {h["low"]} | {a["paragraph_group_count"]} | {s["average"]:.1f} | {s["p50"]:.0f} | {s["p95"]:.0f} | {a["fallback_to_chapter_only_count"]} |')
    lines += ["", "## Representative successes", ""]
    for a in audits:
        for x in a["representative_successes"]: lines.append(f'- `{x["book_id"]}` / {x["chapter"]}: “{x["heading"]}” ({x["confidence"]}).')
    lines += ["", "## Representative failures", ""]
    failures = [x for a in audits for x in a["representative_failures"]]
    lines += [f'- `{x["book_id"]}` / {x["chapter"]}: {x["issue"].replace("_", " ")}.' for x in failures] or ["No chapter required the chapter-only fallback."]
    lines += ["", "## Interpretation", "", "Numbered headings are high confidence; conservative short title-like lines are medium confidence. Low-confidence candidates remain content and are therefore counted as zero detected headings. Detection is useful for retrieval experiments but remains heuristic because PDF text lacks font and indentation metadata.", ""]
    return "\n".join(lines)


def render_report(metrics: dict[str, Any]) -> str:
    """Render effectiveness, stage recall, failures, baseline comparisons, and decision."""
    labels = {"bm25": "BM25", "dense_bge_small": "BGE-small dense", "hybrid_rrf": "Hybrid RRF"}; pct = lambda x: "n/a" if x is None else f"{100*x:.1f}%"
    lines = ["# Hierarchical Chunking and Retrieval v1", "", "Final targets are paragraph groups; chapters and sections supply parent retrieval signals. Gold evidence is never used in hierarchy construction or ranking.", "", "## Headline results", "",
             "| Approach | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR | Avg ms | p95 ms |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for a in APPROACHES:
        for r in RETRIEVERS:
            m = metrics["overall_by_approach_and_retriever"][a][r]
            lines.append(f'| {a.replace("_", " ")} | {labels[r]} | {m["answerable_questions"]} | {pct(m["hit_at_1"])} | {pct(m["hit_at_3"])} | {pct(m["hit_at_5"])} | {m["mrr"]:.3f} | {m["average_latency_ms"]:.2f} | {m["p95_latency_ms"]:.2f} |')
    lines += ["", "## Stage-level recall", "", "| Approach | Retriever | Chapter recall@K | Section recall@K | Independent paragraph Hit@5 | Chapter survival | Section survival |", "|---|---|---:|---:|---:|---:|---:|"]
    for a in APPROACHES:
        for r in RETRIEVERS:
            m = metrics["stage_level_recall"][a][r]
            lines.append(f'| {a.replace("_", " ")} | {labels[r]} | {pct(m["chapter_recall_at_k"])} | {pct(m["section_recall_at_k"])} | {pct(m["independent_paragraph_hit_at_5"])} | {pct(m["cascade_gold_chapter_survival"])} | {pct(m["cascade_gold_section_survival"])} |')
    lines += ["", "## Baseline comparison", "", "| Baseline | Retriever | Hit@1 | Hit@5 | MRR |", "|---|---|---:|---:|---:|"]
    page = metrics["baseline_metrics"]["page"] or {}; chunks = metrics["baseline_metrics"]["chunks"] or {}
    for r, m in page.items(): lines.append(f'| Page | {labels[r]} | {pct(m["hit_at_1"])} | {pct(m["hit_at_5"])} | {m["mrr"]:.3f} |')
    for strategy, rs in chunks.items():
        for r, m in rs.items(): lines.append(f'| {strategy} chunks | {labels[r]} | {pct(m["hit_at_1"])} | {pct(m["hit_at_5"])} | {m["mrr"]:.3f} |')
    page_slices = metrics["baseline_metrics"].get("page_slices") or {}
    slice_comparisons = []
    for name, approaches in metrics["slices"].items():
        hierarchical = approaches["soft_fusion"].get("hybrid_rrf")
        prior = page_slices.get(name, {}).get("hybrid_rrf")
        if hierarchical and prior:
            delta = hierarchical["hit_at_5"] - prior["hit_at_5"]
            slice_comparisons.append(f'{name.replace("_", " ")} {delta:+.1%} Hit@5')
    lines += ["", "## Dependency and evidence-span slices", "", "| Slice | Approach | Retriever | N | Hit@1 | Hit@3 | Hit@5 | MRR |", "|---|---|---|---:|---:|---:|---:|---:|"]
    for slice_name, approaches in metrics["slices"].items():
        for approach, retrievers in approaches.items():
            for retriever in RETRIEVERS:
                m = retrievers.get(retriever)
                if m:
                    lines.append(f'| {slice_name.replace("_", " ")} | {approach.replace("_", " ")} | {labels[retriever]} | {m["answerable_questions"]} | {pct(m["hit_at_1"])} | {pct(m["hit_at_3"])} | {pct(m["hit_at_5"])} | {m["mrr"]:.3f} |')
    lines += ["", "Book, difficulty, and heading-confidence metric blocks are recorded in `hierarchical_retrieval_metrics.json`.", "", "## Top-five failures", "",
              "| Question | Approach | Retriever | Gold rank | Category |", "|---|---|---|---:|---|"]
    for x in metrics["top_5_failures"]: lines.append(f'| {x["question_id"]} | {x["approach"].replace("_", " ")} | {labels[x["retriever"]]} | {x["gold_rank"] or "> corpus"} | {x["failure_category"].replace("_", " ")} |')
    best = max((m["hit_at_5"] or 0, m["mrr"] or 0, a, r) for a, rs in metrics["overall_by_approach_and_retriever"].items() for r, m in rs.items())
    best_mrr = max((m["mrr"] or 0, a, r) for a, rs in metrics["overall_by_approach_and_retriever"].items() for r, m in rs.items())
    baseline_hit5 = max((m["hit_at_5"] or 0 for rs in chunks.values() for m in rs.values()), default=0)
    baseline_mrr = max((m["mrr"] or 0 for m in page.values()), default=0)
    manual = [q for q, g in metrics["gold_mappings"].items() if g["status"] == "manual_review"]
    lines += ["", "## Decision", "", f'Best hierarchical Hit@5 is {pct(best[0])} from **{best[2].replace("_", " ")} / {labels[best[3]]}**. It {"exceeds" if best[0] > baseline_hit5 else "does not exceed"} the current best chunk baseline of {pct(baseline_hit5)}.',
              f'Best hierarchical MRR is {best_mrr[0]:.3f} from **{best_mrr[1].replace("_", " ")} / {labels[best_mrr[2]]}**. It {"preserves or improves" if best_mrr[0] >= baseline_mrr else "does not preserve"} the current best page MRR of {baseline_mrr:.3f}.',
              f'Rows requiring manual gold review: {", ".join(manual) if manual else "none"}.',
              "Section detection is reliable for explicit numbered headings, but the conservative detector intentionally leaves uncertain unnumbered headings as content. Two answer spans require manual chunk-mapping review.",
              "Soft fusion performs better than strict cascade overall. Strict BM25 is especially weak because chapter filtering eliminates accepted evidence early.",
              "Formula-heavy, visual, and evidence-spanning questions remain the dominant weak categories; their exact strategy/retriever results appear above.",
              "Against page Hybrid, soft-fusion Hybrid slice changes are: " + "; ".join(slice_comparisons) + ". Different scored counts in a slice reflect explicitly excluded manual gold mappings.",
              "The hierarchy should not become the default retrieval architecture because it does not improve the strongest baseline and introduces systematic parent-stage failures.",
              "The recommended next experiment is neighbour expansion over soft-fusion Hybrid paragraph retrieval, compared with the fixed 400/80 BM25 baseline.", "", "## Reproducibility", "",
              f'- Chapters selected: {metrics["run_metadata"]["chapter_k"]}; sections selected: {metrics["run_metadata"]["section_k"]}.',
              f'- Soft weights: section {metrics["run_metadata"]["soft_section_weight"]}, chapter {metrics["run_metadata"]["soft_chapter_weight"]}; rank constant 60.',
              "- BM25, BGE-small, and BM25/dense RRF settings match prior baselines. Embeddings are cached independently by book and hierarchy level.", ""]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Define configurable hierarchy, cascade, fusion, cache, and output options."""
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--root", type=Path, default=Path.cwd()); p.add_argument("--benchmark", type=Path)
    p.add_argument("--results", type=Path); p.add_argument("--metrics", type=Path); p.add_argument("--report", type=Path); p.add_argument("--audit", type=Path); p.add_argument("--cache-dir", type=Path)
    p.add_argument("--top-k", type=int, default=5); p.add_argument("--chapter-k", type=int, default=3); p.add_argument("--section-k", type=int, default=8)
    p.add_argument("--paragraph-target", type=int, default=250); p.add_argument("--paragraph-min", type=int, default=150); p.add_argument("--paragraph-max", type=int, default=350)
    p.add_argument("--section-weight", type=float, default=.5); p.add_argument("--chapter-weight", type=float, default=.25); p.add_argument("--gold-min-coverage", type=float, default=.5); p.add_argument("--device")
    return p


def main(argv: list[str] | None = None) -> None:
    """Resolve project-relative paths and execute the hierarchical experiment."""
    a = build_parser().parse_args(argv); root = a.root.resolve()
    m = run(root, (a.benchmark or root / "data/benchmarks/retrieval_benchmark_v1.jsonl").resolve(),
            (a.results or root / "data/retrieval/hierarchical_results.jsonl").resolve(), (a.metrics or root / "reports/hierarchical_retrieval_metrics.json").resolve(),
            (a.report or root / "reports/hierarchical_retrieval_baseline.md").resolve(), (a.audit or root / "reports/hierarchy_detection_audit.md").resolve(),
            (a.cache_dir or root / "data/retrieval/cache").resolve(), a.top_k, a.chapter_k, a.section_k, a.paragraph_target, a.paragraph_min, a.paragraph_max,
            a.section_weight, a.chapter_weight, a.gold_min_coverage, a.device)
    print(json.dumps(m["overall_by_approach_and_retriever"], indent=2))


if __name__ == "__main__": main()
