"""Phase F successive-narrowing chunking and multi-granularity experiments.

The broad screen uses deterministic BM25 so every approved corpus can be
compared cheaply.  Only finalists advance to the retained E5 embedding, which
prevents an uncontrolled embedding-by-chunking Cartesian product.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path
from typing import Any

import numpy as np

from .candidate_compression import APPROVED_PLAN, RANDOM_SEED, _peak_memory_mb, metric_block
from .chunk_retrieval import (TextPiece, _link_chunks, derive_gold_chunks,
                              fixed_chunks, make_chunk, page_pieces,
                              structured_chunks)
from .embedding_bakeoff import (MODEL_CONFIGS, accepted_mapping,
                                corpus_fingerprint, evaluate,
                                load_local_model, load_or_create_embeddings,
                                searchable_pages, select_retriever, summarize,
                                _evaluation_scopes)
from .experiment_tracking import (checkpoint_run, create_run_directory,
                                  experiment_paths, initialize_experiment,
                                  read_jsonl as read_run_log, render_resume,
                                  sha256_file, utc_now, write_json)
from .retrieval import (BM25, read_jsonl, reciprocal_rank_fusion,
                        stable_ranking, tokenize)


STRATEGIES = ("fixed_300_50", "fixed_400_80", "fixed_600_100",
              "fixed_400_80_headings", "paragraph_groups", "section_aware")
E5_PARENT_RUN = "phase_e_e5_e5_large_v2_fixed_400_80"
RRF_CONSTANT = 60
PARENT_PAGE_BUDGET = 20
WINDOW_TOKENS = 250
WINDOW_OVERLAP = 50
MULTI_GRANULARITY_METHODS = (
    "parent_page_child",
    "page_prior_rrf",
    "neighbor_expansion",
    "query_relevant_windows",
)


def paragraph_group_chunks(pages: list[dict[str, Any]],
                           target: int = 300) -> list[dict[str, Any]]:
    """Group boundary-respecting text pieces within one source page at a time."""
    chunks: list[dict[str, Any]] = []
    for page in pages:
        pending: list[TextPiece] = []
        count = 0
        for piece in page_pieces(page, target):
            piece_tokens = len(tokenize(piece.text))
            if pending and count + piece_tokens > target:
                chunks.append(make_chunk(page["book_id"], "paragraph_groups",
                                         len(chunks), pending))
                pending, count = [], 0
            pending.append(piece)
            count += piece_tokens
        if pending:
            chunks.append(make_chunk(page["book_id"], "paragraph_groups",
                                     len(chunks), pending))
    return _link_chunks(chunks)


def prepend_headings(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy fixed chunks and prepend available chapter/section retrieval text."""
    output = []
    for chunk in chunks:
        headings = [f'Chapter: {chunk["chapter_title"]}'
                    if chunk.get("chapter_title") else ""]
        if chunk.get("section_title"):
            headings.append(f'Section: {chunk["section_title"]}')
        text = "\n".join(value for value in headings if value)
        text = f"{text}\n{chunk['text']}" if text else chunk["text"]
        output.append({**chunk, "chunking_strategy": "fixed_400_80_headings",
                       "chunk_id": chunk["chunk_id"].replace(":fixed:", ":fixed_headings:"),
                       "text": text, "token_count": len(tokenize(text))})
    return _link_chunks(output)


def build_corpora(root: Path) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Build all approved base chunk corpora from front-matter-free pages."""
    pages = searchable_pages(root)
    corpora = {strategy: {} for strategy in STRATEGIES}
    for book, book_pages in pages.items():
        fixed_400 = fixed_chunks(book_pages, 400, 80)
        corpora["fixed_300_50"][book] = fixed_chunks(book_pages, 300, 50)
        corpora["fixed_400_80"][book] = fixed_400
        corpora["fixed_600_100"][book] = fixed_chunks(book_pages, 600, 100)
        corpora["fixed_400_80_headings"][book] = prepend_headings(fixed_400)
        corpora["paragraph_groups"][book] = paragraph_group_chunks(book_pages)
        corpora["section_aware"][book] = structured_chunks(book_pages, 250, 500)
    return corpora


def page_documents(pages: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Adapt searchable pages to the common cache and ranking document schema."""
    output: dict[str, list[dict[str, Any]]] = {}
    for book, book_pages in pages.items():
        output[book] = [{
            "chunk_id": f'{book}:page:{int(page["pdf_page_number"]):04d}',
            "book_id": book,
            "text": page["cleaned_text"],
            "pdf_pages": [int(page["pdf_page_number"])],
            "textbook_pages": [page.get("textbook_page_number")],
            "chapter_title": page.get("chapter_title"),
            "section_title": page.get("section_title"),
        } for page in book_pages]
    return output


def _page_windows(page: dict[str, Any], book: str) -> list[dict[str, Any]]:
    """Create deterministic overlapping token windows within one source page."""
    words = page["cleaned_text"].split()
    step = WINDOW_TOKENS - WINDOW_OVERLAP
    windows = []
    for number, start in enumerate(range(0, max(len(words), 1), step)):
        text = " ".join(words[start:start + WINDOW_TOKENS]).strip()
        if not text:
            continue
        pdf_page = int(page["pdf_page_number"])
        windows.append({
            "chunk_id": f"{book}:query_window:{pdf_page:04d}:{number:03d}",
            "book_id": book,
            "text": text,
            "pdf_pages": [pdf_page],
            "textbook_pages": [page.get("textbook_page_number")],
            "chapter_title": page.get("chapter_title"),
            "section_title": page.get("section_title"),
            "window_number": number,
        })
        if start + WINDOW_TOKENS >= len(words):
            break
    return windows


def build_page_windows(pages: dict[str, list[dict[str, Any]]]) -> tuple[
        dict[str, list[dict[str, Any]]], dict[str, dict[int, list[int]]]]:
    """Build query-window candidates and indexes grouped by their source page."""
    corpora: dict[str, list[dict[str, Any]]] = {}
    by_page: dict[str, dict[int, list[int]]] = {}
    for book, book_pages in pages.items():
        corpora[book], by_page[book] = [], {}
        for page in book_pages:
            pdf_page = int(page["pdf_page_number"])
            for window in _page_windows(page, book):
                by_page[book].setdefault(pdf_page, []).append(len(corpora[book]))
                corpora[book].append(window)
    return corpora, by_page


def _rank_positions(ranking: np.ndarray) -> dict[int, int]:
    """Convert a ranking into one-based positions for deterministic fusion."""
    return {int(index): rank for rank, index in enumerate(ranking, 1)}


