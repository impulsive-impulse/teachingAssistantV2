"""Query the selected local textbook retrieval and context pipeline.

The CLI uses the same ranking function and cached indexes as the measured
Phase G/H runs.  It accepts no benchmark labels and searches only the selected
book, so arbitrary student questions follow the evaluated production path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .chunking_bakeoff import build_corpora
from .context_assembly import assemble_context
from .embedding_bakeoff import (MODEL_CONFIGS, load_local_model,
                                load_or_create_embeddings, searchable_pages)
from .retrieval import BM25, stable_ranking
from .specialist_retrieval import (build_specialist_corpora,
                                   rank_combined_query)


PROFILES = ("lightweight", "balanced", "quality")
SPECIALIST_METHODS = ("formula_equation_context", "table_rows_with_headers",
                      "visual_caption_context")


def load_pipeline(root: Path, profile: str, device: str = "cpu",
                  batch_size: int = 16) -> dict[str, Any]:
    """Load the pinned BGE-small model, cached chunk index, and optional priors."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile: {profile}")
    pages = searchable_pages(root)
    chunks = build_corpora(root)["fixed_600_100"]
    config = MODEL_CONFIGS["bge_small"]
    if profile == "lightweight":
        return {"profile": profile, "config": None, "loaded": None,
                "chunks": chunks, "matrices": {}, "resources": {},
                "chunk_index": {}, "specialist_indexes": {}}
    model_cache = root / "data" / "retrieval" / "cache" / "models"
    phase_e_cache = root / "data" / "retrieval" / "cache" / "experiments" / "phase_e"
    loaded = load_local_model(config, model_cache, device, batch_size)
    matrices, chunk_index = load_or_create_embeddings(
        loaded, chunks, phase_e_cache, "phase_f_bge_small_fixed_600_100", batch_size)
    resources: dict[str, Any] = {}
    specialist_indexes: dict[str, Any] = {}
    if profile != "lightweight":
        specialist_corpora = build_specialist_corpora(pages)
        phase_h_cache = root / "data" / "retrieval" / "cache" / "experiments" / "phase_h"
        for method in SPECIALIST_METHODS:
            method_matrices, metadata = load_or_create_embeddings(
                loaded, specialist_corpora[method], phase_h_cache,
                f"phase_h_{method}", batch_size)
            resources[method] = specialist_corpora[method], method_matrices
            specialist_indexes[method] = metadata
    return {"profile": profile, "config": config, "loaded": loaded,
            "chunks": chunks, "matrices": matrices, "resources": resources,
            "chunk_index": chunk_index, "specialist_indexes": specialist_indexes}


def query_pipeline(pipeline: dict[str, Any], question: str, book_id: str,
                   top_k: int = 5, include_text: bool = False) -> dict[str, Any]:
    """Retrieve and overlap-merge evidence for one arbitrary student question."""
    if book_id not in pipeline["chunks"]:
        raise ValueError("book_id must be one of: " + ", ".join(pipeline["chunks"]))
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    chunks = pipeline["chunks"][book_id]
    resources = pipeline["resources"]
    child_bm25 = BM25(item["text"] for item in chunks)
    specialist_bm25 = {
        method: {book: BM25(item["text"] for item in documents)
                 for book, documents in corpora.items()}
        for method, (corpora, _) in resources.items()
    }
    if pipeline["profile"] == "lightweight":
        import time
        started = time.perf_counter()
        scores = child_bm25.scores(question)
        ranked = {"processed_query": question, "activated_specialists": [],
                  "scores": scores, "ranking": stable_ranking(scores),
                  "latency_ms": (time.perf_counter() - started) * 1000}
    else:
        ranked = rank_combined_query(
            question, book_id, pipeline["loaded"], pipeline["config"], chunks,
            pipeline["matrices"][book_id], resources, child_bm25, specialist_bm25)
    ranking = [int(index) for index in ranked["ranking"]]
    hits = []
    for rank, index in enumerate(ranking[:top_k], 1):
        chunk = chunks[index]
        hit = {"rank": rank, "score": float(ranked["scores"][index]),
               "chunk_id": chunk["chunk_id"], "pdf_pages": chunk["pdf_pages"],
               "textbook_pages": chunk["textbook_pages"],
               "chapter_title": chunk.get("chapter_title"),
               "section_title": chunk.get("section_title"),
               "text_snippet": " ".join(chunk["text"].split())[:500]}
        if include_text:
            hit["text"] = chunk["text"]
        hits.append(hit)
    # The selected production context always uses the measured five-candidate
    # overlap merge, independent of a smaller display top_k.
    segments = assemble_context("overlap_merge", ranking, chunks)
    context = [{key: value for key, value in segment.items() if key != "text"}
               | ({"text": segment["text"]} if include_text else
                  {"text_snippet": " ".join(segment["text"].split())[:1000]})
               for segment in segments]
    return {"question": question, "book_id": book_id,
            "profile": pipeline["profile"],
            "processed_query": ranked["processed_query"],
            "activated_specialists": ranked["activated_specialists"],
            "retrieval_latency_ms": ranked["latency_ms"],
            "retrieved": hits, "assembled_context": context,
            "model": (pipeline["loaded"].metadata if pipeline["loaded"] is not None
                      else {"model_name": None, "retriever": "BM25"}),
            "cache": {"chunks": pipeline["chunk_index"],
                      "specialists": pipeline["specialist_indexes"]}}


def main() -> None:
    """Provide a clear local CLI for querying any selected deployment profile."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--book-id", required=True,
                        choices=("biology", "physical_sciences"))
    parser.add_argument("--profile", choices=PROFILES, default="balanced")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--include-text", action="store_true")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    result = query_pipeline(load_pipeline(root, args.profile, args.device,
                                          args.batch_size),
                            args.question, args.book_id, args.top_k,
                            args.include_text)
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
