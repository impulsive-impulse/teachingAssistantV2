"""Acquire exact assessment inputs without relying on private model caches."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

from .assessment_protocol import build_manifest, fingerprint, load_protocol, load_source, read_json
from .experiment_tracking import sha256_file, write_json


ROOT = Path(__file__).resolve().parents[2]
ASSET_MANIFEST = Path("config") / "assessment_assets_v1.json"
SHA256 = re.compile(r"[0-9a-f]{64}")


class ByteReader(Protocol):
    def read(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True)
class FileIdentity:
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int) or self.size_bytes < 1:
            raise ValueError("asset size must be a positive integer")
        if not isinstance(self.sha256, str) or not SHA256.fullmatch(self.sha256):
            raise ValueError("asset SHA-256 must be 64 lowercase hexadecimal characters")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FileIdentity":
        return cls(value["size_bytes"], value["sha256"])


@dataclass(frozen=True)
class AssetProgress:
    filename: str
    processed_bytes: int
    downloaded_bytes: int
    total_bytes: int


def child_path(root: Path, relative: str) -> Path:
    """Reject traversal and Windows absolute paths even on another platform."""
    if not isinstance(relative, str) or not relative:
        raise ValueError("asset path must be a non-empty relative path")
    posix, windows = PurePosixPath(relative), PureWindowsPath(relative)
    if posix.is_absolute() or windows.drive or windows.root or ".." in posix.parts or ".." in windows.parts:
        raise ValueError(f"asset path must stay inside its root: {relative}")
    resolved_root = root.resolve()
    target = (resolved_root / relative).resolve()
    if target == resolved_root or resolved_root not in target.parents:
        raise ValueError(f"asset path escaped its root: {relative}")
    return target


def validate_url(url: str) -> None:
    parts = urlparse(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("asset downloads require an HTTPS URL without embedded credentials")


def load_assets(root: Path = ROOT) -> dict[str, Any]:
    assets = read_json(root / ASSET_MANIFEST)
    if not isinstance(assets, dict) or assets.get("schema_version") != 1:
        raise ValueError("assessment assets must use schema_version 1")
    protocol = load_protocol(child_path(root, assets["protocol_file"]))
    model = assets["embedding"]
    shared = protocol["shared_constraints"]
    if (model["repository"], model["revision"]) != (shared["embedding_model"], shared["embedding_revision"]):
        raise ValueError("embedding asset identity differs from the frozen assessment protocol")
    frozen = read_json(root / "reports" / "retrieval_baseline_v1" / "manifest.json")
    identity = frozen["model"]["cache_identity"]
    if (model["expected_identity_sha256"], model["expected_file_count"], model["expected_size_bytes"]) != (
        identity["identity_sha256"], identity["file_count"], identity["size_bytes"]
    ):
        raise ValueError("embedding inventory differs from the historical frozen identity")
    paths = [item["path"] for item in model["files"]]
    if len(paths) != model["expected_file_count"] or len({path.casefold() for path in paths}) != len(paths):
        raise ValueError("embedding inventory contains missing or duplicate files")
    if "model.safetensors" not in paths or any(path.endswith((".bin", ".onnx", ".py")) for path in paths):
        raise ValueError("only the frozen safetensors model and its required metadata are supported")
    if sum(item["size_bytes"] for item in model["files"]) != model["expected_size_bytes"]:
        raise ValueError("embedding inventory sizes do not match the frozen total")
    for item in model["files"]:
        child_path(root, item["path"])
        FileIdentity.from_dict(item)
    tokenizer = assets["context_tokenizer"]
    if tokenizer["name"] != shared["context_tokenizer"]:
        raise ValueError("context tokenizer differs from the assessment protocol")
    validate_url(tokenizer["url"])
    FileIdentity.from_dict(tokenizer)
    if tokenizer["cache_key"] != hashlib.sha1(tokenizer["url"].encode("utf-8")).hexdigest():
        raise ValueError("tokenizer cache key does not match tiktoken's source URL")
    validate_url(assets["evaluator"]["license"]["url"])
    FileIdentity.from_dict(assets["evaluator"]["license"])
    for relative in (assets["benchmark"]["path"], model["directory"], tokenizer["cache_directory"],
                     assets["evaluator"]["directory"], assets["readiness_report"]):
        child_path(root, relative)
    if assets["demo_books"]["permission_required"] is not True or assets["demo_books"]["automatic_download"] is not False:
        raise ValueError("restricted demo books must use explicit authorized local import")
    return assets


def verify_file(path: Path, identity: FileIdentity) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Required input is missing: {path}")
    if path.stat().st_size != identity.size_bytes or sha256_file(path) != identity.sha256:
        raise ValueError(f"Input failed its pinned size/SHA-256 check: {path}")


def _publish_stream(
    source: ByteReader, destination: Path, identity: FileIdentity,
    progress: Callable[[int], None] | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".", suffix=".partial", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        digest = hashlib.sha256()
        total = 0
        with os.fdopen(descriptor, "wb") as output:
            while block := source.read(1024 * 1024):
                total += len(block)
                if total > identity.size_bytes:
                    raise ValueError(f"Download exceeds the pinned size: {destination.name}")
                output.write(block)
                digest.update(block)
                if progress:
                    progress(total)
        if total != identity.size_bytes or digest.hexdigest() != identity.sha256:
            raise ValueError(f"Downloaded input failed size/SHA-256 verification: {destination.name}")
        try:
            os.link(temporary, destination)
        except FileExistsError:
            verify_file(destination, identity)
    finally:
        temporary.unlink(missing_ok=True)


def acquire_file(
    url: str, destination: Path, identity: FileIdentity, *, download: bool = True,
    progress: Callable[[int], None] | None = None,
) -> bool:
    """Return whether bytes were downloaded; never overwrite a wrong cache file."""
    validate_url(url)
    if destination.exists() or not download:
        verify_file(destination, identity)
        return False
    request = urllib.request.Request(url, headers={"User-Agent": "Marginalia-verified-inputs/1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected asset HTTP status: {response.status}")
        _publish_stream(response, destination, identity, progress)
    return True


def prepare_embedding(
    root: Path = ROOT, *, directory: Path | None = None, download: bool = True,
    progress: Callable[[AssetProgress], None] | None = None,
) -> dict[str, Any]:
    assets = load_assets(root)
    model = assets["embedding"]
    directory = directory.resolve() if directory is not None else child_path(root, model["directory"])
    expected = {item["path"] for item in model["files"]}
    existing = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
    if existing - expected:
        raise ValueError(f"Embedding snapshot contains unexpected files: {sorted(existing - expected)}")
    processed = downloaded_bytes = 0
    total = model["expected_size_bytes"]
    base_url = f"https://huggingface.co/{model['repository']}/resolve/{model['revision']}/"
    for item in model["files"]:
        destination = child_path(directory, item["path"])
        identity = FileIdentity.from_dict(item)
        callback = None
        if progress:
            def callback(current: int, *, filename: str = item["path"],
                         previous: int = processed, network: int = downloaded_bytes) -> None:
                progress(AssetProgress(filename, previous + current, network + current, total))
        acquired = acquire_file(base_url + item["path"], destination, identity,
                                download=download, progress=callback)
        processed += identity.size_bytes
        if acquired:
            downloaded_bytes += identity.size_bytes
        if progress:
            progress(AssetProgress(item["path"], processed, downloaded_bytes, total))
    from textbook_chat.models.embedding import directory_identity
    actual = directory_identity(directory)
    if (actual.identity_sha256, actual.file_count, actual.size_bytes) != (
        model["expected_identity_sha256"], model["expected_file_count"], model["expected_size_bytes"]
    ):
        raise ValueError("Prepared embedding snapshot does not reproduce the frozen identity")
    return {
        "repository": model["repository"], "revision": model["revision"],
        "identity_sha256": actual.identity_sha256, "file_count": actual.file_count,
        "size_bytes": actual.size_bytes, "downloaded_bytes": downloaded_bytes,
    }


def import_demo_books(
    root: Path, source_directory: Path, *, authorized: bool, copy: bool = True,
) -> list[dict[str, Any]]:
    if not authorized:
        raise PermissionError("Demo-book import requires explicit permission covering indexing and demonstration.")
    assets = load_assets(root)
    settings = assets["demo_books"]
    frozen = read_json(child_path(root, settings["identity_manifest"]))["source_pdfs"]
    from pypdf import PdfReader
    results = []
    for book_id, book in settings["books"].items():
        source = child_path(source_directory, book["filename"])
        identity = FileIdentity.from_dict(frozen[book_id])
        if not source.is_file():
            raise FileNotFoundError(
                f"Missing authorized {settings['edition']} copy: {source}. "
                f"Obtain the specified edition through {settings['publisher_portal']} "
                "with the required permission, then pass --demo-books-dir."
            )
        verify_file(source, identity)
        if len(PdfReader(source).pages) != book["page_count"]:
            raise ValueError(f"Demo book page count differs: {book_id}")
        destination = child_path(root, frozen[book_id]["path"])
        if destination != source:
            if destination.exists() or not copy:
                verify_file(destination, identity)
            else:
                with source.open("rb") as handle:
                    _publish_stream(handle, destination, identity)
        results.append({
            "book_id": book_id, "filename": book["filename"],
            "sha256": identity.sha256, "page_count": book["page_count"],
            "status": "verified_authorized_local_input",
        })
    return results


def prepare_inputs(
    root: Path = ROOT, *, download: bool = True, demo_books_dir: Path | None = None,
    authorized_demo_use: bool = False,
) -> dict[str, Any]:
    assets = load_assets(root)
    protocol = load_protocol(child_path(root, assets["protocol_file"]))
    if authorized_demo_use != (demo_books_dir is not None):
        raise ValueError("--demo-books-dir and --authorized-demo-use must be supplied together")
    benchmark = child_path(root, assets["benchmark"]["path"])
    acquired = acquire_file(protocol["benchmark"]["download_url"], benchmark,
                            FileIdentity.from_dict(protocol["benchmark"]), download=download)
    rows = load_source(benchmark, protocol["benchmark"])
    review = read_json(child_path(root, protocol["selection"]["necessity_review"]))
    selection = build_manifest(rows, protocol, review)
    if read_json(child_path(root, protocol["selection"]["manifest"])) != selection:
        raise ValueError("Prepared benchmark does not reproduce the frozen selection")
    embedding = prepare_embedding(root, download=download)
    tokenizer = assets["context_tokenizer"]
    tokenizer_path = child_path(child_path(root, tokenizer["cache_directory"]), tokenizer["cache_key"])
    acquire_file(tokenizer["url"], tokenizer_path, FileIdentity.from_dict(tokenizer), download=download)
    evaluator = assets["evaluator"]
    evaluator_directory = child_path(root, evaluator["directory"])
    scorer = protocol["metrics"]["scorer"]
    acquire_file(scorer["url"], child_path(evaluator_directory, evaluator["script"]["path"]),
                 FileIdentity(evaluator["script"]["size_bytes"], scorer["sha256"]), download=download)
    license_file = evaluator["license"]
    acquire_file(license_file["url"], child_path(evaluator_directory, license_file["path"]),
                 FileIdentity.from_dict(license_file), download=download)
    books = (
        import_demo_books(root, demo_books_dir, authorized=authorized_demo_use, copy=download)
        if demo_books_dir is not None else []
    )
    result = {
        "asset_profile_id": assets["asset_profile_id"],
        "asset_manifest_semantic_sha256": fingerprint(assets),
        "protocol_semantic_sha256": fingerprint(protocol),
        "benchmark": {
            "sha256": protocol["benchmark"]["sha256"],
            "selected_questions": selection["selected_count"], "downloaded": acquired,
        },
        "embedding": embedding,
        "context_tokenizer": {"name": tokenizer["name"], "sha256": tokenizer["sha256"]},
        "evaluator": {"sha256": scorer["sha256"], "license_sha256": license_file["sha256"]},
        "demo_books": books,
        "demo_scope": "authorized_local_inputs" if books else "not_requested",
        "check_only": not download,
        "paid_model_calls": 0,
    }
    if download:
        write_json(child_path(root, assets["readiness_report"]), result)
    return result


def offline_smoke(root: Path = ROOT) -> dict[str, Any]:
    """Exercise the actual encoder and token counter with all network access denied."""
    assets = load_assets(root)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TIKTOKEN_CACHE_DIR"] = str(child_path(root, assets["context_tokenizer"]["cache_directory"]))
    from unittest.mock import patch
    with patch("socket.socket.connect", side_effect=RuntimeError("network disabled during offline readiness")):
        import numpy as np
        import tiktoken
        import torch
        from sentence_transformers import SentenceTransformer
        if torch.version.cuda is not None:
            raise RuntimeError("Assessment readiness requires the locked CPU-only Torch build.")
        directory = child_path(root, assets["embedding"]["directory"])
        model = SentenceTransformer(str(directory), device="cpu", local_files_only=True, trust_remote_code=False)
        vectors = model.encode(["A source provides evidence.", "A citation identifies its location."],
                               normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True)
        if vectors.shape != (2, 384) or not np.isfinite(vectors).all() or not np.allclose(
            np.linalg.norm(vectors, axis=1), 1.0, atol=1e-6
        ):
            raise RuntimeError("Pinned embedding model failed its dimension/normalization readiness check.")
        encoder = tiktoken.get_encoding(assets["context_tokenizer"]["name"])
        text = "Exact source locations support grounded answers."
        tokens = encoder.encode(text)
        if not tokens or encoder.decode(tokens) != text:
            raise RuntimeError("Pinned context tokenizer failed its offline readiness check.")
    return {"embedding_dimensions": 384, "device": str(model.device),
            "torch": torch.__version__, "tokenizer": encoder.name, "network_allowed": False}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true", help="Verify existing inputs without downloading or copying.")
    parser.add_argument("--smoke", action="store_true", help="Run the encoder and token counter offline; no generation.")
    parser.add_argument("--demo-books-dir", type=Path)
    parser.add_argument("--authorized-demo-use", action="store_true")
    args = parser.parse_args(argv)
    result = prepare_inputs(args.root, download=not args.check, demo_books_dir=args.demo_books_dir,
                            authorized_demo_use=args.authorized_demo_use)
    if args.smoke:
        result["offline_readiness"] = offline_smoke(args.root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
