"""Phase E embedding bake-off on one front-matter-free fixed-chunk corpus.

The module changes only the embedding model between runs.  Chunk construction,
BM25, book scoping, gold-blind ranking, cosine similarity, and RRF remain fixed.
Gold evidence is consulted only after complete rankings have been produced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .candidate_complementarity import _scopes
from .candidate_compression import APPROVED_PLAN, RANDOM_SEED, _peak_memory_mb, metric_block
from .chunk_retrieval import derive_gold_chunks, fixed_chunks
from .experiment_tracking import (
    checkpoint_run, create_run_directory, experiment_paths, initialize_experiment,
    read_jsonl as read_run_log, render_resume, sha256_file, utc_now, write_json,
)
from .retrieval import BM25, load_pages, read_jsonl, reciprocal_rank_fusion, stable_ranking


RRF_CONSTANT = 60
MODEL_CONFIGS = {
    "bge_small": {
        "model_name": "BAAI/bge-small-en-v1.5",
        "revision": "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        "query_prefix": "Represent this sentence for searching relevant passages: ",
        "run_id": "phase_e_e0_bge_small_fixed_400_80_control",
    },
    "bge_m3_dense": {
        "model_name": "BAAI/bge-m3",
        "revision": "5617a9f61b028005a4858fdac845db406aefb181",
        # The current BGE-M3 model card specifies no query instruction.
        "query_prefix": "",
        "run_id": "phase_e_e1_bge_m3_dense_fixed_400_80",
    },
    "bge_m3_sparse": {
        "model_name": "BAAI/bge-m3",
        "revision": "5617a9f61b028005a4858fdac845db406aefb181",
        "query_prefix": "",
        "run_id": "phase_e_e2_bge_m3_sparse_and_fusion_fixed_400_80",
    },
    "nomic_full": {
        "model_name": "nomic-ai/nomic-embed-text-v1.5",
        "revision": "e9b6763023c676ca8431644204f50c2b100d9aab",
        "custom_code_revision": "7710840340a098cfb869c4f65e87cf2b1b70caca",
        "query_prefix": "search_query: ", "document_prefix": "search_document: ",
        "trust_remote_code": True, "truncate_dim": None,
        "run_id": "phase_e_e3_nomic_embed_v1_5_full_fixed_400_80",
    },
    "nomic_512": {
        "model_name": "nomic-ai/nomic-embed-text-v1.5",
        "revision": "e9b6763023c676ca8431644204f50c2b100d9aab",
        "custom_code_revision": "7710840340a098cfb869c4f65e87cf2b1b70caca",
        "query_prefix": "search_query: ", "document_prefix": "search_document: ",
        "trust_remote_code": True, "truncate_dim": 512,
        "derived_from_model_key": "nomic_full",
        "run_id": "phase_e_e4_nomic_embed_v1_5_512_fixed_400_80",
    },
    "e5_large_v2": {
        "model_name": "intfloat/e5-large-v2",
        "revision": "f169b11e22de13617baa190a028a32f3493550b6",
        "query_prefix": "query: ", "document_prefix": "passage: ",
        "trust_remote_code": False, "truncate_dim": None,
        "run_id": "phase_e_e5_e5_large_v2_fixed_400_80",
    },
}
RETRIEVERS = ("dense", "hybrid_rrf")


@dataclass(frozen=True)
class LoadedEmbeddingModel:
    """A pinned offline Sentence Transformer and its reproducibility metadata."""

    model: Any
    metadata: dict[str, Any]
    cold_load_ms: float
    warmup_ms: float
    model_size_bytes: int


def searchable_pages(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Load content pages and explicitly remove extraction-marked front matter."""
    books = load_pages(root)
    filtered: dict[str, list[dict[str, Any]]] = {}
    for book_id, pages in books.items():
        filtered[book_id] = [
            page for page in pages
            if "front_matter_or_cover" not in (page.get("extraction_notes") or [])
        ]
        if not filtered[book_id]:
            raise ValueError(f"front-matter filtering removed every {book_id} page")
    return filtered


def build_fixed_corpus(root: Path, target: int = 400,
                       overlap: int = 80) -> dict[str, list[dict[str, Any]]]:
    """Build the common deterministic 400/80 retrieval corpus in memory."""
    return {book_id: fixed_chunks(pages, target, overlap)
            for book_id, pages in searchable_pages(root).items()}


def corpus_fingerprint(chunks: list[dict[str, Any]]) -> str:
    """Hash chunk identity, text, and source pages for safe cache invalidation."""
    digest = hashlib.sha256()
    for chunk in chunks:
        payload = [chunk["chunk_id"], chunk["text"], chunk["pdf_pages"]]
        digest.update(json.dumps(payload, ensure_ascii=False,
                                 separators=(",", ":")).encode("utf-8"))
    return digest.hexdigest()


def _snapshot_path(cache_dir: Path, model_name: str, revision: str) -> Path:
    """Resolve an exact snapshot in the project or standard local HF cache."""
    repository = "models--" + model_name.replace("/", "--")
    candidates = [cache_dir / repository / "snapshots" / revision,
                  Path.home() / ".cache" / "huggingface" / "hub" /
                  repository / "snapshots" / revision]
    for path in candidates:
        if path.is_dir():
            return path
    raise FileNotFoundError("pinned embedding model is not cached in an approved "
                            "offline location: " + "; ".join(map(str, candidates)))


