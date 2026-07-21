"""Deterministic non-model artifact construction for accepted uploads."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from textbook_audit.chunk_retrieval import fixed_chunks
from textbook_audit.retrieval import BM25
from textbook_audit.specialist_retrieval import (
    formula_representation,
    table_representation,
    visual_caption_context,
)

from .models import ValidationResult
from .policy import RUNTIME_PROFILE_VERSION, IngestionPolicy


SPECIALIST_METHODS = {
    "formula": "formula_equation_context",
    "table": "table_rows_with_headers",
    "visual": "visual_caption_context",
}


class ArtifactBuilder:
    """Build the page, chunk, specialist, and lexical artifacts in staging."""

    def __init__(self, policy: IngestionPolicy):
        self.policy = policy

    def build_non_model_artifacts(
        self, result: ValidationResult, staging: Path, source_checksum: str
    ) -> dict[str, Any]:
        """Persist deterministic corpora and exercise all BM25 indexes.

        Dense matrices are intentionally a separate stage because they require
        the pinned model worker. The final book directory is not published by
        this method, so a crash cannot expose a partially indexed book.
        """

        staging.mkdir(parents=True, exist_ok=True)
        searchable = [page for page in result.pages if page.get("textbook_page_number") is not None]
        chunks = fixed_chunks(searchable, target=600, overlap=100)
        if len(chunks) < 5:
            raise ValueError("accepted textbook produced fewer than five fixed chunks")
        specialists = _specialist_corpora(searchable)

        _write_jsonl(staging / "pages.jsonl", result.pages)
        _write_json(staging / "chapter_map.json", {
            "mapping_method": result.page_mapping_method,
            "mapping_confidence": result.page_mapping_confidence,
            "content_pdf_offset": result.content_pdf_offset,
            "chapters": [asdict(chapter) for chapter in result.chapters],
        })
        _write_jsonl(staging / "chunks.jsonl", chunks)
        specialist_dir = staging / "specialists"
        for branch, documents in specialists.items():
            _write_jsonl(specialist_dir / f"{branch}.jsonl", documents)

        # BM25 is cheap and deterministic to reconstruct. Exercising one query
        # now proves every corpus is loadable before the model-heavy stage.
        bm25 = {"chunks": _exercise_bm25(chunks)}
        bm25.update({branch: _exercise_bm25(documents) for branch, documents in specialists.items()})
        _write_json(staging / "indexes" / "bm25_manifest.json", bm25)
        report = result.report(self.policy.to_dict())
        _write_json(staging / "processing_report.json", report)

        corpus_fingerprint = _jsonl_fingerprint(chunks)
        manifest = {
            "schema_version": 1,
            "book_id": result.pages[0]["book_id"],
            "title": result.title,
            "source_sha256": source_checksum,
            "ingestion_policy_version": self.policy.version,
            "runtime_profile_version": RUNTIME_PROFILE_VERSION,
            "retrieval_compatibility": {
                "profile": "Uploaded Textbook Runtime Profile derived from Retrieval Baseline v1",
                "benchmark_validated": False,
                "chunk_target_tokens": 600,
                "chunk_overlap_tokens": 100,
                "final_top_k": 5,
            },
            "book_specific_vocabulary": {
                "state": "not_available",
                "artifact": None,
            },
            "counts": {
                "pages": len(result.pages),
                "searchable_pages": result.searchable_page_count,
                "chapters": len(result.chapters),
                "chunks": len(chunks),
                "formula_documents": len(specialists["formula"]),
                "table_documents": len(specialists["table"]),
                "visual_documents": len(specialists["visual"]),
            },
            "corpus_fingerprint": corpus_fingerprint,
            "artifacts": {},
            "publication_state": "awaiting_dense_indexes",
        }
        for path in _durable_files(staging):
            relative = path.relative_to(staging).as_posix()
            manifest["artifacts"][relative] = {
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        _write_json(staging / "manifest.json", manifest)
        return manifest

    def build_dense_indexes(self, staging: Path, model_cache: Path, root: Path) -> dict[str, Any]:
        """Build normalized BGE matrices with the frozen model and cache format."""

        from textbook_audit.embedding_bakeoff import load_local_model, load_or_create_embeddings

        baseline = yaml.safe_load((root / "config" / "retrieval_baseline_v1.yaml").read_text(encoding="utf-8"))
        embedding = baseline["embedding"]
        model_config = {
            "model_name": embedding["model_name"],
            "revision": embedding["revision"],
            "query_prefix": embedding["query_prefix"],
            "document_prefix": embedding["document_prefix"],
            "trust_remote_code": embedding["trust_remote_code"],
        }
        loaded = load_local_model(model_config, model_cache, "cpu", embedding["batch_size"])
        if loaded.metadata["resolved_model_revision"] != embedding["revision"]:
            raise RuntimeError("resolved embedding revision differs from frozen baseline")
        book_id = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))["book_id"]
        corpora = {"chunks": _read_jsonl(staging / "chunks.jsonl")}
        corpora.update({
            branch: _read_jsonl(staging / "specialists" / f"{branch}.jsonl")
            for branch in SPECIALIST_METHODS
        })
        index_dir = staging / "indexes"
        details: dict[str, Any] = {"model": loaded.metadata, "corpora": {}}
        for branch, documents in corpora.items():
            if not documents:
                path = index_dir / f"{branch}.npz"
                path.parent.mkdir(parents=True, exist_ok=True)
                np.savez_compressed(
                    path,
                    embeddings=np.empty((0, int(embedding["dimensions"])), dtype=np.float32),
                    corpus_fingerprint=np.asarray(_jsonl_fingerprint([])),
                    model_revision=np.asarray(embedding["revision"]),
                    dimensions=np.asarray(embedding["dimensions"]),
                )
                details["corpora"][branch] = {"path": str(path), "chunk_count": 0, "cache_hit": False}
                continue
            matrices, metadata = load_or_create_embeddings(
                loaded,
                {book_id: documents},
                index_dir,
                branch,
                embedding["batch_size"],
                document_prefix=embedding["document_prefix"],
            )
            generated = index_dir / f"{branch}_{book_id}.npz"
            canonical = index_dir / f"{branch}.npz"
            generated.replace(canonical)
            matrix = matrices[book_id]
            if matrix.shape != (len(documents), int(embedding["dimensions"])):
                raise RuntimeError(f"{branch} embedding shape does not match its corpus")
            details["corpora"][branch] = {**metadata[book_id], "path": str(canonical)}
        _write_json(index_dir / "dense_manifest.json", details)
        return details

    def finalize_manifest(self, staging: Path) -> dict[str, Any]:
        """Verify every artifact and seal the manifest before atomic publication."""

        manifest_path = staging / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pages = _read_jsonl(staging / "pages.jsonl")
        chunks = _read_jsonl(staging / "chunks.jsonl")
        if [page["pdf_page_number"] for page in pages] != list(range(1, len(pages) + 1)):
            raise RuntimeError("processed PDF page numbering is not sequential")
        if len({chunk["chunk_id"] for chunk in chunks}) != len(chunks):
            raise RuntimeError("chunk identifiers are not unique")
        if any(len({page for page in chunk["pdf_pages"]}) != len(chunk["pdf_pages"]) for chunk in chunks):
            raise RuntimeError("chunk contains duplicate source pages")
        chapter_by_pdf = {page["pdf_page_number"]: page["chapter_number"] for page in pages}
        if any(
            not chunk["chapter_number"]
            or {chapter_by_pdf.get(page) for page in chunk["pdf_pages"]} != {chunk["chapter_number"]}
            for chunk in chunks
        ):
            raise RuntimeError("chunk crosses or lacks a chapter boundary")
        for branch in ("chunks", *SPECIALIST_METHODS):
            documents = chunks if branch == "chunks" else _read_jsonl(staging / "specialists" / f"{branch}.jsonl")
            with np.load(staging / "indexes" / f"{branch}.npz", allow_pickle=False) as stored:
                if stored["embeddings"].shape != (len(documents), 384):
                    raise RuntimeError(f"{branch} dense index does not match its corpus")
        if len(chunks) < 5:
            raise RuntimeError("retrieval health check requires at least five chunks")
        manifest["artifacts"] = {}
        for path in _durable_files(staging):
            manifest["artifacts"][path.relative_to(staging).as_posix()] = {
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
        manifest["publication_state"] = "verified"
        _write_json(manifest_path, manifest)
        return manifest


def _specialist_corpora(pages: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build the exact frozen winning representations while allowing empties."""

    output: dict[str, list[dict[str, Any]]] = {branch: [] for branch in SPECIALIST_METHODS}
    for page in pages:
        branch_text = {
            "formula": (
                formula_representation(page, include_context=True)
                if page.get("has_equation_like_text") else ""
            ),
            "table": (
                table_representation(page, "table_rows_with_headers")
                if page.get("has_table") else ""
            ),
            "visual": visual_caption_context(page) if page.get("has_image") else "",
        }
        for branch, text in branch_text.items():
            if not text.strip():
                continue
            pdf_page = int(page["pdf_page_number"])
            output[branch].append({
                "chunk_id": f"{page['book_id']}:{SPECIALIST_METHODS[branch]}:{pdf_page:04d}",
                "book_id": page["book_id"],
                "text": text,
                "pdf_pages": [pdf_page],
                "textbook_pages": [page.get("textbook_page_number")],
                "chapter_title": page.get("chapter_title"),
                "section_title": page.get("section_title"),
            })
    return output


def _exercise_bm25(documents: list[dict[str, Any]]) -> dict[str, Any]:
    if not documents:
        return {"documents": 0, "reconstruction_verified": True, "health_query_results": 0}
    index = BM25((document["text"] for document in documents), k1=1.5, b=0.75)
    scores = index.scores("textbook health verification")
    return {
        "documents": len(documents),
        "k1": index.k1,
        "b": index.b,
        "reconstruction_verified": len(scores) == len(documents),
        "health_query_results": len(scores),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _jsonl_fingerprint(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _durable_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file() and path.name != "manifest.json")
