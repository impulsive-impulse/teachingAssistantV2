"""Retrieval Baseline v1-derived runtime for one uploaded textbook.

The runtime reuses the measured query processing, specialist activation,
ranking, RRF, lifting, and overlap-aware context assembly implementations. It
only replaces frozen book paths with an accepted uploaded-book manifest.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from textbook_audit.context_assembly import assemble_context
from textbook_audit.retrieval import BM25
from textbook_audit.specialist_retrieval import rank_combined_query


SPECIALIST_METHODS = {
    "formula": "formula_equation_context",
    "table": "table_rows_with_headers",
    "visual": "visual_caption_context",
}


@dataclass(frozen=True)
class RetrievalSnapshotData:
    """Immutable, persistence-ready output from one independent question."""

    baseline_name: str
    baseline_version: str
    runtime_profile: str
    question: str
    processed_query: str
    book_id: str
    book_fingerprint: str
    profile_fingerprint: str
    activated_specialist_signals: list[str]
    evidence: list[dict[str, Any]]
    assembled_context: list[dict[str, Any]]
    component_diagnostics: dict[str, Any]
    retrieval_latency_ms: float
    checksum: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UploadedBookRetrievalRuntime:
    """Loaded corpora, matrices, lexical indexes, and exact v1 query behavior."""

    def __init__(
        self,
        book_dir: Path,
        embedding_model: Any,
        baseline: dict[str, Any],
        *,
        expected_source_checksum: str | None = None,
    ):
        self.book_dir = book_dir.resolve()
        self.embedding_model = embedding_model
        self.baseline = baseline
        self.manifest = _verify_manifest(self.book_dir, expected_source_checksum)
        self.book_id = self.manifest["book_id"]
        self.chunks = _read_jsonl(self.book_dir / "chunks.jsonl")
        self.chunk_matrix = _load_matrix(
            self.book_dir / "indexes" / "chunks.npz", len(self.chunks),
            int(baseline["embedding"]["dimensions"]),
            baseline["embedding"]["revision"],
        )
        bm25 = baseline["bm25"]
        self.child_bm25 = BM25(
            (chunk["text"] for chunk in self.chunks), float(bm25["k1"]), float(bm25["b"])
        )
        self.resources: dict[str, tuple[dict[str, list[dict[str, Any]]], dict[str, np.ndarray]]] = {}
        self.specialist_bm25: dict[str, dict[str, BM25]] = {}
        for branch, method in SPECIALIST_METHODS.items():
            documents = _read_jsonl(self.book_dir / "specialists" / f"{branch}.jsonl")
            if not documents:
                continue
            matrix = _load_matrix(
                self.book_dir / "indexes" / f"{branch}.npz", len(documents),
                int(baseline["embedding"]["dimensions"]), baseline["embedding"]["revision"],
            )
            self.resources[method] = ({self.book_id: documents}, {self.book_id: matrix})
            self.specialist_bm25[method] = {
                self.book_id: BM25(
                    (document["text"] for document in documents),
                    float(bm25["k1"]), float(bm25["b"]),
                )
            }
        self.book_fingerprint = _sha256(self.book_dir / "manifest.json")
        self.profile_fingerprint = _profile_fingerprint(baseline)

    @classmethod
    def load(
        cls,
        book_dir: Path,
        embedding_model: Any,
        root: Path,
        expected_source_checksum: str | None = None,
    ) -> "UploadedBookRetrievalRuntime":
        baseline = yaml.safe_load(
            (root / "config" / "retrieval_baseline_v1.yaml").read_text(encoding="utf-8")
        )
        return cls(
            book_dir, embedding_model, baseline,
            expected_source_checksum=expected_source_checksum,
        )

    def retrieve(self, question: str) -> RetrievalSnapshotData:
        """Retrieve exactly five evidence chunks for one self-contained question."""

        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")
        started = time.perf_counter()
        runtime_config = {
            "rrf_constant": self.baseline["fusion"]["rrf_k"],
            "synonym_rules": self.baseline["query_processing"]["rules"],
            "specialists": [
                {
                    "method": self.baseline["specialists"][branch]["method"],
                    "branch": branch,
                    "activation_version": self.baseline["specialists"][branch]["activation_version"],
                    "activation_pattern": self.baseline["specialists"][branch]["activation_pattern"],
                    "activation_query": self.baseline["specialists"][branch]["activation_query"],
                }
                for branch in ("formula", "table", "visual")
            ],
        }
        ranked = rank_combined_query(
            question,
            self.book_id,
            self.embedding_model,
            {"query_prefix": self.baseline["embedding"]["query_prefix"]},
            self.chunks,
            self.chunk_matrix,
            self.resources,
            self.child_bm25,
            self.specialist_bm25,
            runtime_config=runtime_config,
        )
        ranking = [int(index) for index in ranked["ranking"]]
        if len(ranking) < 5:
            raise RuntimeError("accepted book retrieval produced fewer than five candidates")
        component_ranks = ranked["component_rankings"]
        raw_scores = ranked["component_raw_scores"]
        evidence = []
        for rank, index in enumerate(ranking[:5], 1):
            chunk = self.chunks[index]
            ranks = {name: int(positions[index]) for name, positions in component_ranks.items()}
            component_scores = {
                name: (
                    float(raw_scores[name][index])
                    if name in raw_scores
                    else 1.0 / (int(self.baseline["fusion"]["rrf_k"]) + source_rank)
                )
                for name, source_rank in ranks.items()
            }
            evidence.append({
                "rank": rank,
                "evidence_id": chunk["chunk_id"],
                "book_id": self.book_id,
                "pdf_pages": [int(page) for page in chunk["pdf_pages"]],
                "textbook_pages": chunk["textbook_pages"],
                "chapter": chunk.get("chapter_title"),
                "section": chunk.get("section_title"),
                "evidence_text": chunk["text"],
                "text_snippet": " ".join(chunk["text"].split())[:500],
                "contributing_retrievers": list(ranks),
                "component_ranks": ranks,
                "component_scores": component_scores,
                "fused_score": float(ranked["scores"][index]),
                "activated_specialist_signals": list(ranked["activated_specialists"]),
            })
        assembly = self.baseline["context_assembly"]
        context = assemble_context(
            "overlap_merge_metadata_preserving", ranking, self.chunks,
            count=int(assembly["input_candidate_count"]),
            overlap_maximum=int(assembly["maximum_exact_overlap_words"]),
            overlap_minimum=int(assembly["minimum_exact_overlap_words"]),
        )
        elapsed = (time.perf_counter() - started) * 1000
        core = {
            "baseline_name": self.baseline["baseline"]["name"],
            "baseline_version": self.baseline["baseline"]["semantic_version"],
            "runtime_profile": self.manifest["runtime_profile_version"],
            "question": question,
            "processed_query": ranked["processed_query"],
            "book_id": self.book_id,
            "book_fingerprint": self.book_fingerprint,
            "profile_fingerprint": self.profile_fingerprint,
            "activated_specialist_signals": list(ranked["activated_specialists"]),
            "evidence": evidence,
            "assembled_context": context,
            "component_diagnostics": {
                "component_rankings": {
                    name: {str(index): int(value) for index, value in positions.items()}
                    for name, positions in component_ranks.items()
                }
            },
            "retrieval_latency_ms": elapsed,
        }
        checksum = hashlib.sha256(
            json.dumps(core, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return RetrievalSnapshotData(**core, checksum=checksum)


def _verify_manifest(book_dir: Path, expected_source_checksum: str | None) -> dict[str, Any]:
    manifest_path = book_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("publication_state") != "verified":
        raise RuntimeError("book artifacts were not atomically verified")
    if manifest.get("runtime_profile_version") != "retrieval-v1-derived-v1":
        raise RuntimeError("uploaded-book runtime profile is incompatible")
    if expected_source_checksum and manifest.get("source_sha256") != expected_source_checksum:
        raise RuntimeError("book source checksum does not match its database identity")
    for relative, identity in manifest.get("artifacts", {}).items():
        path = (book_dir / relative).resolve()
        if book_dir not in path.parents or not path.is_file():
            raise RuntimeError(f"book artifact is missing or escaped its directory: {relative}")
        if path.stat().st_size != int(identity["size_bytes"]) or _sha256(path) != identity["sha256"]:
            raise RuntimeError(f"book artifact failed checksum verification: {relative}")
    return manifest


def _load_matrix(path: Path, rows: int, dimensions: int, revision: str) -> np.ndarray:
    with np.load(path, allow_pickle=False) as stored:
        matrix = stored["embeddings"].astype(np.float32)
        stored_revision = str(stored["model_revision"].item())
        stored_dimensions = int(stored["dimensions"].item())
    if matrix.shape != (rows, dimensions):
        raise RuntimeError(f"dense matrix shape mismatch: {path.name}")
    if stored_revision != revision or stored_dimensions != dimensions:
        raise RuntimeError(f"dense matrix model identity mismatch: {path.name}")
    return matrix


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _profile_fingerprint(baseline: dict[str, Any]) -> str:
    keys = ("chunking", "embedding", "bm25", "query_processing", "specialists", "fusion", "output", "context_assembly")
    payload = {key: baseline[key] for key in keys}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