def _directory_size(path: Path) -> int:
    """Measure files beneath a model snapshot or generated index directory."""
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def load_local_model(config: dict[str, Any], cache_dir: Path, device: str,
                     batch_size: int) -> LoadedEmbeddingModel:
    """Load, warm, and describe a normalized dense encoder from pinned files."""
    snapshot = _snapshot_path(cache_dir, config["model_name"], config["revision"])
    # Nomic's auto-map points at a separately versioned code repository.  The
    # project cache is made authoritative before Transformers is imported so
    # custom code also resolves offline from its pinned snapshot/ref.
    os.environ["HF_HUB_CACHE"] = str(cache_dir.resolve())
    started = time.perf_counter()
    import sentence_transformers
    import torch
    import transformers
    from sentence_transformers import SentenceTransformer

    torch.manual_seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    # Loading the resolved directory, rather than a mutable Hub name, supports
    # the project's two cache roots while guaranteeing this exact commit.
    model = SentenceTransformer(
        str(snapshot), local_files_only=True, device=device,
        trust_remote_code=bool(config.get("trust_remote_code", False)),
    )
    cold_load_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    encode_options = ({"truncate_dim": int(config["truncate_dim"])}
                      if config.get("truncate_dim") else {})
    model.encode([config["query_prefix"] + "warm up"], batch_size=1,
                 convert_to_numpy=True, normalize_embeddings=True,
                 show_progress_bar=False, **encode_options)
    warmup_ms = (time.perf_counter() - started) * 1000
    dimension = int(config.get("truncate_dim") or model.get_embedding_dimension())
    metadata = {
        "model_name": config["model_name"],
        "requested_revision": config["revision"],
        "resolved_model_revision": config["revision"],
        "sentence_transformers_version": sentence_transformers.__version__,
        "transformers_version": transformers.__version__,
        "torch_version": torch.__version__, "device": str(model.device),
        "dimensions": dimension, "batch_size": batch_size,
        "normalized": True,
        "similarity": "cosine via dot product of L2-normalized vectors",
        "query_prefix": config["query_prefix"],
        "document_prefix": config.get("document_prefix", ""),
        "trust_remote_code": bool(config.get("trust_remote_code", False)),
        "custom_code_revision": config.get("custom_code_revision"),
        "local_files_only": True, "snapshot_path": str(snapshot),
    }
    return LoadedEmbeddingModel(model, metadata, cold_load_ms, warmup_ms,
                                _directory_size(snapshot))


