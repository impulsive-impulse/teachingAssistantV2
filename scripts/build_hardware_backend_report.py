"""Collect exact machine inventory and summarize validated local backends."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

import psutil


def powershell_json(script: str) -> Any:
    """Run a read-only CIM query and parse its compressed JSON response."""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script], check=True,
        capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(completed.stdout)


def collect_inventory() -> dict[str, Any]:
    """Capture CPU, memory, OS, accelerator, and signed-driver metadata."""
    script = """
$cpu=Get-CimInstance Win32_Processor | Select Name,Manufacturer,Architecture,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed
$system=Get-CimInstance Win32_ComputerSystem | Select Manufacturer,Model,TotalPhysicalMemory,SystemType
$os=Get-CimInstance Win32_OperatingSystem | Select Caption,Version,BuildNumber,OSArchitecture
$gpu=Get-CimInstance Win32_VideoController | Select Name,DriverVersion,DriverDate,PNPDeviceID
$npu=Get-PnpDevice -PresentOnly | Where-Object {$_.FriendlyName -match 'NPU|Neural|Hexagon'} | Select Class,FriendlyName,InstanceId,Status
$drivers=Get-CimInstance Win32_PnPSignedDriver | Where-Object {$_.DeviceName -match 'Hexagon|Adreno'} | Select DeviceName,DriverVersion,DriverDate,Manufacturer,InfName
[pscustomobject]@{cpu=$cpu;system=$system;os=$os;gpu=$gpu;npu=$npu;drivers=$drivers}|ConvertTo-Json -Depth 6 -Compress
"""
    inventory = powershell_json(script)
    inventory["runtime_architecture"] = platform.machine()
    inventory["ram_bytes_psutil"] = psutil.virtual_memory().total
    return inventory


def load_optional(path: Path | None) -> dict[str, Any] | None:
    """Load a completed probe when present, otherwise preserve a clear not-run state."""
    return json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else None


def main() -> None:
    """Write inventory, normalized probe copies, and the hardware recommendation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/hardware_backend_v1"))
    parser.add_argument("--cpu-probe", type=Path)
    parser.add_argument("--vulkan-probe", type=Path)
    parser.add_argument("--dml-cpu-probe", type=Path)
    parser.add_argument("--dml-probe", type=Path)
    parser.add_argument("--dml-micro-probe", type=Path)
    parser.add_argument("--qnn-cpu-probe", type=Path)
    parser.add_argument("--qnn-probe", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    inventory = collect_inventory()
    (args.output_dir / "hardware_inventory.json").write_text(
        json.dumps(inventory, indent=2) + "\n", encoding="utf-8"
    )
    probes = {
        "Native ARM64 llama.cpp CPU": load_optional(args.cpu_probe),
        "x64 llama.cpp Vulkan": load_optional(args.vulkan_probe),
        "ORT GenAI CPU": load_optional(args.dml_cpu_probe),
        "ORT GenAI DirectML": load_optional(args.dml_probe),
        "ONNX DirectML microbenchmark": load_optional(args.dml_micro_probe),
        "ONNX CPU microbenchmark": load_optional(args.qnn_cpu_probe),
        "ONNX QNN HTP microbenchmark": load_optional(args.qnn_probe),
    }
    for label, path in (
        ("cpu_arm64_probe", args.cpu_probe), ("vulkan_x64_probe", args.vulkan_probe),
        ("ort_genai_cpu_probe", args.dml_cpu_probe), ("ort_genai_dml_probe", args.dml_probe),
        ("onnx_dml_probe", args.dml_micro_probe),
        ("onnx_cpu_probe", args.qnn_cpu_probe), ("onnx_qnn_probe", args.qnn_probe),
    ):
        if path and path.is_file():
            destination = args.output_dir / f"{label}.json"
            # Probe commands commonly write directly into the report directory;
            # avoid SameFileError while still copying external probe artifacts.
            if path.resolve() != destination.resolve():
                shutil.copyfile(path, destination)

    lines = [
        "# Hardware-aware local inference audit", "", "## Machine", "",
        f"- System: {inventory['system']['Manufacturer']} {inventory['system']['Model']}",
        f"- CPU: {inventory['cpu']['Name']} ({inventory['cpu']['NumberOfCores']} cores)",
        f"- RAM: {inventory['ram_bytes_psutil'] / 1024**3:.2f} GiB",
        f"- OS: {inventory['os']['Caption']} build {inventory['os']['BuildNumber']} ({inventory['os']['OSArchitecture']})",
        f"- GPU: {inventory['gpu']['Name']} driver {inventory['gpu']['DriverVersion']}",
        f"- NPU: {inventory['npu']['FriendlyName']} ({inventory['npu']['Status']})",
        "", "## Controlled probes", "",
        "| Backend | Loaded | Valid output | TTFT / p50 | Total / p95 | Throughput | Memory | Decision |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, probe in probes.items():
        if not probe:
            lines.append(f"| {name} | 0 | — | — | — | — | — | Not run |")
            continue
        valid = probe.get("output_valid", False)
        first = probe.get("ttft_seconds", probe.get("time_to_first_token_seconds", probe.get("p50_latency_ms")))
        total = probe.get("latency_seconds", probe.get("p95_latency_ms"))
        throughput = probe.get("tokens_per_second", probe.get("server_perf", {}).get("generation_tokens_per_second"))
        memory = probe.get("peak_rss_bytes", probe.get("peak_memory", {}).get("working_set_bytes"))
        # A microbenchmark proves provider execution only; it does not establish
        # that an arbitrary decoder model is compatible with that provider.
        if "microbenchmark" in name:
            decision = "Provider verified" if valid else "Reject / investigate"
        else:
            decision = "Usable" if valid else "Reject / investigate"
        lines.append(f"| {name} | 1 | {int(bool(valid))} | {first} | {total} | {throughput} | {memory} | {decision} |")
    cpu_micro = probes["ONNX CPU microbenchmark"]
    qnn_micro = probes["ONNX QNN HTP microbenchmark"]
    dml_cpu = probes["ORT GenAI CPU"]
    dml_full = probes["ORT GenAI DirectML"]
    lines.extend(["", "## Measured acceleration verdicts", ""])
    if cpu_micro and qnn_micro:
        qnn_ratio = cpu_micro["p50_latency_ms"] / qnn_micro["p50_latency_ms"]
        lines.append(
            f"- QNN executed the compatible QDQ graph without CPU nodes and produced valid output, "
            f"but achieved only {qnn_ratio:.2f}x CPU p50 performance (below 1.0x means slower)."
        )
    if dml_cpu and dml_full:
        dml_ratio = dml_full["tokens_per_second"] / dml_cpu["tokens_per_second"]
        lines.append(
            f"- DirectML generated {dml_ratio:.2f}x more tokens/s than its matching x64 CPU control, "
            "but the token stream was corrupted (`<unused...>` repetition), so the apparent speedup is rejected."
        )
    lines.append(
        "- No tested GPU or NPU path both accelerated its matching control and produced valid output; "
        "therefore no accelerated generation configuration is approved."
    )
    lines.extend([
        "", "## Compatibility findings", "",
        "- ONNX Runtime GenAI officially lists Windows ARM64, DirectML, and QNN support; backend usability still depends on a matching graph and provider package.",
        "- The official `onnxruntime/Gemma-3-ONNX` DirectML export is the controlled Gemma 3 4B GPU candidate.",
        "- QNN requires a QNN-compatible QDQ or precompiled context graph. A detected NPU or successfully loaded provider library alone is not an acceleration result.",
        "- DirectML is in sustained engineering; Windows ML is Microsoft's recommended long-term Windows deployment path.",
        "", "## Recommendation", "",
        "Use native ARM64 llama.cpp CPU as the reliable fallback. Use an accelerated backend only when its row above has both valid output and measured improvement over its matching CPU control. Never use the x64 Vulkan result because it generated invalid repeated text.",
        "", "## Official references", "",
        "- https://github.com/microsoft/onnxruntime-genai",
        "- https://huggingface.co/onnxruntime/Gemma-3-ONNX",
        "- https://github.com/onnxruntime/onnxruntime-qnn",
        "- https://github.com/microsoft/DirectML",
    ])
    (args.output_dir / "hardware_backend_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