def lift_page_ranking(chunks: list[dict[str, Any]], page_docs: list[dict[str, Any]],
                      page_ranking: np.ndarray) -> np.ndarray:
    """Order child chunks by their best-ranked contributing parent page."""
    page_position = {
        int(page_docs[int(index)]["pdf_pages"][0]): rank
        for rank, index in enumerate(page_ranking, 1)
    }
    positions = np.asarray([
        min(page_position[int(page)] for page in chunk["pdf_pages"])
        for chunk in chunks
    ], dtype=np.int64)
    return np.lexsort((np.arange(len(chunks)), positions))


def expand_neighbor_ranking(ranking: np.ndarray,
                            chunks: list[dict[str, Any]]) -> np.ndarray:
    """Insert each retrieved child's immediate neighbours without duplicates."""
    by_id = {chunk["chunk_id"]: index for index, chunk in enumerate(chunks)}
    expanded: list[int] = []
    seen: set[int] = set()
    for raw_index in ranking:
        index = int(raw_index)
        candidates = [index]
        for field in ("previous_chunk_id", "next_chunk_id"):
            linked = chunks[index].get(field)
            if linked in by_id:
                candidates.append(by_id[linked])
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                expanded.append(candidate)
    return np.asarray(expanded, dtype=np.int64)


def select_page_windows(window_scores: np.ndarray,
                        windows: list[dict[str, Any]],
                        by_page: dict[int, list[int]]) -> dict[int, int]:
    """Select one highest-scoring lexical window per page with stable ties."""
    selected = {}
    for pdf_page, indexes in by_page.items():
        selected[pdf_page] = min(indexes, key=lambda index: (-window_scores[index], index))
    return selected


def _ranking_payload(ranking: np.ndarray, scores: np.ndarray,
                     candidates: list[dict[str, Any]], gold: set[str]) -> list[dict[str, Any]]:
    """Serialize a complete inspectable ranking with source metadata."""
    return [{
        "rank": rank,
        "score": float(scores[int(index)]),
        "chunk_id": candidates[int(index)]["chunk_id"],
        "pdf_pages": candidates[int(index)]["pdf_pages"],
        "textbook_pages": candidates[int(index)]["textbook_pages"],
        "chapter_title": candidates[int(index)].get("chapter_title"),
        "section_title": candidates[int(index)].get("section_title"),
        "text_snippet": " ".join(candidates[int(index)]["text"].split())[:500],
        "matches_accepted_evidence": candidates[int(index)]["chunk_id"] in gold,
    } for rank, index in enumerate(ranking, 1)]