def load_or_create_embeddings(
    loaded: LoadedEmbeddingModel, corpus: dict[str, list[dict[str, Any]]],
    index_dir: Path, model_key: str, batch_size: int,
    document_prefix: str = "", truncate_dim: int | None = None,
    derived_from_model_key: str | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Load valid normalized page vectors or encode and atomically cache them."""
    index_dir.mkdir(parents=True, exist_ok=True)
    matrices: dict[str, np.ndarray] = {}
    details: dict[str, Any] = {}
    for book_id, chunks in corpus.items():
        fingerprint = corpus_fingerprint(chunks)
        path = index_dir / f"{model_key}_{book_id}.npz"
        cache_hit = False
        started = time.perf_counter()
        if path.is_file():
            with np.load(path, allow_pickle=False) as stored:
                cache_hit = (
                    str(stored["corpus_fingerprint"].item()) == fingerprint
                    and str(stored["model_revision"].item())
                    == loaded.metadata["requested_revision"]
                    and int(stored["dimensions"].item())
                    == loaded.metadata["dimensions"]
                )
                if cache_hit:
                    matrices[book_id] = stored["embeddings"].astype(np.float32)
        if not cache_hit and truncate_dim and derived_from_model_key:
            source_path = index_dir / f"{derived_from_model_key}_{book_id}.npz"
            if source_path.is_file():
                with np.load(source_path, allow_pickle=False) as source:
                    if (str(source["corpus_fingerprint"].item()) == fingerprint
                            and source["embeddings"].shape[1] >= truncate_dim):
                        matrix = source["embeddings"].astype(np.float32)[:, :truncate_dim]
                        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
                        matrix = matrix / np.maximum(norms, np.finfo(np.float32).eps)
                        temporary = path.with_suffix(".tmp.npz")
                        np.savez_compressed(
                            temporary, embeddings=matrix,
                            corpus_fingerprint=np.asarray(fingerprint),
                            model_revision=np.asarray(loaded.metadata["requested_revision"]),
                            dimensions=np.asarray(loaded.metadata["dimensions"]),
                        )
                        temporary.replace(path)
                        matrices[book_id] = matrix
                        cache_hit = True
        if not cache_hit:
            # Page/chunk texts intentionally receive no query instruction.
            matrix = loaded.model.encode(
                [document_prefix + chunk["text"] for chunk in chunks], batch_size=batch_size,
                convert_to_numpy=True, normalize_embeddings=True,
                show_progress_bar=True,
                **({"truncate_dim": truncate_dim} if truncate_dim else {}),
            ).astype(np.float32)
            temporary = path.with_suffix(".tmp.npz")
            np.savez_compressed(
                temporary, embeddings=matrix,
                corpus_fingerprint=np.asarray(fingerprint),
                model_revision=np.asarray(loaded.metadata["requested_revision"]),
                dimensions=np.asarray(loaded.metadata["dimensions"]),
            )
            temporary.replace(path)
            matrices[book_id] = matrix
        details[book_id] = {
            "path": str(path), "cache_hit": cache_hit,
            "derived_from_model_key": (derived_from_model_key if cache_hit and
                                       truncate_dim and derived_from_model_key else None),
            "corpus_fingerprint_sha256": fingerprint,
            "chunk_count": len(chunks),
            "elapsed_ms": (time.perf_counter() - started) * 1000,
            "size_bytes": path.stat().st_size,
        }
    return matrices, details


def accepted_mapping(question: dict[str, Any], chunks: list[dict[str, Any]],
                     pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Map primary and reviewed alternative page evidence to accepted chunks."""
    enriched = dict(question)
    pdf_pages = {int(value) for value in question.get("gold_pdf_pages", [])}
    alternatives = {str(value) for value in question.get("alternative_gold_pages", [])}
    pdf_pages.update(int(page["pdf_page_number"]) for page in pages
                     if str(page.get("textbook_page_number")) in alternatives)
    enriched["gold_pdf_pages"] = sorted(pdf_pages)
    return derive_gold_chunks(enriched, chunks)


def _evaluation_scopes(questions: list[dict[str, Any]],
                       answerable: set[str]) -> dict[str, list[str]]:
    """Build all benchmark, book, dependency, style, and difficulty slices."""
    scopes = _scopes(questions, answerable)
    for difficulty in sorted({q.get("difficulty", "unknown") for q in questions
                              if q["question_id"] in answerable}):
        scopes[f"difficulty:{difficulty}"] = [
            q["question_id"] for q in questions
            if q["question_id"] in answerable
            and q.get("difficulty", "unknown") == difficulty
        ]
    return scopes


def summarize(rows: dict[str, dict[str, Any]],
              scopes: dict[str, list[str]]) -> dict[str, Any]:
    """Compute exact effectiveness and latency metrics for every fixed slice."""
    slices = {name: metric_block([rows[qid] for qid in ids])
              for name, ids in scopes.items()}
    return {"overall": slices["all_answerable"], "slices": slices,
            "top_five_miss_question_ids": [
                qid for qid in scopes["all_answerable"]
                if rows[qid]["first_gold_rank"] is None
                or rows[qid]["first_gold_rank"] > 5
            ]}


def select_retriever(metrics: dict[str, Any]) -> str:
    """Choose a model run's dense or hybrid variant by preregistered priorities."""
    def key(name: str) -> tuple[Any, ...]:
        """Build the natural-first deterministic comparison tuple."""
        natural = metrics[name]["slices"]["natural_student"]
        overall = metrics[name]["overall"]
        return (natural["hit_at_1_count"], natural["hit_at_3_count"],
                natural["hit_at_5_count"], natural["mrr"],
                overall["hit_at_1_count"], overall["mrr"],
                overall["hit_at_3_count"], overall["hit_at_5_count"], name)
    return max(metrics, key=key)


def _load_dense_m3_indexes(index_dir: Path,
                           corpus: dict[str, list[dict[str, Any]]]) -> dict[str, np.ndarray]:
    """Load the completed BGE-M3 dense indexes required for specialty fusion."""
    matrices = {}
    for book, chunks in corpus.items():
        path = index_dir / f"bge_m3_dense_{book}.npz"
        if not path.is_file():
            raise FileNotFoundError(f"BGE-M3 dense prerequisite is missing: {path}")
        with np.load(path, allow_pickle=False) as stored:
            if str(stored["corpus_fingerprint"].item()) != corpus_fingerprint(chunks):
                raise ValueError(f"BGE-M3 dense prerequisite has stale {book} corpus")
            matrices[book] = stored["embeddings"].astype(np.float32)
    return matrices


def _load_or_create_sparse_indexes(
    model: Any, corpus: dict[str, list[dict[str, Any]]], index_dir: Path,
    revision: str, batch_size: int,
) -> tuple[dict[str, list[dict[str, float]]], dict[str, Any]]:
    """Encode and cache BGE-M3 lexical weights once per book and fingerprint."""
    index_dir.mkdir(parents=True, exist_ok=True)
    indexes: dict[str, list[dict[str, float]]] = {}
    metadata = {}
    for book, chunks in corpus.items():
        path = index_dir / f"bge_m3_sparse_{book}.json"
        fingerprint = corpus_fingerprint(chunks)
        cache_hit = False
        started = time.perf_counter()
        if path.is_file():
            stored = json.loads(path.read_text(encoding="utf-8"))
            cache_hit = (stored.get("corpus_fingerprint_sha256") == fingerprint
                         and stored.get("model_revision") == revision)
            if cache_hit:
                indexes[book] = stored["lexical_weights"]
        if not cache_hit:
            encoded = model.encode(
                [chunk["text"] for chunk in chunks], batch_size=batch_size,
                max_length=512, return_dense=False, return_sparse=True,
                return_colbert_vecs=False,
            )
            weights = [{str(token): float(weight) for token, weight in row.items()}
                       for row in encoded["lexical_weights"]]
            write_json(path, {"model_revision": revision,
                              "corpus_fingerprint_sha256": fingerprint,
                              "lexical_weights": weights})
            indexes[book] = weights
        metadata[book] = {"path": str(path), "cache_hit": cache_hit,
                          "corpus_fingerprint_sha256": fingerprint,
                          "chunk_count": len(chunks),
                          "elapsed_ms": (time.perf_counter() - started) * 1000,
                          "size_bytes": path.stat().st_size}
    return indexes, metadata


def _sparse_scores(query_weights: dict[str, float],
                   documents: list[dict[str, float]]) -> np.ndarray:
    """Compute the official BGE-M3 lexical dot product for each document."""
    return np.asarray([
        sum(float(weight) * float(document.get(token, 0.0))
            for token, weight in query_weights.items())
        for document in documents
    ], dtype=np.float64)


def evaluate_sparse(
    model: Any, corpus: dict[str, list[dict[str, Any]]],
    pages: dict[str, list[dict[str, Any]]], sparse_indexes: dict[str, list[dict[str, float]]],
    dense_indexes: dict[str, np.ndarray], questions: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Evaluate sparse and cached dense/sparse/BM25 RRF combinations together."""
    methods = ("sparse", "sparse_bm25_rrf", "dense_sparse_rrf",
               "dense_sparse_bm25_rrf")
    answerable = {q["question_id"] for q in questions
                  if q.get("gold_pdf_pages") and (q.get("gold_answer_span") or "").strip()}
    scopes = _evaluation_scopes(questions, answerable)
    bm25 = {book: BM25(chunk["text"] for chunk in chunks)
            for book, chunks in corpus.items()}
    rows = {method: {} for method in methods}
    details = []
    mapped_answerable: set[str] = set()
    for question in questions:
        book = question["book_id"]
        chunks = corpus[book]
        mapping = accepted_mapping(question, chunks, pages[book])
        gold = set(mapping["primary"] + mapping["alternatives"])
        qid = question["question_id"]
        if qid in answerable and mapping["status"] == "mapped":
            mapped_answerable.add(qid)
        started = time.perf_counter()
        query = model.encode([question["question"]], batch_size=1, max_length=512,
                             return_dense=True, return_sparse=True,
                             return_colbert_vecs=False)
        sparse_scores = _sparse_scores(query["lexical_weights"][0], sparse_indexes[book])
        sparse_rank = stable_ranking(sparse_scores)
        dense_scores = dense_indexes[book] @ np.asarray(query["dense_vecs"][0])
        dense_rank = stable_ranking(dense_scores)
        lexical_rank = stable_ranking(bm25[book].scores(question["question"]))
        encode_ms = (time.perf_counter() - started) * 1000
        variants = {
            "sparse": (sparse_scores, sparse_rank),
            "sparse_bm25_rrf": (reciprocal_rank_fusion(
                [sparse_rank, lexical_rank], len(chunks), RRF_CONSTANT), None),
            "dense_sparse_rrf": (reciprocal_rank_fusion(
                [dense_rank, sparse_rank], len(chunks), RRF_CONSTANT), None),
            "dense_sparse_bm25_rrf": (reciprocal_rank_fusion(
                [dense_rank, sparse_rank, lexical_rank], len(chunks), RRF_CONSTANT), None),
        }
        detail = {"question_id": qid, "question": question["question"],
                  "book_id": book,
                  "benchmark_slice": question.get("benchmark_slice", "canonical"),
                  "gold_mapping": mapping, "retrievers": {}}
        for method, (scores, ranking) in variants.items():
            ranking = stable_ranking(scores) if ranking is None else ranking
            first = next((rank for rank, index in enumerate(ranking, 1)
                          if chunks[int(index)]["chunk_id"] in gold), None)
            rows[method][qid] = {"answerable": qid in answerable,
                                 "first_gold_rank": first, "latency_ms": encode_ms}
            detail["retrievers"][method] = {
                "latency_ms": encode_ms, "first_gold_rank": first,
                "ranking": [{"rank": rank, "score": float(scores[int(index)]),
                             "chunk_id": chunks[int(index)]["chunk_id"],
                             "pdf_pages": chunks[int(index)]["pdf_pages"],
                             "textbook_pages": chunks[int(index)]["textbook_pages"],
                             "text_snippet": " ".join(chunks[int(index)]["text"].split())[:500],
                             "matches_accepted_evidence": chunks[int(index)]["chunk_id"] in gold}
                            for rank, index in enumerate(ranking, 1)]}
        details.append(detail)
    metrics = {name: summarize(values, scopes) for name, values in rows.items()}
    recall = {"answerable_questions": len(answerable), "count": len(mapped_answerable),
              "recall": len(mapped_answerable) / len(answerable),
              "missing_question_ids": sorted(answerable - mapped_answerable),
              "required_invariant_satisfied": mapped_answerable == answerable}
    return metrics, details, recall


def evaluate(
    loaded: LoadedEmbeddingModel, config: dict[str, Any],
    corpus: dict[str, list[dict[str, Any]]], pages: dict[str, list[dict[str, Any]]],
    matrices: dict[str, np.ndarray], questions: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Rank each book-local corpus with dense cosine and fixed BM25+dense RRF."""
    answerable = {q["question_id"] for q in questions
                  if q.get("gold_pdf_pages") and (q.get("gold_answer_span") or "").strip()}
    scopes = _evaluation_scopes(questions, answerable)
    bm25 = {book: BM25(chunk["text"] for chunk in chunks)
            for book, chunks in corpus.items()}
    rows = {retriever: {} for retriever in RETRIEVERS}
    details = []
    mapped_answerable: set[str] = set()
    for question in questions:
        book = question["book_id"]
        chunks = corpus[book]
        mapping = accepted_mapping(question, chunks, pages[book])
        gold = set(mapping["primary"] + mapping["alternatives"])
        if question["question_id"] in answerable and mapping["status"] == "mapped":
            mapped_answerable.add(question["question_id"])
        started = time.perf_counter()
        query = loaded.model.encode(
            [config["query_prefix"] + question["question"]],
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
            **({"truncate_dim": int(config["truncate_dim"])}
               if config.get("truncate_dim") else {}),
        )[0]
        dense_scores = matrices[book] @ query
        dense_ranking = stable_ranking(dense_scores)
        dense_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        lexical_scores = bm25[book].scores(question["question"])
        lexical_ranking = stable_ranking(lexical_scores)
        fusion_scores = reciprocal_rank_fusion(
            [lexical_ranking, dense_ranking], len(chunks), RRF_CONSTANT)
        hybrid_ranking = stable_ranking(fusion_scores)
        hybrid_ms = dense_ms + (time.perf_counter() - started) * 1000
        rankings = {
            "dense": (dense_scores, dense_ranking, dense_ms),
            "hybrid_rrf": (fusion_scores, hybrid_ranking, hybrid_ms),
        }
        detail = {
            "question_id": question["question_id"], "question": question["question"],
            "book_id": book,
            "benchmark_slice": question.get("benchmark_slice", "canonical"),
            "gold_mapping": mapping, "retrievers": {},
        }
        for retriever, (scores, ranking, latency_ms) in rankings.items():
            first = next((rank for rank, index in enumerate(ranking, 1)
                          if chunks[int(index)]["chunk_id"] in gold), None)
            rows[retriever][question["question_id"]] = {
                "answerable": question["question_id"] in answerable,
                "first_gold_rank": first, "latency_ms": latency_ms,
            }
            # Retain a full ranking so every result remains inspectable and new
            # cutoffs can be computed without rerunning a large embedding model.
            detail["retrievers"][retriever] = {
                "latency_ms": latency_ms, "first_gold_rank": first,
                "ranking": [{
                    "rank": rank, "score": float(scores[int(index)]),
                    "chunk_id": chunks[int(index)]["chunk_id"],
                    "pdf_pages": chunks[int(index)]["pdf_pages"],
                    "textbook_pages": chunks[int(index)]["textbook_pages"],
                    "chapter_title": chunks[int(index)].get("chapter_title"),
                    "section_title": chunks[int(index)].get("section_title"),
                    "text_snippet": " ".join(chunks[int(index)]["text"].split())[:500],
                    "matches_accepted_evidence": chunks[int(index)]["chunk_id"] in gold,
                } for rank, index in enumerate(ranking, 1)],
            }
        details.append(detail)
    metrics = {name: summarize(values, scopes) for name, values in rows.items()}
    recall = {"answerable_questions": len(answerable),
              "count": len(mapped_answerable),
              "recall": len(mapped_answerable) / len(answerable),
              "missing_question_ids": sorted(answerable - mapped_answerable),
              "required_invariant_satisfied": mapped_answerable == answerable}
    return metrics, details, recall


def _render_report(root: Path) -> None:
    """Regenerate the compact Phase E comparison from immutable run records."""
    records = [r for r in read_run_log(experiment_paths(root)["runs"])
               if r["phase"] == "E"]
    lines = ["# Phase E — embedding model bake-off", "",
             "All runs use the same front-matter-free fixed 400/80 chunk corpus, "
             "book-local search, normalized embeddings, cosine similarity, and BM25 RRF.", "",
             "| Run | Selected | H@1 | H@3 | H@5 | MRR | Natural H@5 | p95 | Decision |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for record in records:
        metric = record["metrics"]["overall"]
        natural = record["metrics"]["natural_student"]
        lines.append(
            f'| `{record["run_id"]}` | {record["configuration"]["selected_retriever"]} | '
            f'{metric["hit_at_1_count"]}/61 | {metric["hit_at_3_count"]}/61 | '
            f'{metric["hit_at_5_count"]}/61 | {metric["mrr"]:.3f} | '
            f'{natural["hit_at_5_count"]}/20 | {record["latency"]["p95_ms"]:.1f} ms | '
            f'{record["decision"]} |')
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    gate = state.get("current_best_configurations", {}).get("phase_e_bge_gate")
    if gate:
        lines.extend(["", "## BGE-M3 stopping gate", "",
                      f'- Balanced control retained: `{gate["balanced_control"]}`.',
                      f'- Overall-quality frontier retained: `{gate["quality_frontier"]}`.',
                      "- BGE-M3 dense and sparse-alone are rejected as balanced choices; multi-vector escalation stopped on quality/latency grounds."])
    lines.extend(["", "Detailed dense and hybrid slice metrics and complete rankings are in each run directory.", ""])
    (root / "reports" / "experiments" / "phase_e_embedding_bakeoff.md").write_text(
        "\n".join(lines), encoding="utf-8")


def apply_bge_gate(root: Path) -> dict[str, Any]:
    """Persist the successive-stopping decision after all approved BGE-M3 modes."""
    paths = experiment_paths(root)
    records = {record["run_id"]: record for record in read_run_log(paths["runs"])}
    required = [MODEL_CONFIGS[key]["run_id"]
                for key in ("bge_small", "bge_m3_dense", "bge_m3_sparse")]
    missing = [run_id for run_id in required if run_id not in records]
    if missing:
        raise FileNotFoundError("BGE gate requires completed runs: " + ", ".join(missing))
    state = json.loads(paths["state"].read_text(encoding="utf-8"))
    best = state.setdefault("current_best_configurations", {})
    best["phase_e_bge_gate"] = {
        "balanced_control": MODEL_CONFIGS["bge_small"]["run_id"],
        "quality_frontier": "phase_e_e2 dense_sparse_bm25_rrf variant",
        "rejected_balanced": [MODEL_CONFIGS["bge_m3_dense"]["run_id"],
                              "phase_e_e2 sparse selected variant"],
        "stopped": ["BGE-M3 multi-vector/ColBERT escalation"],
        "reason": ("Three-way BGE-M3 improves overall Hit@3/5 but loses one natural Hit@1 "
                   "and is about 13x slower; dense and sparse-alone reduce natural Hit@5."),
    }
    for name in ("bge_m3_dense_balanced", "bge_m3_sparse_balanced",
                 "bge_m3_multivector_escalation"):
        if name not in state["rejected_configurations"]:
            state["rejected_configurations"].append(name)
    frontier = "bge_m3_dense_sparse_bm25_rrf_quality_frontier"
    if frontier not in state["retained_configurations"]:
        state["retained_configurations"].append(frontier)
    state["exact_next_action"] = ("Acquire a pinned nomic-ai/nomic-embed-text-v1.5 snapshot, "
                                  "then run full and 512-dimensional retrieval successively.")
    write_json(paths["state"], state)
    marker = "## Phase E BGE-M3 successive-stopping gate"
    decisions = paths["decisions"].read_text(encoding="utf-8")
    if marker not in decisions:
        with paths["decisions"].open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                f"{marker}\n\n- Retain BGE-small hybrid as the balanced control.\n"
                "- Retain BGE-M3 dense+sparse+BM25 only on the overall-quality frontier: "
                "15/39/44 overall and 3/10/13 natural at p95 719 ms.\n"
                "- Reject BGE-M3 dense/sparse as balanced choices and stop multi-vector: "
                "natural quality does not improve and latency rises materially.\n"
                "- Next: acquire and test the approved Nomic embedding.\n\n")
    render_resume(root, state)
    _render_report(root)
    return state


def finalize_phase_e(root: Path) -> dict[str, Any]:
    """Select the two-model embedding Pareto set and advance the loop to Phase F."""
    paths = experiment_paths(root)
    records = {record["run_id"]: record for record in read_run_log(paths["runs"])}
    required_keys = ("bge_small", "bge_m3_dense", "bge_m3_sparse",
                     "nomic_full", "nomic_512", "e5_large_v2")
    missing = [MODEL_CONFIGS[key]["run_id"] for key in required_keys
               if MODEL_CONFIGS[key]["run_id"] not in records]
    if missing:
        raise FileNotFoundError("Phase E finalization requires completed runs: " + ", ".join(missing))
    state = json.loads(paths["state"].read_text(encoding="utf-8"))
    state["current_phase"] = "Phase F — Chunking and multi-granularity retrieval"
    best = state.setdefault("current_best_configurations", {})
    best["phase_e"] = {
        "retained_embeddings": [
            {"role": "lightweight_and_balanced", "model_key": "bge_small",
             "run_id": MODEL_CONFIGS["bge_small"]["run_id"],
             "retriever": "hybrid_rrf", "dimensions": 384},
            {"role": "quality", "model_key": "e5_large_v2",
             "run_id": MODEL_CONFIGS["e5_large_v2"]["run_id"],
             "retrievers": ["dense", "hybrid_rrf"], "dimensions": 1024},
        ],
        "rejected_embeddings": ["bge_m3_dense", "bge_m3_sparse",
                                "nomic_full", "nomic_512"],
        "selection_reason": ("BGE-small preserves the best latency-balanced natural quality. "
                             "E5 supplies the strongest overall Hit@1/MRR and hybrid Hit@5; "
                             "Nomic's natural Hit@3 niche is insufficient to retain a third model."),
    }
    for name in ("bge_small_hybrid_phase_e", "e5_large_v2_quality_embedding"):
        if name not in state["retained_configurations"]:
            state["retained_configurations"].append(name)
    for name in ("nomic_full_embedding", "nomic_512_embedding",
                 "bge_m3_embedding_family"):
        if name not in state["rejected_configurations"]:
            state["rejected_configurations"].append(name)
    state["unresolved_questions"] = [
        "Which approved chunking strategy best exploits E5-large-v2 without losing natural-student quality?",
        "Does the Phase F chunking winner transfer to the lightweight BGE-small embedding?",
    ]
    state["exact_next_action"] = ("Implement Phase F corpus variants, then compare them first with "
                                  "E5-large-v2 while holding retrieval and evaluation fixed.")
    write_json(paths["state"], state)
    marker = "## Phase E final embedding selection"
    decisions = paths["decisions"].read_text(encoding="utf-8")
    if marker not in decisions:
        with paths["decisions"].open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                f"{marker}\n\n- Retain BGE-small hybrid as lightweight/balanced: "
                "15/34/42 overall, 4/9/13 natural, p95 53 ms.\n"
                "- Retain E5-large-v2 as quality embedding: dense 22/35/46 with MRR 0.524; "
                "hybrid 21/37/49 and 3/10/16 natural, p95 about 461 ms.\n"
                "- Reject Nomic full/512 and BGE-M3 from Phase F; neither earns one of the "
                "two embedding slots on quality, natural performance, and runtime together.\n"
                "- Next: Phase F chunking search with E5 first, then BGE-small confirmation.\n\n")
    render_resume(root, state)
    _render_report(root)
    report = root / "reports" / "experiments" / "phase_e_embedding_bakeoff.md"
    with report.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            "\n## Final selection\n\n"
            "- Lightweight/balanced: BGE-small hybrid RRF.\n"
            "- Quality: E5-large-v2, retaining dense and BM25-hybrid operating points.\n"
            "- Rejected from Phase F: BGE-M3 and Nomic full/512.\n"
        )
    return state


