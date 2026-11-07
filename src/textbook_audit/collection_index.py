"""Versioned, collection-local dense retrieval over exact source evidence."""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

import numpy as np
import yaml

from .assessment_protocol import fingerprint, read_json
from .chunk_retrieval import fixed_chunks
from .context_assembly import assemble_context
from .experiment_tracking import sha256_file, write_json
from .retrieval import stable_ranking
from .source_provenance import (
    ProvenanceText, SourceDocument, document_set_fingerprint, read_source_bundle,
    require_retained_spans, retrieval_units, source_locations, write_source_bundle,
)


INDEX_VERSION = "collection-index-v1"
PROFILE_FIELDS = {
    "version", "chunk_target", "chunk_overlap", "model_name", "model_revision",
    "dimensions", "query_prefix", "document_prefix", "batch_size",
}


def collection_profile(root: Path) -> dict[str, Any]:
    baseline = yaml.safe_load((root / "config" / "retrieval_baseline_v1.yaml").read_text("utf-8"))
    embedding, chunking = baseline["embedding"], baseline["chunking"]
    return {
        "version": INDEX_VERSION, "chunk_target": chunking["target_tokens"],
        "chunk_overlap": chunking["overlap_tokens"], "model_name": embedding["model_name"],
        "model_revision": embedding["revision"], "dimensions": embedding["dimensions"],
        "query_prefix": embedding["query_prefix"], "document_prefix": embedding["document_prefix"],
        "batch_size": embedding["batch_size"],
    }


def _validate_profile(profile: dict[str, Any]) -> None:
    if not isinstance(profile, dict) or set(profile) != PROFILE_FIELDS or profile["version"] != INDEX_VERSION:
        raise ValueError("collection index profile has invalid fields or version")
    for field in ("chunk_target", "dimensions", "batch_size"):
        value = profile[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"collection profile {field} must be a positive integer")
    overlap = profile["chunk_overlap"]
    if isinstance(overlap, bool) or not isinstance(overlap, int) or not 0 <= overlap < profile["chunk_target"]:
        raise ValueError("collection overlap must be smaller than its chunk target")
    for field in ("model_name", "model_revision"):
        if not isinstance(profile[field], str) or not profile[field]:
            raise ValueError(f"collection profile {field} must be a non-empty string")
    if any(not isinstance(profile[field], str) for field in ("query_prefix", "document_prefix")):
        raise ValueError("embedding prefixes must be strings")


def _model(model: Any, profile: dict[str, Any]) -> Any:
    metadata = model.metadata
    if (
        metadata["resolved_model_revision"] != profile["model_revision"]
        or metadata["dimensions"] != profile["dimensions"]
        or metadata["model_name"] != profile["model_name"]
    ):
        raise ValueError("collection encoder differs from its declared profile")
    return model.model


def _matrix(matrix: np.ndarray, rows: int, dimensions: int) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.shape != (rows, dimensions) or not np.isfinite(matrix).all():
        raise ValueError("collection embeddings have invalid shape or non-finite values")
    if rows and not np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-4):
        raise ValueError("collection embeddings must be normalized and nonzero")
    matrix = matrix.copy()
    matrix.flags.writeable = False
    return matrix


