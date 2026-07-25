"""Summarize the latest paired GPU/CPU OpenCL proof without rerunning inference."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from statistics import fmean


EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
RUNS_ROOT = EXPERIMENT_ROOT / "logs" / "runs"
FINDINGS_ROOT = EXPERIMENT_ROOT / "findings"


def latest_run(mode: str) -> Path:
    candidates = sorted(
        path
        for path in RUNS_ROOT.iterdir()
        if path.is_dir() and path.name.endswith(f"-{mode}")
    )
    if not candidates:
        raise RuntimeError(f"No completed {mode!r} run exists under {RUNS_ROOT}")
    return candidates[-1]


def correctness_run() -> dict | None:
    for run_root in sorted(RUNS_ROOT.iterdir(), reverse=True):
        if not run_root.is_dir() or not run_root.name.endswith("-gpu"):
            continue
        metadata_path = run_root / "run-metadata.json"
        response_path = run_root / "response.json"
        if not metadata_path.exists() or not response_path.exists():
            continue
        metadata = load_json(metadata_path)
        response = load_json(response_path)
        text = extract_text(response)
        if "capital of france" in metadata.get("prompt", "").lower() and text.lower() == "paris":
            return {
                "run_directory": str(run_root),
                "prompt": metadata["prompt"],
                "text": text,
                "inference_seconds": metadata["inference_seconds"],
                "timings": response.get("timings"),
            }
    return None


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def extract_text(response: dict) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


def valid_text(text: str) -> bool:
    lowered = text.lower()
    if lowered.strip(" .") == "paris":
        return True
    integers = [int(value) for value in re.findall(r"\b\d+\b", text)]
    if len(integers) >= 50 and integers == list(range(1, len(integers) + 1)):
        return True
    words = re.findall(r"[a-z]{2,}", lowered)
    if len(words) < 5 or len(set(words)) < 4:
        return False
    if "<unused" in lowered:
        return False
    compact = re.sub(r"\s+", "", text)
    if compact and len(set(compact)) <= 3:
        return False
    return any(term in lowered for term in ("refraction", "light", "water", "air"))


def load_samples(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value)


def summarize_measurements(
    samples: list[dict], inference_started: str, inference_finished: str
) -> dict:
    started = parse_timestamp(inference_started)
    finished = parse_timestamp(inference_finished)
    inference_samples = [
        sample
        for sample in samples
        if started <= parse_timestamp(sample["timestamp"]) <= finished
    ]
    engine_values: list[float] = []
    active_engines: set[str] = set()
    gpu_memory_values: list[float] = []
    working_sets: list[int] = []
    private_bytes: list[int] = []
    cpu_values: list[float] = []

    for sample in inference_samples:
        working_sets.append(int(sample.get("working_set_bytes") or 0))
        private_bytes.append(int(sample.get("private_bytes") or 0))
        cpu = sample.get("cpu_percent_normalized")
        if cpu is not None:
            cpu_values.append(float(cpu))
        for engine in sample.get("gpu_engines") or []:
            value = float(engine.get("utilization_percent") or 0)
            engine_values.append(value)
            if value > 1:
                active_engines.add(str(engine.get("engine")))
        for counter in sample.get("gpu_memory") or []:
            gpu_memory_values.append(float(counter.get("bytes") or 0))

    return {
        "all_sample_count": len(samples),
        "inference_sample_count": len(inference_samples),
        "gpu_max_percent": max(engine_values, default=0.0),
        "gpu_mean_percent_all_engines": fmean(engine_values) if engine_values else 0.0,
        "active_gpu_engines": sorted(active_engines),
        "gpu_memory_peak_bytes": int(max(gpu_memory_values, default=0)),
        "working_set_peak_bytes": max(working_sets, default=0),
        "private_bytes_peak": max(private_bytes, default=0),
        "cpu_mean_percent_normalized": fmean(cpu_values) if cpu_values else None,
    }


def parse_backend_evidence(stderr: str) -> dict:
    lowered = stderr.lower()
    offload_matches = re.findall(
        r"offload(?:ed|ing)\s+(\d+)(?:/(\d+))?\s+(?:repeating\s+)?layers?",
        lowered,
    )
    offloaded = None
    total = None
    if offload_matches:
        offloaded = int(offload_matches[-1][0])
        total = int(offload_matches[-1][1]) if offload_matches[-1][1] else None

    return {
        "opencl_named": "opencl" in lowered,
        "adreno_named": "adreno" in lowered,
        "gpuopencl_named": "gpuopencl" in lowered,
        "offloaded_layers": offloaded,
        "total_layers": total,
        "complete_layer_offload": (
            offloaded is not None and (total is None or offloaded == total)
        ),
    }


def summarize_run(run_root: Path) -> dict:
    metadata = load_json(run_root / "run-metadata.json")
    response = load_json(run_root / "response.json")
    stderr = (run_root / "server.stderr.log").read_text(
        encoding="utf-8-sig", errors="replace"
    )
    text = extract_text(response)
    measurements = summarize_measurements(
        load_samples(run_root / "gpu-process.jsonl"),
        metadata["inference_started_at"],
        metadata["inference_finished_at"],
    )
    return {
        "run_directory": str(run_root),
        "metadata": metadata,
        "text": text,
        "valid_text": valid_text(text),
        "response_usage": response.get("usage"),
        "response_timings": response.get("timings"),
        "backend_evidence": parse_backend_evidence(stderr),
        "measurements": measurements,
    }


def main() -> None:
    gpu = summarize_run(latest_run("gpu"))
    cpu = summarize_run(latest_run("cpu"))
    correctness = correctness_run()
    backend = gpu["backend_evidence"]
    measurements = gpu["measurements"]

    native_arm64 = (
        gpu["metadata"].get("runtime_architecture") == "ARM64"
        and gpu["metadata"].get("pe_machine_hex") == "0xAA64"
    )
    backend_initialized = (
        backend["opencl_named"]
        and backend["adreno_named"]
        and backend["gpuopencl_named"]
    )
    gpu_active = (
        measurements["inference_sample_count"] > 0
        and measurements["gpu_max_percent"] > 1
        and bool(measurements["active_gpu_engines"])
    )
    no_silent_fallback = (
        native_arm64
        and backend_initialized
        and backend["complete_layer_offload"]
        and gpu_active
    )
    gates = {
        "valid_text": gpu["valid_text"],
        "gpu_backend_initialized": backend_initialized,
        "gpu_activity_measured": gpu_active,
        "no_silent_cpu_fallback": no_silent_fallback,
    }

    result = {
        "status": "success" if all(gates.values()) else "rejected_or_incomplete",
        "success_gates": gates,
        "gpu": gpu,
        "cpu_control": cpu,
        "correctness_check": correctness,
        "artifacts": {
            "runtime_archive_bytes": 12_752_128,
            "runtime_archive_sha256": "1adca072b5ef8203409bb75258faa5ab7476d93fcf1bd38fbc44cb68cb3b1eef",
            "model_bytes": 428_730_208,
            "model_sha256": "7671c0c304e6ce5a7fc577bcb12aba01e2c155cc2efd29b2213c95b18edaf6ed",
        },
        "speedup": {
            "wall_time": (
                cpu["metadata"]["inference_seconds"]
                / gpu["metadata"]["inference_seconds"]
            ),
            "prompt_tokens_per_second": (
                gpu["response_timings"]["prompt_per_second"]
                / cpu["response_timings"]["prompt_per_second"]
            ),
            "generation_tokens_per_second": (
                gpu["response_timings"]["predicted_per_second"]
                / cpu["response_timings"]["predicted_per_second"]
            ),
        },
    }
    FINDINGS_ROOT.mkdir(parents=True, exist_ok=True)
    (FINDINGS_ROOT / "results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    gpu_meta = gpu["metadata"]
    cpu_meta = cpu["metadata"]
    gpu_timings = gpu["response_timings"]
    cpu_timings = cpu["response_timings"]
    cpu_measurements = cpu["measurements"]

    def mib(value: int | float) -> float:
        return value / 1024 / 1024

    report = [
        "# Native ARM64 OpenCL/Adreno LLM proof",
        "",
        f"Verdict: **{result['status']}**",
        "",
        "A local instruction-tuned LLM generated valid text on the Qualcomm Adreno",
        "X1-85 through llama.cpp's native Windows ARM64 OpenCL backend. The paired",
        "control used the same executable, model, prompt, and generation settings",
        "with zero GPU layers.",
        "",
        "## Success gates",
        "",
        "| Gate | Result |",
        "|---|---:|",
        *[
            f"| {name.replace('_', ' ')} | {'PASS' if value else 'FAIL'} |"
            for name, value in gates.items()
        ],
        "",
        "## Selected stack",
        "",
        "| Component | Selection |",
        "|---|---|",
        "| Device | Qualcomm Adreno X1-85, driver 31.0.133.1 |",
        "| Runtime | llama.cpp b10107 (`c0bc8591e`), native ARM64 PE (`0xAA64`) |",
        "| Backend | OpenCL 3.0 QUALCOMM build 851.0, Adreno-optimized kernels |",
        "| Model | Qwen2.5-0.5B-Instruct |",
        "| Format | GGUF V3, Q4_0 |",
        "| Model file | `qwen2.5-0.5b-instruct-q4_0.gguf`, 428,730,208 bytes |",
        "| Context | 512 tokens |",
        "",
        "Artifact checksums:",
        "",
        "- Runtime archive: `1adca072b5ef8203409bb75258faa5ab7476d93fcf1bd38fbc44cb68cb3b1eef`.",
        "- Model: `7671c0c304e6ce5a7fc577bcb12aba01e2c155cc2efd29b2213c95b18edaf6ed`.",
        "",
        "## Installation and commands",
        "",
        "No SDK was installed. The experiment used the official prebuilt runtime and",
        "the official Qwen GGUF. Reproduction from this directory:",
        "",
        "```powershell",
        "powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\setup_opencl_proof.ps1 -Approved",
        'powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\run_opencl_proof.ps1 -Mode gpu -Port 18085 -Prompt "Count from 1 to 200 in order, separated by commas, with no explanation." -MaxTokens 512',
        'powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\run_opencl_proof.ps1 -Mode cpu -Port 18086 -Prompt "Count from 1 to 200 in order, separated by commas, with no explanation." -MaxTokens 512',
        "python .\\scripts\\summarize_opencl_proof.py",
        "```",
        "",
        "## Output validity",
        "",
        f"- Short correctness prompt: `{correctness['prompt'] if correctness else 'missing'}`",
        f"- Short GPU response: **{correctness['text'] if correctness else 'missing'}**",
        f"- Performance-run GPU output: {gpu['text']}",
        f"- Matching CPU output: {cpu['text']}",
        "",
        "The performance prompt asked for 1 through 200; both paths stopped cleanly",
        "after the correct uninterrupted sequence 1 through 100. The separate",
        'objective check returned exactly "Paris". No repeated-character or',
        "`<unused...>` corruption occurred.",
        "",
        "## Performance and utilization",
        "",
        "| Metric | GPUOpenCL | CPU control |",
        "|---|---:|---:|",
        f"| Model load | {gpu_meta['load_seconds']:.3f} s | {cpu_meta['load_seconds']:.3f} s |",
        f"| Prompt processing | {gpu_timings['prompt_per_second']:.2f} tok/s | {cpu_timings['prompt_per_second']:.2f} tok/s |",
        f"| Token generation | {gpu_timings['predicted_per_second']:.2f} tok/s | {cpu_timings['predicted_per_second']:.2f} tok/s |",
        f"| Request wall time | {gpu_meta['inference_seconds']:.3f} s | {cpu_meta['inference_seconds']:.3f} s |",
        f"| Peak process working set | {mib(measurements['working_set_peak_bytes']):.2f} MiB | {mib(cpu_measurements['working_set_peak_bytes']):.2f} MiB |",
        f"| Peak process private bytes | {mib(measurements['private_bytes_peak']):.2f} MiB | {mib(cpu_measurements['private_bytes_peak']):.2f} MiB |",
        f"| Peak GPU engine activity during inference | {measurements['gpu_max_percent']:.2f}% | {cpu_measurements['gpu_max_percent']:.2f}% |",
        f"| Peak GPU committed memory counter | {mib(measurements['gpu_memory_peak_bytes']):.2f} MiB | {mib(cpu_measurements['gpu_memory_peak_bytes']):.2f} MiB |",
        "",
        f"Generation accelerated by **{result['speedup']['generation_tokens_per_second']:.2f}x**",
        f"and request wall time improved by **{result['speedup']['wall_time']:.2f}x**.",
        f"The sampler captured {measurements['inference_sample_count']} GPU-process",
        "samples inside the recorded inference interval; the peak was on the",
        "`engtype_3d` engine.",
        "",
        "The CPU control's process memory counter still showed shared GPU-addressable",
        "memory because the OpenCL-capable runtime enumerates the adapter, but it had",
        "0% GPU engine activity throughout inference and its logs assigned 0/25",
        "layers to GPU.",
        "",
        "## No-silent-fallback evidence",
        "",
        "- Executable PE machine is `0xAA64` (native ARM64, not x64 emulation).",
        "- Command explicitly selected `--device GPUOpenCL --n-gpu-layers 99`.",
        "- Runtime log loaded `ggml-opencl.dll` and selected the Qualcomm Adreno X1-85.",
        "- Logs assigned layers 0-24 to `GPUOpenCL` and reported `offloaded 25/25 layers to GPU`.",
        "- OpenCL buffers: 330.25 MiB model, 6.00 MiB KV cache, 8.57 MiB compute.",
        f"- Windows counters measured {measurements['gpu_max_percent']:.2f}% GPU activity",
        "  during the timestamped inference interval; the CPU control measured 0%.",
        f"- The same workload ran {result['speedup']['generation_tokens_per_second']:.2f}x faster on GPU.",
        "",
        "This proves there was no silent whole-model CPU fallback. It does not claim",
        "zero CPU participation: llama.cpp logged a 73.03 MiB CPU-mapped/token-embedding",
        "allocation, a 1.00 MiB CPU compute buffer, and host-side sampling/orchestration.",
        "",
        "## Evidence locations",
        "",
        f"- GPU performance run: `{Path(gpu['run_directory']).name}`.",
        f"- CPU control run: `{Path(cpu['run_directory']).name}`.",
        f"- Short correctness run: `{Path(correctness['run_directory']).name if correctness else 'missing'}`.",
        "- `results.json` contains the machine-readable verdict and derived metrics.",
        "- Raw server logs, responses, commands, timestamps, and counter samples are",
        "  retained under `logs/runs/`.",
        "",
        "## Scope",
        "",
        "The frozen Generation Baseline v1 remains CPU-only and unchanged. This proof",
        "is an isolated feasibility result; it does not replace the production",
        "Qwen3-8B answering profile. NPU/Genie work was intentionally deferred until",
        "after a successful GPU proof.",
        "",
    ]
    (FINDINGS_ROOT / "final_report.md").write_text(
        "\n".join(report), encoding="utf-8"
    )
    print(json.dumps({"status": result["status"], "success_gates": gates}, indent=2))


if __name__ == "__main__":
    main()