def run_sparse(root: Path, benchmark_path: Path, config: dict[str, str],
               cache_dir: Path, index_dir: Path, device: str,
               batch_size: int) -> dict[str, Any]:
    """Run the reliable BGE-M3 sparse branch and all no-reencode fusions."""
    from FlagEmbedding import BGEM3FlagModel
    import FlagEmbedding

    snapshot = _snapshot_path(cache_dir, config["model_name"], config["revision"])
    started = time.perf_counter()
    model = BGEM3FlagModel(
        str(snapshot), normalize_embeddings=True, use_fp16=False,
        devices=device, batch_size=batch_size, query_max_length=512,
        passage_max_length=512, return_dense=True, return_sparse=True,
        return_colbert_vecs=False,
    )
    cold_load_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    model.encode(["warm up"], batch_size=1, max_length=32,
                 return_dense=True, return_sparse=True,
                 return_colbert_vecs=False)
    warmup_ms = (time.perf_counter() - started) * 1000
    questions = read_jsonl(benchmark_path)
    pages = searchable_pages(root)
    corpus = {book: fixed_chunks(book_pages, 400, 80)
              for book, book_pages in pages.items()}
    dense_indexes = _load_dense_m3_indexes(index_dir, corpus)
    sparse_indexes, index = _load_or_create_sparse_indexes(
        model, corpus, index_dir, config["revision"], batch_size)
    metrics_by_retriever, details, recall = evaluate_sparse(
        model, corpus, pages, sparse_indexes, dense_indexes, questions)
    selected = select_retriever(metrics_by_retriever)
    selected_metrics = metrics_by_retriever[selected]
    run_dir = create_run_directory(root, config["run_id"])
    details_path = run_dir / "rankings.jsonl"
    with details_path.open("w", encoding="utf-8", newline="\n") as handle:
        for detail in details:
            handle.write(json.dumps(detail, ensure_ascii=False) + "\n")
    metrics_path = run_dir / "metrics.json"
    configuration_path = run_dir / "configuration.json"
    write_json(metrics_path, {"selected_retriever": selected,
                              "retrievers": metrics_by_retriever,
                              "candidate_recall": recall})
    write_json(configuration_path, {
        "model_key": "bge_m3_sparse", **config,
        "selected_retriever": selected,
        "retrievers_evaluated": list(metrics_by_retriever),
        "chunking": {"strategy": "fixed", "target_tokens": 400,
                     "overlap_tokens": 80, "front_matter_excluded": True},
        "maximum_length": 512, "rrf_constant": RRF_CONSTANT,
        "search_scope": "corresponding book only", "index": index,
    })
    overall = selected_metrics["overall"]
    natural = selected_metrics["slices"]["natural_student"]
    record = {
        "run_id": config["run_id"], "timestamp": utc_now(), "phase": "E",
        "parent_run_id": MODEL_CONFIGS["bge_m3_dense"]["run_id"],
        "changed_variable": "BGE-M3 sparse output and rank fusion",
        "configuration": {"pipeline_name": f"bge_m3_{selected}",
                          "model_key": "bge_m3_sparse",
                          "selected_retriever": selected,
                          "retrievers_evaluated": list(metrics_by_retriever),
                          "fixed_chunk_target": 400, "fixed_chunk_overlap": 80,
                          "front_matter_excluded": True,
                          "maximum_length": 512, "rrf_constant": RRF_CONSTANT},
        "random_seed": RANDOM_SEED,
        "input_artifact_versions": {
            "benchmark_sha256": sha256_file(benchmark_path),
            "page_sha256": {book: sha256_file(root / "data" / "processed" / f"{book}_pages.jsonl")
                            for book in corpus},
            "corpus_fingerprints_sha256": {book: corpus_fingerprint(chunks)
                                            for book, chunks in corpus.items()},
            "dense_parent_run_id": MODEL_CONFIGS["bge_m3_dense"]["run_id"],
        },
        "model_revisions": {"embedding": {"model_name": config["model_name"],
            "requested_revision": config["revision"],
            "resolved_model_revision": config["revision"],
            "library": "FlagEmbedding", "library_version": getattr(FlagEmbedding, "__version__", "1.4.0"),
            "device": device, "batch_size": batch_size, "maximum_length": 512,
            "normalized_dense": True, "sparse_score": "lexical-weight dot product",
            "query_prefix": "", "document_prefix": "", "local_files_only": True,
            "snapshot_path": str(snapshot)}},
        "metrics": {"overall": overall,
                    "canonical": selected_metrics["slices"]["canonical"],
                    "natural_student": natural,
                    "all_retrievers": metrics_by_retriever},
        "latency": {"measurement": "warm joint dense+sparse query encoding and ranking",
                    "average_ms": overall["average_latency_ms"],
                    "p50_ms": overall["p50_latency_ms"],
                    "p95_ms": overall["p95_latency_ms"],
                    "maximum_ms": overall["maximum_latency_ms"],
                    "cold_model_load_ms": cold_load_ms, "warmup_ms": warmup_ms,
                    "index_build_or_load_ms": sum(v["elapsed_ms"] for v in index.values())},
        "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                        "measurement": "process peak working set"},
        "disk_index_size": {"embedding_index_bytes": sum(v["size_bytes"] for v in index.values()),
                            "model_snapshot_bytes": _directory_size(snapshot)},
        "candidate_recall": recall, "decision": "investigate",
        "concise_reason": "Sparse and fusion modes completed; apply the natural-quality/runtime gate.",
        "output_artifact_paths": [str(details_path.relative_to(root)),
                                  str(metrics_path.relative_to(root)),
                                  str(configuration_path.relative_to(root))],
        "reproduce_command": ("temp\\python-x64\\python.exe scripts\\run_embedding_bakeoff.py "
                              f"--model bge_m3_sparse --device {device} --batch-size {batch_size}"),
        "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__,
                             "platform": platform.platform(), "device": device},
    }
    checkpoint_run(root, record,
                   "Apply the BGE-M3 specialty stopping gate, then acquire the approved Nomic revision if justified.")
    _render_report(root)
    return record