class CollectionIndex:
    """One immutable corpus; subset views never search outside their source set."""

    def __init__(
        self, documents: Sequence[SourceDocument], embeddings: np.ndarray, profile: dict[str, Any],
    ):
        _validate_profile(profile)
        self.profile = dict(profile)
        self.profile_fingerprint = fingerprint(self.profile)
        self.collection_fingerprint = document_set_fingerprint(documents)
        self.documents = tuple(sorted(documents, key=lambda document: document.document_id))
        self.catalog = {document.document_id: document for document in self.documents}
        self.chunks = [
            chunk for document in self.documents
            for chunk in fixed_chunks(
                retrieval_units(document), target=profile["chunk_target"], overlap=profile["chunk_overlap"],
            )
        ]
        if not self.chunks:
            raise ValueError("collection has no searchable source text")
        self.embeddings = _matrix(embeddings, len(self.chunks), profile["dimensions"])
        self.corpus_fingerprint = fingerprint({
            "collection_fingerprint": self.collection_fingerprint,
            "profile_fingerprint": self.profile_fingerprint,
            "evidence_ids": [chunk["evidence_id"] for chunk in self.chunks],
        })
        self.embedding_fingerprint = hashlib.sha256(self.embeddings.tobytes()).hexdigest()

    @classmethod
    def build(
        cls, documents: Sequence[SourceDocument], model: Any, profile: dict[str, Any],
    ) -> CollectionIndex:
        _validate_profile(profile)
        document_set_fingerprint(documents)
        chunks = [
            chunk for document in sorted(documents, key=lambda document: document.document_id)
            for chunk in fixed_chunks(
                retrieval_units(document), target=profile["chunk_target"], overlap=profile["chunk_overlap"],
            )
        ]
        if not chunks:
            raise ValueError("collection has no searchable source text")
        matrix = _model(model, profile).encode(
            [profile["document_prefix"] + chunk["text"] for chunk in chunks],
            batch_size=profile["batch_size"], convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False,
        )
        return cls(documents, matrix, profile)

    def subset(self, document_ids: Sequence[str]) -> CollectionIndex:
        if (
            not isinstance(document_ids, (tuple, list)) or not document_ids
            or any(not isinstance(document_id, str) for document_id in document_ids)
            or len(set(document_ids)) != len(document_ids)
        ):
            raise ValueError("retrieval scope requires distinct source IDs")
        if set(document_ids) - set(self.catalog):
            raise ValueError("retrieval scope includes documents outside this collection")
        wanted = set(document_ids)
        rows = [index for index, chunk in enumerate(self.chunks) if chunk["document_id"] in wanted]
        return CollectionIndex(
            [self.catalog[document_id] for document_id in sorted(wanted)], self.embeddings[rows], self.profile,
        )

    def dense_scores(self, question: str, model: Any) -> np.ndarray:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must not be empty")
        vector = _model(model, self.profile).encode(
            [self.profile["query_prefix"] + question.strip()],
            convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False,
        )
        vector = _matrix(vector, 1, self.profile["dimensions"])[0]
        return self.embeddings @ vector

    def retrieve(self, question: str, model: Any, top_k: int = 5) -> dict[str, Any]:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("retrieval top-k must be positive")
        started = time.perf_counter()
        scores = self.dense_scores(question, model)
        ranking = stable_ranking(scores).tolist()
        return self.snapshot(question, ranking, scores, top_k, started=started)

    def snapshot(
        self, question: str, ranking: Sequence[int], scores: np.ndarray, top_k: int = 5,
        *, started: float | None = None,
    ) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must not be empty")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("retrieval top-k must be positive")
        if (
            any(isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.chunks)
                for index in ranking)
            or len(set(ranking)) != len(ranking)
        ):
            raise ValueError("retrieval ranking contains invalid or duplicate corpus indices")
        scores = np.asarray(scores)
        if scores.shape != (len(self.chunks),) or not np.isfinite(scores).all():
            raise ValueError("retrieval scores do not match the indexed corpus")
        started = time.perf_counter() if started is None else started
        evidence = []
        for rank, index in enumerate(ranking[:top_k], 1):
            chunk = self.chunks[index]
            mapped = ProvenanceText.from_dict(chunk["source_provenance"])
            mapped.validate(self.catalog)
            document = self.catalog[chunk["document_id"]]
            evidence.append({
                **chunk, "rank": rank, "document_title": document.title,
                "evidence_text": chunk["text"], "score": float(scores[index]),
                "source_locations": [
                    {"document_id": document_id, "unit_id": unit_id}
                    for document_id, unit_id in sorted(source_locations(mapped))
                ],
            })
        context = assemble_context(
            "overlap_merge_metadata_preserving", list(ranking), self.chunks, count=top_k,
        )
        core = {
            "version": INDEX_VERSION, "question": question.strip(),
            "profile": self.profile,
            "collection_fingerprint": self.collection_fingerprint,
            "corpus_fingerprint": self.corpus_fingerprint,
            "profile_fingerprint": self.profile_fingerprint,
            "embedding_fingerprint": self.embedding_fingerprint,
            "document_ids": [document.document_id for document in self.documents],
            "source_documents": [document.to_dict() for document in self.documents],
            "evidence": evidence, "assembled_context": context,
        }
        return {
            **core, "checksum": fingerprint(core),
            "retrieval_latency_ms": (time.perf_counter() - started) * 1000,
        }

    def validate_snapshot(self, snapshot: dict[str, Any]) -> None:
        if not isinstance(snapshot, dict) or set(snapshot) != {
            "version", "question", "profile", "collection_fingerprint", "corpus_fingerprint",
            "profile_fingerprint", "embedding_fingerprint", "document_ids", "source_documents",
            "evidence", "assembled_context", "checksum", "retrieval_latency_ms",
        }:
            raise ValueError("collection retrieval snapshot has invalid fields")
        core = {key: value for key, value in snapshot.items() if key not in {"checksum", "retrieval_latency_ms"}}
        if snapshot["checksum"] != fingerprint(core) or snapshot["version"] != INDEX_VERSION:
            raise ValueError("collection snapshot checksum or version is invalid")
        if snapshot["profile"] != self.profile:
            raise ValueError("collection snapshot profile differs")
        for field in ("collection_fingerprint", "corpus_fingerprint", "profile_fingerprint", "embedding_fingerprint"):
            if snapshot[field] != getattr(self, field):
                raise ValueError(f"collection snapshot {field} differs from its index")
        if snapshot["document_ids"] != list(self.catalog) or snapshot["source_documents"] != [
            document.to_dict() for document in self.documents
        ]:
            raise ValueError("collection snapshot broadened or changed its source scope")
        if not isinstance(snapshot["question"], str) or not snapshot["question"].strip():
            raise ValueError("collection snapshot question is missing")
        latency = snapshot["retrieval_latency_ms"]
        if isinstance(latency, bool) or not isinstance(latency, (float, int)) or not np.isfinite(latency) or latency < 0:
            raise ValueError("collection snapshot latency is invalid")
        if not isinstance(snapshot["evidence"], list) or not snapshot["evidence"] or not isinstance(snapshot["assembled_context"], list):
            raise ValueError("collection snapshot evidence is missing")
        by_id = {chunk["evidence_id"]: chunk for chunk in self.chunks}
        selected = []
        for item in snapshot["evidence"]:
            mapped = ProvenanceText.from_dict(item["source_provenance"])
            mapped.validate(self.catalog)
            if item["evidence_id"] not in by_id or mapped.to_dict() != by_id[item["evidence_id"]]["source_provenance"]:
                raise ValueError("collection snapshot evidence is outside its indexed corpus")
            if (
                item["text"] != mapped.text or item["evidence_text"] != mapped.text
                or item["document_id"] != mapped.document_hashes[0][0]
                or item["document_title"] != self.catalog[item["document_id"]].title
            ):
                raise ValueError("collection snapshot text or source address was altered")
            selected.append(mapped)
        for segment in snapshot["assembled_context"]:
            mapped = ProvenanceText.from_dict(segment["source_provenance"])
            mapped.validate(self.catalog)
            if segment["text"] != mapped.text:
                raise ValueError("collection context text was altered")
            require_retained_spans(mapped, selected)

    def write_snapshot(self, path: Path, snapshot: dict[str, Any]) -> None:
        self.validate_snapshot(snapshot)
        write_json(path, snapshot)

    def read_snapshot(self, path: Path) -> dict[str, Any]:
        snapshot = read_json(path)
        self.validate_snapshot(snapshot)
        return snapshot

    def save(self, directory: Path) -> None:
        """Publish an owned, complete index directory, never overwrite a cache."""
        directory = directory.resolve()
        if directory.exists():
            raise FileExistsError("collection index destination already exists")
        directory.parent.mkdir(parents=True, exist_ok=True)
        staging = directory.parent / f".{directory.name}-{uuid4().hex}.partial"
        staging.mkdir(exist_ok=False)
        try:
            write_source_bundle(
                staging / "corpus.json", self.documents,
                [ProvenanceText.from_dict(chunk["source_provenance"]) for chunk in self.chunks],
            )
            np.savez_compressed(staging / "embeddings.npz", embeddings=self.embeddings)
            write_json(staging / "manifest.json", {
                "version": INDEX_VERSION, "profile": self.profile,
                "collection_fingerprint": self.collection_fingerprint,
                "corpus_fingerprint": self.corpus_fingerprint,
                "embedding_fingerprint": self.embedding_fingerprint,
                "artifacts": {
                    name: {"sha256": sha256_file(staging / name), "size_bytes": (staging / name).stat().st_size}
                    for name in ("corpus.json", "embeddings.npz")
                },
            })
            self.load(staging)
            staging.rename(directory)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    @classmethod
    def load(cls, directory: Path) -> CollectionIndex:
        manifest = read_json(directory / "manifest.json")
        if not isinstance(manifest, dict) or set(manifest) != {
            "version", "profile", "collection_fingerprint", "corpus_fingerprint",
            "embedding_fingerprint", "artifacts",
        } or manifest["version"] != INDEX_VERSION:
            raise ValueError("collection index manifest is invalid")
        if not isinstance(manifest["artifacts"], dict) or set(manifest["artifacts"]) != {"corpus.json", "embeddings.npz"}:
            raise ValueError("collection index artifact inventory is invalid")
        for name, identity in manifest["artifacts"].items():
            path = directory / name
            if not path.is_file() or path.stat().st_size != identity["size_bytes"] or sha256_file(path) != identity["sha256"]:
                raise ValueError(f"collection index artifact failed integrity verification: {name}")
        documents, evidence = read_source_bundle(directory / "corpus.json")
        with np.load(directory / "embeddings.npz", allow_pickle=False) as stored:
            if set(stored.files) != {"embeddings"}:
                raise ValueError("collection embedding archive has unexpected fields")
            result = cls(documents, stored["embeddings"], manifest["profile"])
        if evidence != [ProvenanceText.from_dict(chunk["source_provenance"]) for chunk in result.chunks]:
            raise ValueError("stored evidence differs from the declared chunking profile")
        for field in ("collection_fingerprint", "corpus_fingerprint", "embedding_fingerprint"):
            if getattr(result, field) != manifest[field]:
                raise ValueError(f"collection index {field} is inconsistent")
        return result
