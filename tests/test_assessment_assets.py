"""Offline acquisition, integrity, permission, and cache-boundary checks."""

from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import Mock

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pypdf import PdfWriter

import textbook_audit.assessment_assets as assets_module
from textbook_audit.assessment_assets import (
    FileIdentity, acquire_file, child_path, import_demo_books, load_assets,
    prepare_embedding, prepare_inputs, validate_url,
)
from textbook_audit.assessment_protocol import build_manifest, read_json
from textbook_chat.models.embedding import directory_identity
from test_assessment_protocol import ROOT, example, reviewed, small_protocol


def identity(content: bytes) -> dict:
    return {"size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def asset_root(tmp_path: Path, small_protocol: dict, monkeypatch: pytest.MonkeyPatch) -> Path:
    assets = copy.deepcopy(load_assets())
    rows = [example(f"{kind}-{index}", kind) for kind in ("bridge", "comparison") for index in range(2)]
    source = child_path(tmp_path, assets["benchmark"]["path"])
    source.parent.mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(rows), source)
    small_protocol["benchmark"].update(identity(source.read_bytes()), expected_rows=len(rows))
    review = reviewed(rows, small_protocol)
    write_json(child_path(tmp_path, assets["protocol_file"]), small_protocol)
    write_json(child_path(tmp_path, small_protocol["selection"]["necessity_review"]), review)
    write_json(child_path(tmp_path, small_protocol["selection"]["manifest"]),
               build_manifest(rows, small_protocol, review))
    bodies = {"README.md": b"Synthetic test metadata", "model.safetensors": b"synthetic weights",
              "1_Pooling/config.json": b'{"pooling":true}'}
    reference = tmp_path / "identity-reference"
    files = []
    for name, content in bodies.items():
        path = child_path(reference, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        files.append({"path": name, **identity(content)})
    model_identity = directory_identity(reference)
    assets["embedding"].update(files=files, expected_file_count=model_identity.file_count,
                               expected_size_bytes=model_identity.size_bytes,
                               expected_identity_sha256=model_identity.identity_sha256)
    legacy = {
        "model": {"cache_identity": {
            "identity_sha256": model_identity.identity_sha256, "file_count": model_identity.file_count,
            "size_bytes": model_identity.size_bytes,
        }},
        "source_pdfs": {},
    }
    supplied = tmp_path / "supplied-books"
    supplied.mkdir()
    for index, (book_id, book) in enumerate(assets["demo_books"]["books"].items(), 1):
        writer = PdfWriter()
        writer.add_blank_page(width=72 * index, height=72)
        destination = supplied / book["filename"]
        writer.write(destination)
        book["page_count"] = 1
        legacy["source_pdfs"][book_id] = {"path": f"books/{book['filename']}", **identity(destination.read_bytes())}
    write_json(tmp_path / "reports" / "retrieval_baseline_v1" / "manifest.json", legacy)
    tokenizer_bytes = b"synthetic tokenizer bytes"
    scorer_bytes = b"synthetic official-scorer fixture"
    license_bytes = b"synthetic license fixture"
    assets["context_tokenizer"].update(identity(tokenizer_bytes))
    assets["evaluator"]["script"]["size_bytes"] = len(scorer_bytes)
    assets["evaluator"]["license"].update(identity(license_bytes))
    small_protocol["metrics"]["scorer"]["sha256"] = identity(scorer_bytes)["sha256"]
    write_json(child_path(tmp_path, assets["protocol_file"]), small_protocol)
    write_json(child_path(tmp_path, small_protocol["selection"]["manifest"]),
               build_manifest(rows, small_protocol, review))
    write_json(tmp_path / assets_module.ASSET_MANIFEST, assets)
    base = f"https://huggingface.co/{assets['embedding']['repository']}/resolve/{assets['embedding']['revision']}/"
    downloads = {base + name: body for name, body in bodies.items()}
    downloads.update({
        assets["context_tokenizer"]["url"]: tokenizer_bytes,
        small_protocol["metrics"]["scorer"]["url"]: scorer_bytes,
        assets["evaluator"]["license"]["url"]: license_bytes,
        small_protocol["benchmark"]["download_url"]: source.read_bytes(),
    })

    def open_request(request, timeout):
        assert timeout == 120
        response = io.BytesIO(downloads[request.full_url])
        response.status = 200
        return response

    monkeypatch.setattr(assets_module.urllib.request, "urlopen", Mock(side_effect=open_request))
    return tmp_path


def test_checked_in_inventory_preserves_model_and_permission_contracts() -> None:
    assets = load_assets()
    assert len(assets["embedding"]["files"]) == 11
    assert sum(item["size_bytes"] for item in assets["embedding"]["files"]) == 134_505_940
    assert assets["demo_books"]["permission_required"] is True
    assert assets["demo_books"]["automatic_download"] is False
    assert assets["embedding"]["license"] == "MIT"


@pytest.mark.parametrize("size,sha", [(0, "a" * 64), (True, "a" * 64), (1.0, "a" * 64),
                                     (1, "a" * 63), (1, "g" * 64), (1, None)])
def test_invalid_identities_fail_explicitly(size, sha) -> None:
    with pytest.raises(ValueError):
        FileIdentity(size, sha)


@pytest.mark.parametrize("path", ["", ".", "..", "../outside", r"..\outside", "/outside",
                                     r"C:\outside", r"C:outside", r"\\server\share\file"])
def test_paths_cannot_escape_asset_root(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError):
        child_path(tmp_path, path)


@pytest.mark.parametrize("url", ["http://example.org/x", "file:///x", "https://user:secret@example.org/x", "https:///x"])
def test_downloads_require_https_without_credentials(url: str) -> None:
    with pytest.raises(ValueError):
        validate_url(url)


def test_verified_cache_is_reused_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = b"verified bytes"
    destination = tmp_path / "cached.bin"
    destination.write_bytes(content)
    opener = Mock(side_effect=AssertionError("cache reuse must not access the network"))
    monkeypatch.setattr(assets_module.urllib.request, "urlopen", opener)
    assert acquire_file("https://example.org/x", destination, FileIdentity.from_dict(identity(content))) is False
    opener.assert_not_called()


def test_wrong_existing_cache_is_not_overwritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "cached.bin"
    destination.write_bytes(b"wrong existing data")
    monkeypatch.setattr(assets_module.urllib.request, "urlopen", Mock(side_effect=AssertionError("no retry")))
    with pytest.raises(ValueError, match="pinned"):
        acquire_file("https://example.org/x", destination, FileIdentity.from_dict(identity(b"expected")))
    assert destination.read_bytes() == b"wrong existing data"


@pytest.mark.parametrize("body", [b"short", b"xxxxxxxx", b"too many bytes"])
def test_corrupt_downloads_never_publish_and_clean_owned_partial(tmp_path: Path, body: bytes) -> None:
    destination = tmp_path / "output.bin"
    with pytest.raises(ValueError, match="size|SHA"):
        assets_module._publish_stream(io.BytesIO(body), destination, FileIdentity.from_dict(identity(b"expected")))
    assert not destination.exists()
    assert not list(tmp_path.glob("*.partial"))


def test_stream_error_is_visible_and_only_owned_partial_is_removed(tmp_path: Path) -> None:
    class FailedStream:
        def read(self, _size=-1):
            raise OSError("transfer interrupted")
    untouched = tmp_path / "unrelated.partial"
    untouched.write_bytes(b"keep")
    with pytest.raises(OSError, match="interrupted"):
        assets_module._publish_stream(FailedStream(), tmp_path / "output", FileIdentity.from_dict(identity(b"expected")))
    assert list(tmp_path.iterdir()) == [untouched]


def test_atomic_publication_does_not_clobber_concurrent_writer(tmp_path: Path) -> None:
    destination = tmp_path / "output.bin"
    content = b"expected"

    def concurrent_write(_current: int) -> None:
        destination.write_bytes(b"external")

    with pytest.raises(ValueError, match="pinned"):
        assets_module._publish_stream(io.BytesIO(content), destination,
                                      FileIdentity.from_dict(identity(content)), concurrent_write)
    assert destination.read_bytes() == b"external"
    assert not list(tmp_path.glob("*.partial"))


def test_check_mode_does_not_create_directories_or_download(tmp_path: Path) -> None:
    destination = tmp_path / "missing-parent" / "output"
    with pytest.raises(FileNotFoundError, match="missing"):
        acquire_file("https://example.org/x", destination, FileIdentity.from_dict(identity(b"expected")), download=False)
    assert not destination.parent.exists()


def test_embedding_uses_only_pinned_inventory_and_reports_real_bytes(asset_root: Path) -> None:
    events = []
    result = prepare_embedding(asset_root, progress=events.append)
    assert result["file_count"] == 3
    assert result["downloaded_bytes"] == result["size_bytes"]
    requests = assets_module.urllib.request.urlopen.call_args_list
    requested = [call.args[0].full_url for call in requests]
    assert len(requested) == 3
    assert not any(url.endswith((".bin", ".onnx", ".gitattributes")) for url in requested)
    assert events[-1].processed_bytes == result["size_bytes"]
    assert events[-1].downloaded_bytes == result["size_bytes"]
    assets_module.urllib.request.urlopen.reset_mock()
    assert prepare_embedding(asset_root)["downloaded_bytes"] == 0
    assets_module.urllib.request.urlopen.assert_not_called()


def test_unexpected_embedding_files_fail_before_download(asset_root: Path) -> None:
    assets = load_assets(asset_root)
    directory = child_path(asset_root, assets["embedding"]["directory"])
    directory.mkdir(parents=True)
    (directory / "pytorch_model.bin").write_bytes(b"extra")
    with pytest.raises(ValueError, match="unexpected files"):
        prepare_embedding(asset_root)
    assets_module.urllib.request.urlopen.assert_not_called()
    assert (directory / "pytorch_model.bin").read_bytes() == b"extra"


def test_embedding_override_stays_in_requested_application_cache(asset_root: Path) -> None:
    custom = asset_root / "custom-app-data" / "snapshot"
    prepare_embedding(asset_root, directory=custom)
    assert (custom / "model.safetensors").is_file()
    assert not child_path(asset_root, load_assets(asset_root)["embedding"]["directory"]).exists()


def test_demo_import_requires_explicit_permission(asset_root: Path) -> None:
    with pytest.raises(PermissionError, match="permission"):
        import_demo_books(asset_root, asset_root / "supplied-books", authorized=False)
    assert not (asset_root / "books").exists()


def test_demo_import_verifies_identity_and_physical_pages_without_network(asset_root: Path) -> None:
    results = import_demo_books(asset_root, asset_root / "supplied-books", authorized=True)
    assert len(results) == 2
    assert all(book["page_count"] == 1 for book in results)
    assert all(book["status"] == "verified_authorized_local_input" for book in results)
    assets_module.urllib.request.urlopen.assert_not_called()


def test_missing_demo_edition_has_actionable_error(asset_root: Path) -> None:
    with pytest.raises(FileNotFoundError, match="2025-26.*--demo-books-dir"):
        import_demo_books(asset_root, asset_root / "missing-books", authorized=True)


def test_wrong_demo_file_is_rejected_without_copy(asset_root: Path) -> None:
    assets = load_assets(asset_root)
    filename = next(iter(assets["demo_books"]["books"].values()))["filename"]
    (asset_root / "supplied-books" / filename).write_bytes(b"not the specified edition")
    with pytest.raises(ValueError, match="pinned"):
        import_demo_books(asset_root, asset_root / "supplied-books", authorized=True)
    assert not (asset_root / "books").exists()


def test_demo_page_count_is_verified_not_assumed(asset_root: Path) -> None:
    assets = load_assets(asset_root)
    next(iter(assets["demo_books"]["books"].values()))["page_count"] = 2
    write_json(asset_root / assets_module.ASSET_MANIFEST, assets)
    with pytest.raises(ValueError, match="page count"):
        import_demo_books(asset_root, asset_root / "supplied-books", authorized=True)
    assert not (asset_root / "books").exists()


def test_full_preparation_and_read_only_recheck(asset_root: Path) -> None:
    result = prepare_inputs(asset_root, demo_books_dir=asset_root / "supplied-books", authorized_demo_use=True)
    report = child_path(asset_root, load_assets(asset_root)["readiness_report"])
    previous = report.read_bytes()
    assert result["benchmark"]["selected_questions"] == 4
    assert result["paid_model_calls"] == 0
    assert result["demo_scope"] == "authorized_local_inputs"
    assets_module.urllib.request.urlopen.reset_mock()
    checked = prepare_inputs(asset_root, download=False, demo_books_dir=asset_root / "supplied-books",
                             authorized_demo_use=True)
    assert checked["check_only"] is True
    assert report.read_bytes() == previous
    assets_module.urllib.request.urlopen.assert_not_called()


def test_no_demo_request_does_not_claim_demo_readiness(asset_root: Path) -> None:
    result = prepare_inputs(asset_root)
    assert result["demo_scope"] == "not_requested"
    assert result["demo_books"] == []
    assert not (asset_root / "books").exists()


def test_changed_selection_is_not_silently_rebuilt(asset_root: Path) -> None:
    protocol = read_json(asset_root / "config" / "assessment_protocol_v1.json")
    manifest = child_path(asset_root, protocol["selection"]["manifest"])
    changed = read_json(manifest)
    changed["selected_count"] += 1
    write_json(manifest, changed)
    with pytest.raises(ValueError, match="frozen selection"):
        prepare_inputs(asset_root)
    assert read_json(manifest) == changed
    assert not child_path(asset_root, load_assets(asset_root)["readiness_report"]).exists()


@pytest.mark.parametrize("directory,permission", [(None, True), (Path("books"), False)])
def test_demo_flags_must_be_paired_before_acquisition(asset_root: Path, directory, permission) -> None:
    with pytest.raises(ValueError, match="supplied together"):
        prepare_inputs(asset_root, demo_books_dir=directory, authorized_demo_use=permission)
    assets_module.urllib.request.urlopen.assert_not_called()


def test_frontend_lock_is_public_and_has_strong_integrities() -> None:
    lock = read_json(ROOT / "frontend" / "package-lock.json")
    artifacts = [value for key, value in lock["packages"].items() if key]
    assert len(artifacts) == 126
    assert all(value["resolved"].startswith("https://registry.npmjs.org/") for value in artifacts)
    assert all(value["integrity"].startswith("sha512-") for value in artifacts)