def evaluate_bm25(questions: list[dict[str, Any]],
                  pages: dict[str, list[dict[str, Any]]],
                  corpus: dict[str, list[dict[str, Any]]]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Rank one chunk corpus with book-local BM25 and evaluate after ranking."""
    answerable = {q["question_id"] for q in questions
                  if q.get("gold_pdf_pages") and (q.get("gold_answer_span") or "").strip()}
    scopes = _evaluation_scopes(questions, answerable)
    indexes = {book: BM25(chunk["text"] for chunk in chunks)
               for book, chunks in corpus.items()}
    rows: dict[str, dict[str, Any]] = {}
    details = []
    mapped = set()
    for question in questions:
        book = question["book_id"]
        chunks = corpus[book]
        mapping = accepted_mapping(question, chunks, pages[book])
        gold = set(mapping["primary"] + mapping["alternatives"])
        qid = question["question_id"]
        if qid in answerable and mapping["status"] == "mapped":
            mapped.add(qid)
        started = time.perf_counter()
        scores = indexes[book].scores(question["question"])
        ranking = stable_ranking(scores)
        latency = (time.perf_counter() - started) * 1000
        first = next((rank for rank, index in enumerate(ranking, 1)
                      if chunks[int(index)]["chunk_id"] in gold), None)
        rows[qid] = {"answerable": qid in answerable,
                     "first_gold_rank": first, "latency_ms": latency}
        details.append({"question_id": qid, "question": question["question"],
                        "book_id": book,
                        "benchmark_slice": question.get("benchmark_slice", "canonical"),
                        "gold_mapping": mapping, "first_gold_rank": first,
                        "latency_ms": latency,
                        "ranking": [{"rank": rank, "score": float(scores[int(index)]),
                                     "chunk_id": chunks[int(index)]["chunk_id"],
                                     "pdf_pages": chunks[int(index)]["pdf_pages"],
                                     "textbook_pages": chunks[int(index)]["textbook_pages"],
                                     "text_snippet": " ".join(chunks[int(index)]["text"].split())[:500],
                                     "matches_accepted_evidence": chunks[int(index)]["chunk_id"] in gold}
                                    for rank, index in enumerate(ranking, 1)]})
    slices = {name: metric_block([rows[qid] for qid in ids])
              for name, ids in scopes.items()}
    metrics = {"overall": slices["all_answerable"], "slices": slices,
               "top_five_miss_question_ids": [qid for qid in scopes["all_answerable"]
                                                if rows[qid]["first_gold_rank"] is None
                                                or rows[qid]["first_gold_rank"] > 5]}
    recall = {"answerable_questions": len(answerable), "count": len(mapped),
              "recall": len(mapped) / len(answerable),
              "missing_question_ids": sorted(answerable - mapped),
              "required_invariant_satisfied": mapped == answerable}
    return metrics, details, recall


def evaluate_multi_granularity(
    loaded: Any,
    model_config: dict[str, Any],
    questions: list[dict[str, Any]],
    pages: dict[str, list[dict[str, Any]]],
    chunks: dict[str, list[dict[str, Any]]],
    chunk_matrices: dict[str, np.ndarray],
    page_docs: dict[str, list[dict[str, Any]]],
    page_matrices: dict[str, np.ndarray],
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Evaluate approved parent/child, page-prior, neighbour, and window methods."""
    answerable = {q["question_id"] for q in questions
                  if q.get("gold_pdf_pages") and (q.get("gold_answer_span") or "").strip()}
    scopes = _evaluation_scopes(questions, answerable)
    child_bm25 = {book: BM25(item["text"] for item in corpus)
                  for book, corpus in chunks.items()}
    parent_bm25 = {book: BM25(item["text"] for item in corpus)
                   for book, corpus in page_docs.items()}
    windows, windows_by_page = build_page_windows(pages)
    window_bm25 = {book: BM25(item["text"] for item in corpus)
                   for book, corpus in windows.items()}
    rows = {method: {} for method in MULTI_GRANULARITY_METHODS}
    details = {method: [] for method in MULTI_GRANULARITY_METHODS}
    candidate_hits = {method: set() for method in MULTI_GRANULARITY_METHODS}

    for question in questions:
        qid, book = question["question_id"], question["book_id"]
        book_chunks, book_pages = chunks[book], page_docs[book]
        child_mapping = accepted_mapping(question, book_chunks, pages[book])
        child_gold = set(child_mapping["primary"] + child_mapping["alternatives"])
        started = time.perf_counter()
        query = loaded.model.encode(
            [model_config["query_prefix"] + question["question"]],
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        child_dense = chunk_matrices[book] @ query
        child_dense_ranking = stable_ranking(child_dense)
        child_lexical = child_bm25[book].scores(question["question"])
        child_lexical_ranking = stable_ranking(child_lexical)
        child_hybrid = reciprocal_rank_fusion(
            [child_lexical_ranking, child_dense_ranking], len(book_chunks), RRF_CONSTANT)
        child_hybrid_ranking = stable_ranking(child_hybrid)
        parent_dense = page_matrices[book] @ query
        parent_dense_ranking = stable_ranking(parent_dense)
        parent_lexical = parent_bm25[book].scores(question["question"])
        parent_lexical_ranking = stable_ranking(parent_lexical)
        parent_hybrid = reciprocal_rank_fusion(
            [parent_lexical_ranking, parent_dense_ranking], len(book_pages), RRF_CONSTANT)
        parent_ranking = stable_ranking(parent_hybrid)
        common_ms = (time.perf_counter() - started) * 1000

        # Hard hierarchical retrieval searches children only under the top
        # parent pages. It is intentionally candidate-recall gated.
        started = time.perf_counter()
        top_parent_pages = {
            int(book_pages[int(index)]["pdf_pages"][0])
            for index in parent_ranking[:PARENT_PAGE_BUDGET]
        }
        eligible = np.asarray([
            int(index) for index in child_hybrid_ranking
            if top_parent_pages.intersection(int(p) for p in book_chunks[int(index)]["pdf_pages"])
        ], dtype=np.int64)
        parent_latency = common_ms + (time.perf_counter() - started) * 1000

        # A soft prior retains every child and adds the lifted parent ranking
        # as a third RRF signal, avoiding incomparable raw score scales.
        started = time.perf_counter()
        lifted = lift_page_ranking(book_chunks, book_pages, parent_ranking)
        prior_scores = reciprocal_rank_fusion(
            [child_lexical_ranking, child_dense_ranking, lifted],
            len(book_chunks), RRF_CONSTANT)
        prior_ranking = stable_ranking(prior_scores)
        prior_latency = common_ms + (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        neighbour_ranking = expand_neighbor_ranking(child_hybrid_ranking, book_chunks)
        # Scores are reciprocal output positions because expansion is an
        # ordering operation, not a new learned relevance score.
        neighbour_scores = np.zeros(len(book_chunks), dtype=np.float64)
        for rank, index in enumerate(neighbour_ranking, 1):
            neighbour_scores[int(index)] = 1.0 / rank
        neighbour_latency = common_ms + (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        lexical_window_scores = window_bm25[book].scores(question["question"])
        selected_windows = select_page_windows(
            lexical_window_scores, windows[book], windows_by_page[book])
        window_candidates = [windows[book][selected_windows[int(page["pdf_pages"][0])]]
                             for page in book_pages]
        window_scores = parent_hybrid.copy()
        window_ranking = parent_ranking.copy()
        window_mapping = accepted_mapping(question, window_candidates, pages[book])
        window_gold = set(window_mapping["primary"] + window_mapping["alternatives"])
        window_latency = common_ms + (time.perf_counter() - started) * 1000

        variants = {
            "parent_page_child": (eligible, child_hybrid, book_chunks, child_mapping,
                                  child_gold, parent_latency),
            "page_prior_rrf": (prior_ranking, prior_scores, book_chunks, child_mapping,
                               child_gold, prior_latency),
            "neighbor_expansion": (neighbour_ranking, neighbour_scores, book_chunks,
                                   child_mapping, child_gold, neighbour_latency),
            "query_relevant_windows": (window_ranking, window_scores, window_candidates,
                                       window_mapping, window_gold, window_latency),
        }
        for method, (ranking, scores, candidates, mapping, gold, latency) in variants.items():
            first = next((rank for rank, index in enumerate(ranking, 1)
                          if candidates[int(index)]["chunk_id"] in gold), None)
            rows[method][qid] = {"answerable": qid in answerable,
                                 "first_gold_rank": first, "latency_ms": latency}
            if qid in answerable and mapping["status"] == "mapped" and first is not None:
                candidate_hits[method].add(qid)
            details[method].append({
                "question_id": qid, "question": question["question"],
                "book_id": book,
                "benchmark_slice": question.get("benchmark_slice", "canonical"),
                "gold_mapping": mapping, "first_gold_rank": first,
                "latency_ms": latency,
                "ranking": _ranking_payload(ranking, scores, candidates, gold),
            })

    metrics = {method: summarize(method_rows, scopes)
               for method, method_rows in rows.items()}
    recalls = {}
    for method in MULTI_GRANULARITY_METHODS:
        hits = candidate_hits[method]
        recalls[method] = {
            "answerable_questions": len(answerable), "count": len(hits),
            "recall": len(hits) / len(answerable),
            "missing_question_ids": sorted(answerable - hits),
            "required_invariant_satisfied": hits == answerable,
        }
    return metrics, details, recalls


def _quality_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Rank completed corpora by natural quality, then overall quality and size."""
    natural = record["metrics"]["natural_student"]
    overall = record["metrics"]["overall"]
    configuration = record["configuration"]
    counts = configuration.get("corpus_counts")
    if counts:
        chunks = sum(counts.values())
    elif configuration.get("fixed_chunk_target") == 400:
        # Early Phase E run-log records predate corpus_counts, but their fixed
        # reviewed corpus is immutable and contains 249 + 295 chunks.
        chunks = 544
    else:
        chunks = 10**9
    return (natural["hit_at_1_count"], natural["hit_at_3_count"],
            natural["hit_at_5_count"], natural["mrr"],
            overall["hit_at_1_count"], overall["mrr"],
            overall["hit_at_3_count"], overall["hit_at_5_count"], -chunks)


def _render_report(root: Path, records: list[dict[str, Any]], finalists: list[str] | None = None,
                   e5_records: list[dict[str, Any]] | None = None,
                   multi_records: list[dict[str, Any]] | None = None,
                   bge_records: list[dict[str, Any]] | None = None) -> None:
    """Render the Phase F BM25 screen and its successive-narrowing decision."""
    lines = ["# Phase F — chunking and multi-granularity retrieval", "",
             "## BM25 base-corpus screen", "",
             "| Strategy | Chunks | H@1 | H@3 | H@5 | MRR | Natural H@1/3/5 | Mapping |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for record in records:
        overall = record["metrics"]["overall"]
        natural = record["metrics"]["natural_student"]
        counts = sum(record["configuration"]["corpus_counts"].values())
        recall = record["candidate_recall"]
        lines.append(f'| {record["configuration"]["strategy"]} | {counts} | '
                     f'{overall["hit_at_1_count"]}/61 | {overall["hit_at_3_count"]}/61 | '
                     f'{overall["hit_at_5_count"]}/61 | {overall["mrr"]:.3f} | '
                     f'{natural["hit_at_1_count"]}/{natural["hit_at_3_count"]}/{natural["hit_at_5_count"]} | '
                     f'{recall["count"]}/61 |')
    if finalists:
        lines.extend(["", "Finalists advancing to E5: " + ", ".join(f"`{x}`" for x in finalists) + "."])
    if e5_records:
        lines.extend(["", "## E5 finalist comparison", "",
                      "| Strategy | Selected | H@1 | H@3 | H@5 | MRR | Natural H@1/3/5 | p95 |",
                      "|---|---|---:|---:|---:|---:|---:|---:|"])
        for record in e5_records:
            overall = record["metrics"]["overall"]
            natural = record["metrics"]["natural_student"]
            lines.append(f'| {record["configuration"]["strategy"]} | '
                         f'{record["configuration"]["selected_retriever"]} | '
                         f'{overall["hit_at_1_count"]}/61 | {overall["hit_at_3_count"]}/61 | '
                         f'{overall["hit_at_5_count"]}/61 | {overall["mrr"]:.3f} | '
                         f'{natural["hit_at_1_count"]}/{natural["hit_at_3_count"]}/{natural["hit_at_5_count"]} | '
                         f'{record["latency"]["p95_ms"]:.1f} ms |')
    if multi_records:
        lines.extend(["", "## Multi-granularity comparison", "",
                      "| Method | H@1 | H@3 | H@5 | MRR | Natural H@1/3/5 | Candidate recall | p95 | Decision |",
                      "|---|---:|---:|---:|---:|---:|---:|---:|---|"])
        for record in multi_records:
            overall = record["metrics"]["overall"]
            natural = record["metrics"]["natural_student"]
            recall = record["candidate_recall"]
            lines.append(
                f'| {record["configuration"]["method"]} | '
                f'{overall["hit_at_1_count"]}/61 | {overall["hit_at_3_count"]}/61 | '
                f'{overall["hit_at_5_count"]}/61 | {overall["mrr"]:.3f} | '
                f'{natural["hit_at_1_count"]}/{natural["hit_at_3_count"]}/{natural["hit_at_5_count"]} | '
                f'{recall["count"]}/61 | {record["latency"]["p95_ms"]:.1f} ms | '
                f'{record["decision"]} |')
    if bge_records:
        lines.extend(["", "## BGE-small confirmation", "",
                      "| Method | H@1 | H@3 | H@5 | MRR | Natural H@1/3/5 | p95 | Decision |",
                      "|---|---:|---:|---:|---:|---:|---:|---|"])
        for record in bge_records:
            overall = record["metrics"]["overall"]
            natural = record["metrics"]["natural_student"]
            lines.append(
                f'| {record["configuration"]["method"]} | '
                f'{overall["hit_at_1_count"]}/61 | {overall["hit_at_3_count"]}/61 | '
                f'{overall["hit_at_5_count"]}/61 | {overall["mrr"]:.3f} | '
                f'{natural["hit_at_1_count"]}/{natural["hit_at_3_count"]}/{natural["hit_at_5_count"]} | '
                f'{record["latency"]["p95_ms"]:.1f} ms | {record["decision"]} |')
    lines.append("")
    (root / "reports" / "experiments" / "phase_f_chunking_bakeoff.md").write_text(
        "\n".join(lines), encoding="utf-8")


def run_bm25_screen(root: Path, benchmark_path: Path) -> dict[str, Any]:
    """Run/checkpoint all base corpora, then retain at most three E5 finalists."""
    if not benchmark_path.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark_path}")
    run_ids = [f"phase_f_f0_bm25_{strategy}" for strategy in STRATEGIES]
    state_path = experiment_paths(root)["state"]
    existing = json.loads(state_path.read_text(encoding="utf-8"))
    initialize_experiment(root, APPROVED_PLAN, run_ids,
                          existing.get("model_cache_status", {}))
    questions = read_jsonl(benchmark_path)
    pages = searchable_pages(root)
    corpora = build_corpora(root)
    history = {record["run_id"]: record
               for record in read_run_log(experiment_paths(root)["runs"])}
    for strategy in STRATEGIES:
        run_id = f"phase_f_f0_bm25_{strategy}"
        if run_id in history:
            continue
        metrics, details, recall = evaluate_bm25(questions, pages, corpora[strategy])
        run_dir = create_run_directory(root, run_id)
        details_path = run_dir / "rankings.jsonl"
        with details_path.open("w", encoding="utf-8", newline="\n") as handle:
            for detail in details:
                handle.write(json.dumps(detail, ensure_ascii=False) + "\n")
        metrics_path, config_path = run_dir / "metrics.json", run_dir / "configuration.json"
        configuration = {"pipeline_name": f"bm25_{strategy}", "strategy": strategy,
                         "retriever": "BM25", "front_matter_excluded": True,
                         "search_scope": "corresponding book only",
                         "corpus_counts": {book: len(chunks)
                                           for book, chunks in corpora[strategy].items()},
                         "corpus_fingerprints_sha256": {book: corpus_fingerprint(chunks)
                                                         for book, chunks in corpora[strategy].items()}}
        write_json(metrics_path, {"metrics": metrics, "candidate_recall": recall})
        write_json(config_path, configuration)
        overall = metrics["overall"]
        record = {"run_id": run_id, "timestamp": utc_now(), "phase": "F",
                  "parent_run_id": E5_PARENT_RUN,
                  "changed_variable": "chunking strategy only", "configuration": configuration,
                  "random_seed": RANDOM_SEED,
                  "input_artifact_versions": {"benchmark_sha256": sha256_file(benchmark_path),
                      "page_sha256": {book: sha256_file(root / "data" / "processed" / f"{book}_pages.jsonl")
                                      for book in pages}},
                  "model_revisions": {"embedding": "none in BM25 pre-screen"},
                  "metrics": {"overall": overall,
                              "canonical": metrics["slices"]["canonical"],
                              "natural_student": metrics["slices"]["natural_student"],
                              "all_slices": metrics["slices"]},
                  "latency": {"measurement": "warm BM25 scoring and sorting",
                              "average_ms": overall["average_latency_ms"],
                              "p50_ms": overall["p50_latency_ms"],
                              "p95_ms": overall["p95_latency_ms"],
                              "maximum_ms": overall["maximum_latency_ms"]},
                  "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                                  "measurement": "process peak working set"},
                  "disk_index_size": {"new_index_bytes": 0,
                                      "run_artifacts_bytes": 0},
                  "candidate_recall": recall, "decision": "investigate",
                  "concise_reason": "BM25 screen completed; select finalists only after all corpus rankings exist.",
                  "output_artifact_paths": [str(details_path.relative_to(root)),
                                            str(metrics_path.relative_to(root)),
                                            str(config_path.relative_to(root))],
                  "reproduce_command": "python scripts\\run_chunking_bakeoff.py --stage bm25_screen",
                  "runtime_versions": {"python": platform.python_version(),
                                       "numpy": np.__version__, "platform": platform.platform()}}
        checkpoint_run(root, record, "Complete all Phase F BM25 corpus screens.")
        history[run_id] = record
    records = [history[run_id] for run_id in run_ids]
    finalists = [record["configuration"]["strategy"]
                 for record in sorted(records, key=_quality_key, reverse=True)[:3]]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_best_configurations"]["phase_f_bm25_finalists"] = finalists
    state["exact_next_action"] = ("Encode and evaluate the Phase F BM25 finalists with retained E5-large-v2; "
                                  "do not encode eliminated corpora.")
    write_json(state_path, state)
    render_resume(root, state)
    _render_report(root, records, finalists)
    return {"finalists": finalists, "records": records}


def run_e5_finalists(root: Path, benchmark_path: Path, cache_dir: Path,
                     index_dir: Path, device: str, batch_size: int) -> dict[str, Any]:
    """Encode only BM25 finalists with E5 and checkpoint dense/hybrid results."""
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    finalists = list(state.get("current_best_configurations", {}).get(
        "phase_f_bm25_finalists", []))
    if not finalists:
        raise ValueError("run the Phase F BM25 screen before E5 finalists")
    questions = read_jsonl(benchmark_path)
    pages = searchable_pages(root)
    all_corpora = build_corpora(root)
    e5_config = MODEL_CONFIGS["e5_large_v2"]
    loaded = load_local_model(e5_config, cache_dir, device, batch_size)
    run_ids = [f"phase_f_f1_e5_{strategy}" for strategy in finalists]
    initialize_experiment(root, APPROVED_PLAN, run_ids,
                          state.get("model_cache_status", {}))
    history = {record["run_id"]: record
               for record in read_run_log(experiment_paths(root)["runs"])}
    for strategy in finalists:
        run_id = f"phase_f_f1_e5_{strategy}"
        if run_id in history:
            continue
        corpus = all_corpora[strategy]
        # The 400/80 finalist is byte-identical to Phase E and reuses that
        # index key. Other finalist corpora receive isolated fingerprinted keys.
        index_key = "e5_large_v2" if strategy == "fixed_400_80" else f"phase_f_e5_{strategy}"
        matrices, index = load_or_create_embeddings(
            loaded, corpus, index_dir, index_key, batch_size,
            document_prefix=e5_config["document_prefix"])
        metrics_by_retriever, details, recall = evaluate(
            loaded, e5_config, corpus, pages, matrices, questions)
        selected = select_retriever(metrics_by_retriever)
        selected_metrics = metrics_by_retriever[selected]
        run_dir = create_run_directory(root, run_id)
        details_path = run_dir / "rankings.jsonl"
        with details_path.open("w", encoding="utf-8", newline="\n") as handle:
            for detail in details:
                handle.write(json.dumps(detail, ensure_ascii=False) + "\n")
        metrics_path, config_path = run_dir / "metrics.json", run_dir / "configuration.json"
        configuration = {"pipeline_name": f"e5_{strategy}_{selected}",
                         "strategy": strategy, "embedding": "e5_large_v2",
                         "selected_retriever": selected,
                         "retrievers_evaluated": ["dense", "hybrid_rrf"],
                         "front_matter_excluded": True,
                         "corpus_counts": {book: len(chunks) for book, chunks in corpus.items()},
                         "index": index}
        write_json(metrics_path, {"selected_retriever": selected,
                                  "retrievers": metrics_by_retriever,
                                  "candidate_recall": recall})
        write_json(config_path, configuration)
        overall = selected_metrics["overall"]
        record = {"run_id": run_id, "timestamp": utc_now(), "phase": "F",
                  "parent_run_id": E5_PARENT_RUN,
                  "changed_variable": "chunking strategy only", "configuration": configuration,
                  "random_seed": RANDOM_SEED,
                  "input_artifact_versions": {"benchmark_sha256": sha256_file(benchmark_path),
                      "corpus_fingerprints_sha256": {book: corpus_fingerprint(chunks)
                                                      for book, chunks in corpus.items()}},
                  "model_revisions": {"embedding": loaded.metadata},
                  "metrics": {"overall": overall,
                              "canonical": selected_metrics["slices"]["canonical"],
                              "natural_student": selected_metrics["slices"]["natural_student"],
                              "all_retrievers": metrics_by_retriever},
                  "latency": {"measurement": "warm E5 query embedding and ranking",
                              "average_ms": overall["average_latency_ms"],
                              "p50_ms": overall["p50_latency_ms"],
                              "p95_ms": overall["p95_latency_ms"],
                              "maximum_ms": overall["maximum_latency_ms"],
                              "cold_model_load_ms": loaded.cold_load_ms,
                              "warmup_ms": loaded.warmup_ms,
                              "index_build_or_load_ms": sum(value["elapsed_ms"] for value in index.values())},
                  "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                                  "measurement": "process peak working set"},
                  "disk_index_size": {"embedding_index_bytes": sum(value["size_bytes"] for value in index.values()),
                                      "model_snapshot_bytes": loaded.model_size_bytes},
                  "candidate_recall": recall, "decision": "investigate",
                  "concise_reason": "E5 finalist completed; select the chunk winner after every finalist run.",
                  "output_artifact_paths": [str(details_path.relative_to(root)),
                                            str(metrics_path.relative_to(root)),
                                            str(config_path.relative_to(root))],
                  "reproduce_command": ("temp\\python-x64\\python.exe scripts\\run_chunking_bakeoff.py "
                                        f"--stage e5_finalists --device {device} --batch-size {batch_size}"),
                  "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__,
                                       "platform": platform.platform(), "device": device}}
        checkpoint_run(root, record, "Complete all retained E5 chunking finalists.")
        history[run_id] = record
    records = [history[run_id] for run_id in run_ids]
    winner = max(records, key=_quality_key)["configuration"]["strategy"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_best_configurations"]["phase_f_e5_base_chunk_winner"] = winner
    state["exact_next_action"] = (f"Use E5 with {winner} to test approved parent-page priors, neighbouring "
                                  "expansion, and query-relevant page windows successively.")
    write_json(state_path, state)
    render_resume(root, state)
    bm25_records = [history[f"phase_f_f0_bm25_{strategy}"] for strategy in STRATEGIES]
    _render_report(root, bm25_records, finalists, records)
    return {"winner": winner, "records": records}


def run_multi_granularity(root: Path, benchmark_path: Path, cache_dir: Path,
                          index_dir: Path, device: str,
                          batch_size: int) -> dict[str, Any]:
    """Run and checkpoint the approved Phase F multi-granularity methods."""
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    winner = state.get("current_best_configurations", {}).get(
        "phase_f_e5_base_chunk_winner")
    if winner != "fixed_600_100":
        raise ValueError("multi-granularity stage expects the completed fixed_600_100 E5 winner")
    if not benchmark_path.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark_path}")
    questions = read_jsonl(benchmark_path)
    pages = searchable_pages(root)
    page_corpus = page_documents(pages)
    child_corpus = build_corpora(root)[winner]
    config = MODEL_CONFIGS["e5_large_v2"]
    loaded = load_local_model(config, cache_dir, device, batch_size)
    child_matrices, child_index = load_or_create_embeddings(
        loaded, child_corpus, index_dir, "phase_f_e5_fixed_600_100",
        batch_size, document_prefix=config["document_prefix"])
    page_matrices, page_index = load_or_create_embeddings(
        loaded, page_corpus, index_dir, "phase_f_e5_pages",
        batch_size, document_prefix=config["document_prefix"])
    metrics, details, recalls = evaluate_multi_granularity(
        loaded, config, questions, pages, child_corpus, child_matrices,
        page_corpus, page_matrices)

    run_ids = [f"phase_f_f2_{method}" for method in MULTI_GRANULARITY_METHODS]
    initialize_experiment(root, APPROVED_PLAN, run_ids,
                          state.get("model_cache_status", {}))
    history = {record["run_id"]: record
               for record in read_run_log(experiment_paths(root)["runs"])}
    base = history["phase_f_f1_e5_fixed_600_100"]
    for method, run_id in zip(MULTI_GRANULARITY_METHODS, run_ids):
        if run_id in history:
            continue
        method_metrics = metrics[method]
        recall = recalls[method]
        configuration = {
            "pipeline_name": f"e5_fixed_600_100_{method}",
            "strategy": "fixed_600_100", "method": method,
            "embedding": "e5_large_v2", "front_matter_excluded": True,
            "book_local_search": True, "gold_blind_ranking": True,
            "parent_page_budget": (PARENT_PAGE_BUDGET
                                   if method == "parent_page_child" else None),
            "query_window_tokens": (WINDOW_TOKENS
                                    if method == "query_relevant_windows" else None),
            "query_window_overlap": (WINDOW_OVERLAP
                                     if method == "query_relevant_windows" else None),
            "corpus_counts": {book: len(corpus)
                              for book, corpus in child_corpus.items()},
            "child_index": child_index, "page_index": page_index,
        }
        provisional = {
            "configuration": configuration,
            "metrics": {"overall": method_metrics["overall"],
                        "natural_student": method_metrics["slices"]["natural_student"]},
        }
        if not recall["required_invariant_satisfied"]:
            decision = "reject"
            reason = (f"Candidate recall fell to {recall['count']}/61; the method "
                      "violates the evidence-preservation invariant.")
        elif _quality_key(provisional) > _quality_key(base):
            decision = "retain"
            reason = "Improved the preregistered natural-student-first quality ordering without losing evidence."
        else:
            decision = "reject"
            reason = "Did not improve the preregistered natural-student-first quality ordering over the base winner."
        run_dir = create_run_directory(root, run_id)
        details_path = run_dir / "rankings.jsonl"
        with details_path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in details[method]:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        metrics_path = run_dir / "metrics.json"
        config_path = run_dir / "configuration.json"
        write_json(metrics_path, {"metrics": method_metrics,
                                  "candidate_recall": recall})
        write_json(config_path, configuration)
        overall = method_metrics["overall"]
        record = {
            "run_id": run_id, "timestamp": utc_now(), "phase": "F",
            "parent_run_id": "phase_f_f1_e5_fixed_600_100",
            "changed_variable": method, "configuration": configuration,
            "random_seed": RANDOM_SEED,
            "input_artifact_versions": {
                "benchmark_sha256": sha256_file(benchmark_path),
                "child_corpus_fingerprints_sha256": {
                    book: corpus_fingerprint(corpus)
                    for book, corpus in child_corpus.items()},
                "page_corpus_fingerprints_sha256": {
                    book: corpus_fingerprint(corpus)
                    for book, corpus in page_corpus.items()},
            },
            "model_revisions": {"embedding": loaded.metadata},
            "metrics": {
                "overall": overall,
                "canonical": method_metrics["slices"]["canonical"],
                "natural_student": method_metrics["slices"]["natural_student"],
                "all_slices": method_metrics["slices"],
            },
            "latency": {
                "measurement": "warm E5 query plus child/page ranking and method transform",
                "average_ms": overall["average_latency_ms"],
                "p50_ms": overall["p50_latency_ms"],
                "p95_ms": overall["p95_latency_ms"],
                "maximum_ms": overall["maximum_latency_ms"],
                "cold_model_load_ms": loaded.cold_load_ms,
                "warmup_ms": loaded.warmup_ms,
            },
            "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                            "measurement": "process peak working set"},
            "disk_index_size": {
                "child_embedding_index_bytes": sum(v["size_bytes"] for v in child_index.values()),
                "page_embedding_index_bytes": sum(v["size_bytes"] for v in page_index.values()),
                "model_snapshot_bytes": loaded.model_size_bytes,
            },
            "candidate_recall": recall, "decision": decision,
            "concise_reason": reason,
            "output_artifact_paths": [str(details_path.relative_to(root)),
                                      str(metrics_path.relative_to(root)),
                                      str(config_path.relative_to(root))],
            "reproduce_command": ("temp\\python-x64\\python.exe scripts\\run_chunking_bakeoff.py "
                                  f"--stage multi_granularity --device {device} --batch-size {batch_size}"),
            "runtime_versions": {"python": platform.python_version(),
                                 "numpy": np.__version__, "platform": platform.platform(),
                                 "device": device},
        }
        checkpoint_run(root, record, "Complete all approved Phase F multi-granularity methods.")
        history[run_id] = record

    records = [history[run_id] for run_id in run_ids]
    eligible_records = [base] + [record for record in records
                                 if record["candidate_recall"]["required_invariant_satisfied"]]
    selected = max(eligible_records, key=_quality_key)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_best_configurations"]["phase_f_e5_retrieval_winner"] = {
        "run_id": selected["run_id"],
        "method": selected["configuration"].get("method", "base_hybrid_rrf"),
        "strategy": selected["configuration"]["strategy"],
    }
    state["unresolved_questions"] = [
        "Does the retained Phase F chunking choice transfer to the lightweight BGE-small embedding?",
        "Can deterministic query processing improve natural-student queries without canonical regressions?",
    ]
    state["exact_next_action"] = (
        "Confirm the Phase F fixed_600_100 choice with retained BGE-small only if needed, "
        "then finalize Phase F and advance to deterministic Phase G query processing."
    )
    write_json(state_path, state)
    render_resume(root, state)
    bm25_records = [history[f"phase_f_f0_bm25_{strategy}"] for strategy in STRATEGIES]
    finalists = state["current_best_configurations"]["phase_f_bm25_finalists"]
    e5_records = [history[f"phase_f_f1_e5_{strategy}"] for strategy in finalists]
    _render_report(root, bm25_records, finalists, e5_records, records)
    return {"winner": state["current_best_configurations"]["phase_f_e5_retrieval_winner"],
            "records": records}


def _confirmation_record(
    root: Path, run_id: str, parent_run_id: str, method: str,
    configuration: dict[str, Any], metrics: dict[str, Any],
    recall: dict[str, Any], details: list[dict[str, Any]], loaded: Any,
    benchmark_path: Path, index_bytes: int, decision: str, reason: str,
    device: str, batch_size: int,
) -> dict[str, Any]:
    """Persist one BGE confirmation result in the standard immutable schema."""
    run_dir = create_run_directory(root, run_id)
    details_path = run_dir / "rankings.jsonl"
    with details_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in details:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    metrics_path, config_path = run_dir / "metrics.json", run_dir / "configuration.json"
    write_json(metrics_path, {"metrics": metrics, "candidate_recall": recall})
    write_json(config_path, configuration)
    overall = metrics["overall"]
    record = {
        "run_id": run_id, "timestamp": utc_now(), "phase": "F",
        "parent_run_id": parent_run_id, "changed_variable": method,
        "configuration": configuration, "random_seed": RANDOM_SEED,
        "input_artifact_versions": {"benchmark_sha256": sha256_file(benchmark_path)},
        "model_revisions": {"embedding": loaded.metadata},
        "metrics": {"overall": overall, "canonical": metrics["slices"]["canonical"],
                    "natural_student": metrics["slices"]["natural_student"],
                    "all_slices": metrics["slices"]},
        "latency": {"measurement": "warm BGE-small query and ranking",
                    "average_ms": overall["average_latency_ms"],
                    "p50_ms": overall["p50_latency_ms"],
                    "p95_ms": overall["p95_latency_ms"],
                    "maximum_ms": overall["maximum_latency_ms"],
                    "cold_model_load_ms": loaded.cold_load_ms,
                    "warmup_ms": loaded.warmup_ms},
        "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                        "measurement": "process peak working set"},
        "disk_index_size": {"embedding_index_bytes": index_bytes,
                            "model_snapshot_bytes": loaded.model_size_bytes},
        "candidate_recall": recall, "decision": decision,
        "concise_reason": reason,
        "output_artifact_paths": [str(details_path.relative_to(root)),
                                  str(metrics_path.relative_to(root)),
                                  str(config_path.relative_to(root))],
        "reproduce_command": ("temp\\python-x64\\python.exe scripts\\run_chunking_bakeoff.py "
                              f"--stage bge_confirmation --device {device} --batch-size {batch_size}"),
        "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__,
                             "platform": platform.platform(), "device": device},
    }
    checkpoint_run(root, record, "Complete the BGE-small Phase F confirmation.")
    return record


def run_bge_confirmation(root: Path, benchmark_path: Path, cache_dir: Path,
                         index_dir: Path, device: str,
                         batch_size: int) -> dict[str, Any]:
    """Confirm only the E5 chunk/page-prior winners with lightweight BGE-small."""
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    e5_winner = state.get("current_best_configurations", {}).get(
        "phase_f_e5_retrieval_winner", {})
    if e5_winner.get("method") != "page_prior_rrf":
        raise ValueError("complete the E5 multi-granularity stage before BGE confirmation")
    if not benchmark_path.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark_path}")
    run_ids = ["phase_f_f3_bge_small_fixed_600_100",
               "phase_f_f4_bge_small_page_prior_rrf"]
    initialize_experiment(root, APPROVED_PLAN, run_ids,
                          state.get("model_cache_status", {}))
    history = {record["run_id"]: record
               for record in read_run_log(experiment_paths(root)["runs"])}
    questions = read_jsonl(benchmark_path)
    pages = searchable_pages(root)
    child_corpus = build_corpora(root)["fixed_600_100"]
    parents = page_documents(pages)
    config = MODEL_CONFIGS["bge_small"]
    loaded = load_local_model(config, cache_dir, device, batch_size)
    child_matrices, child_index = load_or_create_embeddings(
        loaded, child_corpus, index_dir, "phase_f_bge_small_fixed_600_100",
        batch_size, document_prefix=config.get("document_prefix", ""))
    page_matrices, page_index = load_or_create_embeddings(
        loaded, parents, index_dir, "phase_f_bge_small_pages",
        batch_size, document_prefix=config.get("document_prefix", ""))
    base_metrics_all, base_details, base_recall = evaluate(
        loaded, config, child_corpus, pages, child_matrices, questions)
    base_retriever = select_retriever(base_metrics_all)
    base_metrics = base_metrics_all[base_retriever]
    multi_metrics, multi_details, multi_recalls = evaluate_multi_granularity(
        loaded, config, questions, pages, child_corpus, child_matrices,
        parents, page_matrices)
    prior_metrics = multi_metrics["page_prior_rrf"]
    prior_recall = multi_recalls["page_prior_rrf"]
    control = history["phase_e_e0_bge_small_fixed_400_80_control"]
    corpus_counts = {book: len(corpus) for book, corpus in child_corpus.items()}

    if run_ids[0] not in history:
        base_config = {"pipeline_name": f"bge_small_fixed_600_100_{base_retriever}",
                       "strategy": "fixed_600_100", "method": base_retriever,
                       "embedding": "bge_small", "corpus_counts": corpus_counts,
                       "retrievers_evaluated": ["dense", "hybrid_rrf"],
                       "front_matter_excluded": True, "book_local_search": True}
        provisional = {"configuration": base_config,
                       "metrics": {"overall": base_metrics["overall"],
                                   "natural_student": base_metrics["slices"]["natural_student"]}}
        decision = "retain" if _quality_key(provisional) > _quality_key(control) else "reject"
        reason = ("Fixed 600/100 transfers the natural-student-first gain to BGE-small."
                  if decision == "retain" else
                  "Fixed 600/100 does not improve the existing BGE-small 400/80 control.")
        record = _confirmation_record(
            root, run_ids[0], control["run_id"], base_retriever, base_config,
            base_metrics, base_recall, base_details, loaded, benchmark_path,
            sum(v["size_bytes"] for v in child_index.values()), decision, reason,
            device, batch_size)
        history[run_ids[0]] = record

    if run_ids[1] not in history:
        prior_config = {"pipeline_name": "bge_small_fixed_600_100_page_prior_rrf",
                        "strategy": "fixed_600_100", "method": "page_prior_rrf",
                        "embedding": "bge_small", "corpus_counts": corpus_counts,
                        "front_matter_excluded": True, "book_local_search": True,
                        "gold_blind_ranking": True}
        provisional = {"configuration": prior_config,
                       "metrics": {"overall": prior_metrics["overall"],
                                   "natural_student": prior_metrics["slices"]["natural_student"]}}
        base_record = history[run_ids[0]]
        decision = ("retain" if prior_recall["required_invariant_satisfied"]
                    and _quality_key(provisional) > _quality_key(base_record) else "reject")
        reason = ("The page prior also improves BGE-small under the natural-student-first rule."
                  if decision == "retain" else
                  "The page prior does not transfer a quality gain to BGE-small.")
        record = _confirmation_record(
            root, run_ids[1], run_ids[0], "page_prior_rrf", prior_config,
            prior_metrics, prior_recall, multi_details["page_prior_rrf"], loaded,
            benchmark_path,
            sum(v["size_bytes"] for v in child_index.values())
            + sum(v["size_bytes"] for v in page_index.values()),
            decision, reason, device, batch_size)
        history[run_ids[1]] = record

    records = [history[run_id] for run_id in run_ids]
    eligible = [control] + [record for record in records
                            if record["candidate_recall"]["required_invariant_satisfied"]]
    lightweight = max(eligible, key=_quality_key)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_best_configurations"]["phase_f_lightweight_winner"] = {
        "run_id": lightweight["run_id"],
        "strategy": lightweight["configuration"].get("strategy", "fixed_400_80"),
        "method": lightweight["configuration"].get("method",
                                                      lightweight["configuration"].get("selected_retriever")),
    }
    state["current_phase"] = "Phase G — Query processing"
    state["unresolved_questions"] = [
        "Which deterministic query normalizations help natural-student wording without changing meaning?",
        "Does original-plus-expanded-query fusion avoid canonical regressions?",
    ]
    state["exact_next_action"] = (
        "Implement and screen approved deterministic Phase G query processing on the retained "
        "balanced pipeline; keep the original query in every fusion experiment."
    )
    write_json(state_path, state)
    render_resume(root, state)
    bm25_records = [history[f"phase_f_f0_bm25_{strategy}"] for strategy in STRATEGIES]
    finalists = state["current_best_configurations"]["phase_f_bm25_finalists"]
    e5_records = [history[f"phase_f_f1_e5_{strategy}"] for strategy in finalists]
    multi_records = [history[f"phase_f_f2_{method}"] for method in MULTI_GRANULARITY_METHODS]
    _render_report(root, bm25_records, finalists, e5_records, multi_records, records)
    return {"lightweight_winner": state["current_best_configurations"]["phase_f_lightweight_winner"],
            "records": records}


def build_parser() -> argparse.ArgumentParser:
    """Create the resumable Phase F command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--benchmark", type=Path,
                        default=Path("data/benchmarks/retrieval_benchmark_v1.jsonl"))
    parser.add_argument("--stage", choices=("bm25_screen", "e5_finalists",
                                             "multi_granularity", "bge_confirmation"),
                        default="bm25_screen")
    parser.add_argument("--cache-dir", type=Path,
                        default=Path("data/retrieval/cache/models"))
    parser.add_argument("--index-dir", type=Path,
                        default=Path("data/retrieval/cache/experiments/phase_e"))
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the requested Phase F stage and print its compact result."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    benchmark = args.benchmark if args.benchmark.is_absolute() else root / args.benchmark
    if args.stage == "bm25_screen":
        result = run_bm25_screen(root, benchmark)
        compact = {"finalists": result["finalists"]}
    elif args.stage == "e5_finalists":
        cache = args.cache_dir if args.cache_dir.is_absolute() else root / args.cache_dir
        index = args.index_dir if args.index_dir.is_absolute() else root / args.index_dir
        result = run_e5_finalists(root, benchmark, cache, index,
                                  args.device, args.batch_size)
        compact = {"winner": result["winner"]}
    elif args.stage == "multi_granularity":
        cache = args.cache_dir if args.cache_dir.is_absolute() else root / args.cache_dir
        index = args.index_dir if args.index_dir.is_absolute() else root / args.index_dir
        result = run_multi_granularity(root, benchmark, cache, index,
                                       args.device, args.batch_size)
        compact = {"winner": result["winner"]}
    else:
        cache = args.cache_dir if args.cache_dir.is_absolute() else root / args.cache_dir
        index = args.index_dir if args.index_dir.is_absolute() else root / args.index_dir
        result = run_bge_confirmation(root, benchmark, cache, index,
                                      args.device, args.batch_size)
        compact = {"lightweight_winner": result["lightweight_winner"]}
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