def run(root: Path, benchmark_path: Path, model_key: str, cache_dir: Path,
        index_dir: Path, device: str = "cpu", batch_size: int = 8) -> dict[str, Any]:
    """Execute and checkpoint one approved embedding-model comparison run."""
    if model_key not in MODEL_CONFIGS:
        raise ValueError(f"unknown embedding model key: {model_key}")
    if not benchmark_path.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark_path}")
    config = MODEL_CONFIGS[model_key]
    # Preserve cache knowledge accumulated by prior phases; initialization's
    # cache argument is authoritative and must never erase those checkpoints.
    state_path = experiment_paths(root)["state"]
    existing_state = (json.loads(state_path.read_text(encoding="utf-8"))
                      if state_path.is_file() else {})
    initialize_experiment(root, APPROVED_PLAN, [config["run_id"]],
                          existing_state.get("model_cache_status", {}))
    history = {r["run_id"]: r for r in read_run_log(experiment_paths(root)["runs"])}
    if config["run_id"] in history:
        return history[config["run_id"]]
    if model_key == "bge_m3_sparse":
        return run_sparse(root, benchmark_path, config, cache_dir, index_dir,
                          device, batch_size)
    questions = read_jsonl(benchmark_path)
    pages = searchable_pages(root)
    corpus = {book: fixed_chunks(book_pages, 400, 80)
              for book, book_pages in pages.items()}
    loaded = load_local_model(config, cache_dir, device, batch_size)
    matrices, index = load_or_create_embeddings(
        loaded, corpus, index_dir, model_key, batch_size,
        document_prefix=config.get("document_prefix", ""),
        truncate_dim=config.get("truncate_dim"),
        derived_from_model_key=config.get("derived_from_model_key"))
    metrics_by_retriever, details, recall = evaluate(
        loaded, config, corpus, pages, matrices, questions)
    selected = select_retriever(metrics_by_retriever)
    selected_metrics = metrics_by_retriever[selected]
    run_dir = create_run_directory(root, config["run_id"])
    details_path = run_dir / "rankings.jsonl"
    with details_path.open("w", encoding="utf-8", newline="\n") as handle:
        for detail in details:
            handle.write(json.dumps(detail, ensure_ascii=False) + "\n")
    metrics_path = run_dir / "metrics.json"
    configuration_path = run_dir / "configuration.json"
    write_json(metrics_path, {"selected_retriever": selected,
                              "retrievers": metrics_by_retriever,
                              "candidate_recall": recall})
    write_json(configuration_path, {
        "model_key": model_key, **config, "selected_retriever": selected,
        "chunking": {"strategy": "fixed", "target_tokens": 400,
                     "overlap_tokens": 80, "front_matter_excluded": True},
        "rrf_constant": RRF_CONSTANT, "search_scope": "corresponding book only",
        "corpus_counts": {book: len(chunks) for book, chunks in corpus.items()},
        "index": index,
    })
    # The control establishes the refreshed reference.  A new model remains an
    # investigation until its quality/runtime is compared in the phase report.
    decision = "retain" if model_key == "bge_small" else "investigate"
    reason = ("Refreshed normalized BGE-small control on the corrected corpus."
              if model_key == "bge_small" else
              f"{config['model_name']} completed; compare quality and runtime with retained controls.")
    overall = selected_metrics["overall"]
    natural = selected_metrics["slices"]["natural_student"]
    record = {
        "run_id": config["run_id"], "timestamp": utc_now(), "phase": "E",
        "parent_run_id": None if model_key == "bge_small" else MODEL_CONFIGS["bge_small"]["run_id"],
        "changed_variable": "embedding model only",
        "configuration": {"pipeline_name": f"{model_key}_{selected}",
                          "model_key": model_key, "selected_retriever": selected,
                          "retrievers_evaluated": list(RETRIEVERS),
                          "fixed_chunk_target": 400, "fixed_chunk_overlap": 80,
                          "front_matter_excluded": True, "rrf_constant": RRF_CONSTANT},
        "random_seed": RANDOM_SEED,
        "input_artifact_versions": {
            "benchmark_sha256": sha256_file(benchmark_path),
            "page_sha256": {book: sha256_file(root / "data" / "processed" / f"{book}_pages.jsonl")
                            for book in corpus},
            "corpus_fingerprints_sha256": {book: corpus_fingerprint(chunks)
                                            for book, chunks in corpus.items()},
        },
        "model_revisions": {"embedding": loaded.metadata},
        "metrics": {"overall": overall,
                    "canonical": selected_metrics["slices"]["canonical"],
                    "natural_student": natural,
                    "all_retrievers": metrics_by_retriever},
        "latency": {"measurement": "warm per-query embedding and ranking",
                    "average_ms": overall["average_latency_ms"],
                    "p50_ms": overall["p50_latency_ms"],
                    "p95_ms": overall["p95_latency_ms"],
                    "maximum_ms": overall["maximum_latency_ms"],
                    "cold_model_load_ms": loaded.cold_load_ms,
                    "warmup_ms": loaded.warmup_ms,
                    "index_build_or_load_ms": sum(v["elapsed_ms"] for v in index.values())},
        "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                        "measurement": "process peak working set"},
        "disk_index_size": {"embedding_index_bytes": sum(v["size_bytes"] for v in index.values()),
                            "model_snapshot_bytes": loaded.model_size_bytes},
        "candidate_recall": recall, "decision": decision, "concise_reason": reason,
        "output_artifact_paths": [str(details_path.relative_to(root)),
                                  str(metrics_path.relative_to(root)),
                                  str(configuration_path.relative_to(root))],
        "reproduce_command": (f"temp\\python-x64\\python.exe scripts\\run_embedding_bakeoff.py "
                              f"--model {model_key} --device {device} --batch-size {batch_size}"),
        "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__,
                             "platform": platform.platform(), "device": device},
    }
    if model_key == "bge_small":
        next_action = "Run BGE-M3 dense on the identical fixed corpus."
    elif model_key == "nomic_full":
        next_action = "Run Nomic at 512 dimensions by deriving and renormalizing the cached full vectors."
    elif model_key == "nomic_512":
        next_action = "Apply the Nomic stopping gate, then acquire the approved e5-large-v2 revision if justified."
    elif model_key == "e5_large_v2":
        next_action = "Finalize the Phase E Pareto gate and advance only the best two embeddings to Phase F."
    else:
        next_action = "Apply the Phase E successive-stopping gate before testing sparse or larger embeddings."
    state = json.loads(state_path.read_text(encoding="utf-8"))
    cache_status = state.setdefault("model_cache_status", {})
    cache_status[model_key] = {"status": "cached", "revision": config["revision"],
                               "path": loaded.metadata["snapshot_path"]}
    write_json(state_path, state)
    checkpoint_run(root, record, next_action)
    _render_report(root)
    return record


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface for one resumable Phase E run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--benchmark", type=Path,
                        default=Path("data/benchmarks/retrieval_benchmark_v1.jsonl"))
    parser.add_argument("--model", choices=sorted(MODEL_CONFIGS))
    parser.add_argument("--apply-bge-gate", action="store_true",
                        help="record BGE-M3 stopping decisions after its runs")
    parser.add_argument("--finalize-phase-e", action="store_true",
                        help="select two embedding winners and advance to Phase F")
    parser.add_argument("--cache-dir", type=Path,
                        default=Path("data/retrieval/cache/models"))
    parser.add_argument("--index-dir", type=Path,
                        default=Path("data/retrieval/cache/experiments/phase_e"))
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=8)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Resolve project-relative paths, execute one run, and print its checkpoint."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    if args.apply_bge_gate:
        state = apply_bge_gate(root)
        print(json.dumps({"current_phase": state["current_phase"],
                          "exact_next_action": state["exact_next_action"]}, indent=2))
        return
    if args.finalize_phase_e:
        state = finalize_phase_e(root)
        print(json.dumps({"current_phase": state["current_phase"],
                          "exact_next_action": state["exact_next_action"]}, indent=2))
        return
    if not args.model:
        raise SystemExit("--model is required unless --apply-bge-gate is used")
    benchmark = args.benchmark if args.benchmark.is_absolute() else root / args.benchmark
    cache = args.cache_dir if args.cache_dir.is_absolute() else root / args.cache_dir
    index = args.index_dir if args.index_dir.is_absolute() else root / args.index_dir
    result = run(root, benchmark, args.model, cache, index,
                 args.device, args.batch_size)
    print(json.dumps({"run_id": result["run_id"], "decision": result["decision"],
                      "metrics": result["metrics"]}, indent=2))


if __name__ == "__main__":
    main()
