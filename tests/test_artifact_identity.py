"""Only explicit named UTF-8 artifacts may use the text identity v2 policy."""

import hashlib
import json

import pytest

from textbook_audit.artifact_identity import load_text_identity_profile, verify_artifact_identity


def digest(data):
    return hashlib.sha256(data).hexdigest()


def text_profile(tmp_path, relative="fixture.jsonl"):
    original = b'{"value":"one"}\r\n'
    profile = {
        "schema_version": 2, "text_policy": "utf8-crlf-to-lf-only", "artifacts": [{
            "path": relative, "historical_raw_sha256": digest(original),
            "utf8_lf_sha256": digest(original.replace(b"\r\n", b"\n")),
        }],
    }
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    return original, path


def test_v1_remains_raw_and_v2_explicitly_accepts_only_newline_equivalence(tmp_path):
    original, profile = text_profile(tmp_path)
    file = tmp_path / "fixture.jsonl"
    artifact = {"path": file.name, "sha256": digest(original)}
    identities = load_text_identity_profile(profile)
    for content, mode in ((original, "raw-sha256-v1"), (original.replace(b"\r\n", b"\n"), "utf8-lf-text-v2")):
        file.write_bytes(content)
        checked = verify_artifact_identity(tmp_path, artifact, identities)
        assert checked["valid"] and checked["verification"] == mode
    assert not verify_artifact_identity(tmp_path, artifact)["valid"]
    for changed in (
        b'{"value":"two"}\n', b'{"value": "one"}\n', b'{"value":"one"}\n\n', b"\xff\n",
        b'{"value":"one"}\r',
    ):
        file.write_bytes(changed)
        assert not verify_artifact_identity(tmp_path, artifact, identities)["valid"]
    file.write_bytes(original.replace(b"\r\n", b"\n"))
    assert not verify_artifact_identity(tmp_path, {**artifact, "sha256": "a" * 64}, identities)["valid"]


@pytest.mark.parametrize("relative", ["fixture.npz", "source.pdf", "../fixture.jsonl", "/fixture.jsonl", "C:/fixture.jsonl"])
def test_binary_and_unsafe_profile_paths_are_rejected(tmp_path, relative):
    _original, profile = text_profile(tmp_path, relative)
    with pytest.raises(ValueError, match="relative UTF-8 text paths"):
        load_text_identity_profile(profile)


@pytest.mark.parametrize("suffix", [".pdf", ".npz", ".gguf", ".whl"])
def test_binary_crlf_bytes_can_never_use_text_normalization(tmp_path, suffix):
    original = b"\x00BINARY\r\n\x00"
    relative = "asset" + suffix
    file = tmp_path / relative
    file.write_bytes(original.replace(b"\r\n", b"\n"))
    entry = {"historical_raw_sha256": digest(original), "utf8_lf_sha256": digest(file.read_bytes())}
    assert not verify_artifact_identity(
        tmp_path, {"path": relative, "sha256": digest(original)}, {relative: entry},
    )["valid"]
