"""Frozen local-provider configuration checks that do not load the 8B model."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import json

import pytest

from textbook_audit.generation_phase_a import LlamaServerConfig, LocalLlamaServer
from textbook_chat.config import (
    AppSettings,
    OfflineBackend,
    OfflineGenerationSettings,
)
from textbook_chat.generation.backends import (
    ADRENO_DEVICE,
    BackendInitialization,
    BackendInitializationError,
    CpuBackendStrategy,
    OpenCLGpuBackendStrategy,
    backend_strategy,
    parse_opencl_initialization,
)
from textbook_chat.generation.offline import OfflineRuntimeManager
from textbook_chat.models.offline import (
    LLAMA_ARCHIVE_SHA256,
    LLAMA_ARCHIVE_URL,
    LLAMA_OPENCL_ARCHIVE_SHA256,
    LLAMA_OPENCL_ARCHIVE_URL,
    OfflineArtifactRegistry,
)


ROOT = Path(__file__).resolve().parents[1]


def _settings(
    tmp_path: Path, backend: OfflineBackend = "cpu", allow_fallback: bool = False
) -> AppSettings:
    return AppSettings(
        ROOT, tmp_path, tmp_path / "app.db", "127.0.0.1", 8765,
        10 * 1024 * 1024, 100, False,
        OfflineGenerationSettings(backend=backend, allow_fallback=allow_fallback),
    )


def test_offline_artifact_identity_is_exact(tmp_path: Path) -> None:
    registry = OfflineArtifactRegistry(_settings(tmp_path))

    assert registry.model_repository == "Qwen/Qwen3-8B-GGUF"
    assert registry.model_revision == "7c41481f57cb95916b40956ab2f0b139b296d974"
    assert registry.model_filename == "Qwen3-8B-Q4_K_M.gguf"
    assert registry.model_sha256 == "d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785"
    assert LLAMA_ARCHIVE_URL.endswith("/b10046/llama-b10046-bin-win-cpu-arm64.zip")
    assert LLAMA_ARCHIVE_SHA256 == "7f9958be4bdfc110c4eaa7bb49eeb115573d44d80a8b9400063bc49336923f1c"
    assert LLAMA_OPENCL_ARCHIVE_URL.endswith(
        "/b10107/llama-b10107-bin-win-opencl-adreno-arm64.zip"
    )
    assert LLAMA_OPENCL_ARCHIVE_SHA256 == (
        "1adca072b5ef8203409bb75258faa5ab7476d93fcf1bd38fbc44cb68cb3b1eef"
    )


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


def test_backend_factory_routes_cpu_and_opencl() -> None:
    assert isinstance(backend_strategy("cpu"), CpuBackendStrategy)
    assert isinstance(backend_strategy("opencl_gpu"), OpenCLGpuBackendStrategy)


def test_opencl_command_changes_only_runtime_backend_arguments(tmp_path: Path) -> None:
    cpu_runtime = OfflineRuntimeManager(
        _settings(tmp_path, "cpu"), OfflineArtifactRegistry(_settings(tmp_path, "cpu"))
    )
    gpu_strategy = OpenCLGpuBackendStrategy()
    gpu_runtime = gpu_strategy.runtime_config(cpu_runtime.runtime)
    config = LlamaServerConfig(
        executable=tmp_path / "llama-server.exe",
        model=tmp_path / "Qwen3-8B-Q4_K_M.gguf",
        port=18091,
        runtime=gpu_runtime,
        generation=cpu_runtime.generation,
        log_dir=tmp_path / "logs",
        extra_arguments=gpu_strategy.extra_arguments(),
    )
    command = LocalLlamaServer(config).command()

    assert command[command.index("--n-gpu-layers") + 1] == "99"
    assert command[command.index("--device") + 1] == "GPUOpenCL"
    assert command[command.index("--log-verbosity") + 1] == "5"
    for field in (
        "context_size", "threads", "threads_batch", "batch_size",
        "ubatch_size", "parallel_slots",
    ):
        assert gpu_runtime[field] == cpu_runtime.runtime[field]
    assert config.generation is cpu_runtime.generation


def test_opencl_initialization_requires_adreno_and_complete_offload() -> None:
    valid_log = "\n".join((
        f"using device GPUOpenCL ({ADRENO_DEVICE})",
        "ggml_opencl: using kernels optimized for Adreno (GGML_OPENCL_USE_ADRENO_KERNELS)",
        "load_tensors: offloaded 37/37 layers to GPU",
    ))
    diagnostics = parse_opencl_initialization(valid_log)

    assert diagnostics.active_backend == "opencl_gpu"
    assert diagnostics.runtime_build == 10107
    assert diagnostics.selected_device == ADRENO_DEVICE
    assert diagnostics.offloaded_layers == 37

    with pytest.raises(BackendInitializationError, match="observed 12/37"):
        parse_opencl_initialization(valid_log.replace("37/37", "12/37"))
    with pytest.raises(BackendInitializationError, match="was not selected"):
        parse_opencl_initialization(valid_log.replace(ADRENO_DEVICE, "Other GPU"))


def test_opencl_missing_dll_error_is_actionable(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "opencl_gpu")
    registry = OfflineArtifactRegistry(settings)
    runtime_bin = registry.runtime_directory("opencl_gpu") / "bin"
    runtime_bin.mkdir(parents=True)
    (runtime_bin / "llama-server.exe").write_bytes(b"placeholder")
    with patch.object(registry, "verify_model", return_value=True):
        error = registry.artifact_error("opencl_gpu")

    assert error is not None
    assert "ggml-opencl.dll" in error
    assert "rerun offline setup" in error


def test_opencl_manifest_requires_checksums_for_server_and_dll(tmp_path: Path) -> None:
    registry = OfflineArtifactRegistry(_settings(tmp_path, "opencl_gpu"))
    runtime_bin = registry.runtime_directory("opencl_gpu") / "bin"
    runtime_bin.mkdir(parents=True)
    server = runtime_bin / "llama-server.exe"
    dll = runtime_bin / "ggml-opencl.dll"
    server.write_bytes(b"server")
    dll.write_bytes(b"opencl")
    files = {
        "llama-server.exe": hashlib.sha256(server.read_bytes()).hexdigest(),
        "ggml-opencl.dll": hashlib.sha256(dll.read_bytes()).hexdigest(),
    }
    manifest = {
        "schema_version": 1,
        "backend": "opencl_gpu",
        "archive_sha256": LLAMA_OPENCL_ARCHIVE_SHA256,
        "build_number": 10107,
        "commit": "c0bc8591e",
        "architecture": "windows-arm64",
        "files": files,
    }
    manifest_path = registry.runtime_manifest_for("opencl_gpu")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with patch.object(registry, "_version_matches", return_value=True):
        assert registry.verify_runtime(server, "opencl_gpu") is True
        del manifest["files"]["ggml-opencl.dll"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        assert registry.verify_runtime(server, "opencl_gpu") is False


def test_gpu_failure_does_not_fallback_by_default(tmp_path: Path) -> None:
    runtime = OfflineRuntimeManager(
        _settings(tmp_path, "opencl_gpu"), OfflineArtifactRegistry(_settings(tmp_path))
    )
    with (
        patch.object(runtime, "_start_backend", side_effect=BackendInitializationError("no offload"))
        as start,
        pytest.raises(RuntimeError, match="opencl_gpu backend initialization failed"),
    ):
        runtime.load()

    start.assert_called_once_with("opencl_gpu")


def test_explicit_gpu_fallback_is_logged_and_diagnosed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    runtime = OfflineRuntimeManager(
        _settings(tmp_path, "opencl_gpu", True), OfflineArtifactRegistry(_settings(tmp_path))
    )
    cpu_server = SimpleNamespace(load_seconds=1.25)
    cpu_ready = BackendInitialization(
        requested_backend="cpu", active_backend="cpu", runtime_build=10046,
        selected_device="CPU", offloaded_layers=0, expected_layers=0,
        initialization_status="ready",
    )
    with patch.object(
        runtime, "_start_backend",
        side_effect=[BackendInitializationError("Adreno missing"), (cpu_server, cpu_ready)],
    ) as start:
        result = runtime.load()

    assert [call.args[0] for call in start.call_args_list] == ["opencl_gpu", "cpu"]
    assert result["active_backend"] == "cpu"
    assert result["requested_backend"] == "opencl_gpu"
    assert result["fallback_used"] is True
    assert result["initialization_status"] == "ready_with_fallback"
    assert "Adreno missing" in result["initialization_error"]
    assert "falling back to CPU" in caplog.text


def test_cpu_and_gpu_share_model_request_and_generation_contract(tmp_path: Path) -> None:
    cpu_settings = _settings(tmp_path / "cpu", "cpu")
    gpu_settings = _settings(tmp_path / "gpu", "opencl_gpu")
    cpu_registry = OfflineArtifactRegistry(cpu_settings)
    gpu_registry = OfflineArtifactRegistry(gpu_settings)
    cpu = OfflineRuntimeManager(cpu_settings, cpu_registry)
    gpu = OfflineRuntimeManager(gpu_settings, gpu_registry)
    prompt = "/no_think\nidentical prompt"

    assert cpu_registry.model_filename == gpu_registry.model_filename == "Qwen3-8B-Q4_K_M.gguf"
    assert cpu_registry.model_sha256 == gpu_registry.model_sha256
    assert cpu.generation == gpu.generation
    assert cpu.request_payload(prompt) == gpu.request_payload(prompt)


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
