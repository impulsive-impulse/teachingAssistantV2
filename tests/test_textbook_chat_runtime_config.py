"""Typed operational backend settings stay separate from frozen v1 files."""

from pathlib import Path

import pytest

from textbook_chat.config import AppSettings


def _write_runtime(root: Path, text: str) -> None:
    config = root / "config"
    config.mkdir(parents=True)
    (config / "runtime.yaml").write_text(text, encoding="utf-8")


def test_cpu_is_the_default_when_runtime_file_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TEXTBOOK_CHAT_OFFLINE_BACKEND", raising=False)
    monkeypatch.delenv("TEXTBOOK_CHAT_OFFLINE_ALLOW_FALLBACK", raising=False)
    settings = AppSettings.load(tmp_path)

    assert settings.offline_generation.backend == "cpu"
    assert settings.offline_generation.allow_fallback is False


def test_opencl_gpu_configuration_is_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TEXTBOOK_CHAT_OFFLINE_BACKEND", raising=False)
    monkeypatch.delenv("TEXTBOOK_CHAT_OFFLINE_ALLOW_FALLBACK", raising=False)
    _write_runtime(
        tmp_path,
        "offline_generation:\n  backend: opencl_gpu\n  allow_fallback: true\n",
    )
    settings = AppSettings.load(tmp_path)

    assert settings.offline_generation.backend == "opencl_gpu"
    assert settings.offline_generation.allow_fallback is True


@pytest.mark.parametrize("backend", ["cuda", "vulkan", ""])
def test_unknown_backend_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend: str
) -> None:
    monkeypatch.delenv("TEXTBOOK_CHAT_OFFLINE_BACKEND", raising=False)
    _write_runtime(
        tmp_path,
        f"offline_generation:\n  backend: {backend!r}\n  allow_fallback: false\n",
    )
    with pytest.raises(ValueError, match="backend must be one of"):
        AppSettings.load(tmp_path)


def test_environment_override_requires_explicit_boolean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEXTBOOK_CHAT_OFFLINE_ALLOW_FALLBACK", "sometimes")
    with pytest.raises(ValueError, match="must be a boolean"):
        AppSettings.load(tmp_path)
