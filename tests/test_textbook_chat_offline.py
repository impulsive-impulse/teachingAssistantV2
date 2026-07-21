"""Frozen local-provider configuration checks that do not load the 8B model."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json

from textbook_chat.config import AppSettings
from textbook_chat.generation.offline import OfflineRuntimeManager
from textbook_chat.models.offline import (
    LLAMA_ARCHIVE_SHA256,
    LLAMA_ARCHIVE_URL,
    OfflineArtifactRegistry,
)


ROOT = Path(__file__).resolve().parents[1]


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        ROOT, tmp_path, tmp_path / "app.db", "127.0.0.1", 8765,
        10 * 1024 * 1024, 100, False,
    )


def test_offline_artifact_identity_is_exact(tmp_path: Path) -> None:
    registry = OfflineArtifactRegistry(_settings(tmp_path))

    assert registry.model_repository == "Qwen/Qwen3-8B-GGUF"
    assert registry.model_revision == "7c41481f57cb95916b40956ab2f0b139b296d974"
    assert registry.model_filename == "Qwen3-8B-Q4_K_M.gguf"
    assert registry.model_sha256 == "d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785"
    assert LLAMA_ARCHIVE_URL.endswith("/b10046/llama-b10046-bin-win-cpu-arm64.zip")
    assert LLAMA_ARCHIVE_SHA256 == "7f9958be4bdfc110c4eaa7bb49eeb115573d44d80a8b9400063bc49336923f1c"


def test_offline_request_matches_evaluated_cpu_profile(tmp_path: Path) -> None:
    registry = OfflineArtifactRegistry(_settings(tmp_path))
    runtime = OfflineRuntimeManager(_settings(tmp_path), registry)
    payload = runtime.request_payload("/no_think\nprompt")

    assert runtime.runtime == {
        "engine": "llama.cpp",
        "build_number": 10046,
        "build_commit": "32e789fdfd598e9a1872da55ac941e4d94f030bd",
        "architecture": "windows-arm64",
        "backend": "cpu",
        "context_size": 8192,
        "threads": 10,
        "threads_batch": 10,
        "batch_size": 512,
        "ubatch_size": 256,
        "gpu_layers": 0,
        "parallel_slots": 1,
    }
    assert payload["temperature"] == 0.0
    assert payload["seed"] == 42
    assert payload["max_tokens"] == 384
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert payload["response_format"] == {"type": "json_object"}


def test_x64_python_on_native_windows_arm64_is_compatible(tmp_path: Path) -> None:
    registry = OfflineArtifactRegistry(_settings(tmp_path))
    with (
        patch("textbook_chat.models.offline.platform.system", return_value="Windows"),
        patch("textbook_chat.models.offline.platform.machine", return_value="AMD64"),
        patch.dict("os.environ", {"PROCESSOR_ARCHITEW6432": "ARM64"}, clear=False),
    ):
        assert registry.compatibility_error() is None


def test_offline_stream_discards_reasoning_and_emits_answer_delta(tmp_path: Path) -> None:
    registry = OfflineArtifactRegistry(_settings(tmp_path))
    runtime = OfflineRuntimeManager(_settings(tmp_path), registry)
    runtime._server = SimpleNamespace(config=SimpleNamespace(port=12345))  # type: ignore[assignment]
    output = json.dumps({
        "status": "answered", "answer": "Grounded answer.",
        "selected_evidence_ids": ["E1"], "citations": [], "missing_information": [],
    })
    chunks = [
        {"id": "local-1", "choices": [{"delta": {"reasoning_content": "hidden"}}]},
        {"id": "local-1", "choices": [{"delta": {"content": output[:40]}}]},
        {"id": "local-1", "choices": [{"delta": {"content": output[40:]}}]},
        {"id": "local-1", "usage": {"prompt_tokens": 90, "completion_tokens": 15, "total_tokens": 105}, "choices": []},
    ]
    lines = [f"data: {json.dumps(chunk)}\n".encode() for chunk in chunks] + [b"data: [DONE]\n"]

    class FakeResponse(list):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    with (
        patch.object(runtime, "load", return_value={"state": "loaded", "load_seconds": 1.2}),
        patch("textbook_chat.generation.offline.urllib.request.urlopen", return_value=FakeResponse(lines)),
    ):
        events = list(runtime.stream("/no_think\nprompt"))

    assert "".join(event.data["delta"] for event in events if event.type == "answer_delta") == "Grounded answer."
    completed = events[-1].data
    assert completed["raw_text"] == output
    assert "hidden" not in completed["raw_text"]
    assert completed["usage"] == {
        "prompt_tokens": 90, "completion_tokens": 15, "total_tokens": 105,
    }
