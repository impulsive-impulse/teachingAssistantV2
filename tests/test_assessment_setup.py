"""Standard-library bootstrap safety and offline package-source checks."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("assessment_setup", ROOT / "scripts" / "setup_assessment.py")
assert SPEC is not None and SPEC.loader is not None
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


def test_bootstrap_cleans_private_configuration_only_in_child_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIP_INDEX_URL", "https://private.invalid/simple")
    monkeypatch.setenv("PIP_TRUSTED_HOST", "private.invalid")
    monkeypatch.setenv("NPM_CONFIG_REGISTRY", "https://private.invalid")
    monkeypatch.setenv("PYTHONPATH", "private-packages")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("HTTPS_PROXY", "https://transport.invalid")
    clean = setup.clean_environment()
    assert "PIP_INDEX_URL" not in clean
    assert "PIP_TRUSTED_HOST" not in clean
    assert "NPM_CONFIG_REGISTRY" not in clean
    assert "PYTHONPATH" not in clean
    assert "OPENAI_API_KEY" not in clean
    assert clean["HTTPS_PROXY"] == "https://transport.invalid"
    assert setup.os.environ["OPENAI_API_KEY"] == "synthetic-test-key"


@pytest.mark.parametrize("index", ["http://example.org/simple", "https://user:secret@example.org/simple",
                                       "https://example.org/simple?token=x"])
def test_index_cannot_disable_tls_or_expose_credentials(index: str) -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        setup.validate_index(index)


def test_cpu_profile_checks_process_architecture_not_host_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup.sys, "version_info", (3, 12, 10))
    monkeypatch.setattr(setup.sysconfig, "get_platform", lambda: "win-amd64")
    setup.require_supported_python()
    monkeypatch.setattr(setup.sysconfig, "get_platform", lambda: "win-arm64")
    with pytest.raises(RuntimeError, match="x64"):
        setup.require_supported_python()


def test_windows_path_limit_accepts_exact_boundary() -> None:
    directory = Path("x" * setup.MAX_SETUP_PATH_LENGTH)
    setup.validate_setup_paths(directory, directory)


@pytest.mark.parametrize("target", ["checkout", "environment"])
def test_windows_path_limit_rejects_above_boundary(target: str) -> None:
    short, long = Path("short"), Path("x" * (setup.MAX_SETUP_PATH_LENGTH + 1))
    root, directory = (long, short) if target == "checkout" else (short, long)
    with pytest.raises(RuntimeError, match="path is too long"):
        setup.validate_setup_paths(root, directory)


def test_bootstrap_never_reuses_an_unowned_environment(tmp_path: Path) -> None:
    directory = tmp_path / "user-environment"
    directory.mkdir()
    (directory / "important.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unowned"):
        setup.create_environment(tmp_path, directory, {})
    assert (directory / "important.txt").read_text() == "keep"
    assert len(list(directory.iterdir())) == 1


def test_bootstrap_rejects_another_projects_owned_environment(tmp_path: Path) -> None:
    directory = tmp_path / "other-environment"
    directory.mkdir()
    (directory / "pyvenv.cfg").write_text("include-system-site-packages = false", encoding="utf-8")
    marker = directory / setup.OWNERSHIP_MARKER
    marker.write_text(json.dumps({"profile": "assessment-windows-py312-cpu", "project_root": "another-project"}))
    with pytest.raises(RuntimeError, match="different profile or project"):
        setup.create_environment(tmp_path, directory, {})


def test_offline_direct_url_keeps_hash_and_uses_local_wheel(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    filename = "torch-2.13.0+cpu-cp312-cp312-win_amd64.whl"
    wheel = wheelhouse / filename
    wheel.write_bytes(b"synthetic wheel; pip must still verify its pinned hash")
    sha = "a" * 64
    lock.write_text(
        f"torch @ https://download-r2.pytorch.org/whl/cpu/{filename.replace('+', '%2B')}#sha256={sha} \\\n"
        f"    --hash=sha256:{sha}\n"
        "numpy==2.5.1 \\\n    --hash=sha256:" + "b" * 64 + "\n",
        encoding="utf-8",
    )
    offline = setup.offline_requirements(lock, wheelhouse, tmp_path).read_text()
    assert wheel.resolve().as_uri() in offline
    assert "--hash=sha256:" + sha in offline
    assert "numpy==2.5.1" in offline
    assert "download-r2.pytorch.org" not in offline
    assert "download-r2.pytorch.org" in lock.read_text()


def test_missing_direct_url_wheel_cannot_trigger_silent_network_fallback(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock"
    lock.write_text("torch @ https://example.org/missing.whl\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="missing from wheelhouse"):
        setup.offline_requirements(lock, tmp_path, tmp_path)


def test_demo_flags_are_checked_before_creating_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(setup, "require_supported_python", lambda: None)
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (tmp_path / "requirements").mkdir()
    (tmp_path / setup.LOCK).write_text("synthetic lock", encoding="utf-8")
    with pytest.raises(ValueError, match="supplied together"):
        setup.main(["--root", str(tmp_path), "--authorized-demo-use"])
    assert not (tmp_path / ".venv-assessment").exists()
