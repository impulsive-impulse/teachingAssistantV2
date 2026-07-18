"""Probe CPU, DirectML, or QNN with the same deterministic ONNX MatMul graph.

This is a backend-functionality microbenchmark, not an LLM quality benchmark.
CPU fallback is disabled for accelerated sessions so a successful run proves
that the requested provider accepted the graph.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import time
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort


def build_fixture(path: Path, width: int = 256, quantize: bool = False) -> None:
    """Create a static MatMul+Relu graph, optionally converted to QDQ INT8."""
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    rng = np.random.default_rng(42)
    weight = (rng.standard_normal((width, width), dtype=np.float32) /
              np.float32(np.sqrt(width))).astype(np.float32)
    graph = helper.make_graph(
        [helper.make_node("MatMul", ["input", "weight"], ["product"]),
         helper.make_node("Relu", ["product"], ["output"])],
        "backend_probe",
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, width])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, width])],
        [numpy_helper.from_array(weight, "weight")],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 10
    path.parent.mkdir(parents=True, exist_ok=True)
    if not quantize:
        onnx.save(model, path)
        return
    float_path = path.with_suffix(".float.onnx")
    onnx.save(model, float_path)
    from onnxruntime.quantization import (
        CalibrationDataReader, QuantFormat, QuantType, quantize_static,
    )

    class Reader(CalibrationDataReader):
        """Supply one deterministic calibration sample for the synthetic graph."""

        def __init__(self) -> None:
            """Initialize the one-row deterministic calibration iterator."""
            self._rows = iter([{"input": np.ones((1, width), dtype=np.float32)}])

        def get_next(self):
            """Return the next calibration mapping, or ``None`` when exhausted."""
            return next(self._rows, None)

    quantize_static(
        float_path, path, Reader(), quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8,
        per_channel=True,
    )
    float_path.unlink(missing_ok=True)


def percentile(values: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile in milliseconds."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.5))]


def main() -> None:
    """Load the selected provider, verify output, and record controlled timings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("cpu", "dml", "qnn"), required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--build-model", action="store_true")
    parser.add_argument("--quantize", action="store_true")
    args = parser.parse_args()
    if args.build_model or not args.model.is_file():
        build_fixture(args.model, quantize=args.quantize)

    options = ort.SessionOptions()
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.enable_mem_pattern = False
    # Disable CPU fallback only for accelerated probes. Applying this option to
    # the CPU control itself is contradictory and newer ORT builds reject it.
    if args.provider != "cpu":
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
    options.enable_profiling = True
    providers: list[Any]
    if args.provider == "cpu":
        providers = ["CPUExecutionProvider"]
    elif args.provider == "dml":
        providers = ["DmlExecutionProvider"]
    else:
        import onnxruntime_qnn as qnn
        ort.register_execution_provider_library(qnn.get_ep_name(), qnn.get_library_path())
        devices = [device for device in ort.get_ep_devices()
                   if device.ep_name == qnn.get_ep_name()]
        if not devices:
            raise RuntimeError("QNN plugin registered but exposed no execution-provider device")
        options.add_provider_for_devices(devices, {
            "backend_path": qnn.get_qnn_htp_path(),
            "htp_performance_mode": "burst",
            "enable_htp_fp16_precision": "1",
        })
        providers = []

    load_start = time.perf_counter()
    session = ort.InferenceSession(
        str(args.model), sess_options=options,
        providers=providers if providers else None,
    )
    load_seconds = time.perf_counter() - load_start
    rng = np.random.default_rng(7)
    value = rng.standard_normal((1, 256), dtype=np.float32)
    for _ in range(10):
        session.run(None, {"input": value})
    timings = []
    output = None
    for _ in range(args.iterations):
        started = time.perf_counter()
        output = session.run(None, {"input": value})[0]
        timings.append((time.perf_counter() - started) * 1000)
    profile_path = Path(session.end_profiling())
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    provider_nodes: dict[str, int] = {}
    for event in profile:
        provider = event.get("args", {}).get("provider")
        if event.get("cat") == "Node" and provider:
            provider_nodes[provider] = provider_nodes.get(provider, 0) + 1
    # A separate CPU session is used only as an output-consistency reference;
    # its timing is excluded from this provider's performance measurements.
    reference = ort.InferenceSession(str(args.model), providers=["CPUExecutionProvider"])
    expected = reference.run(None, {"input": value})[0]
    max_error = float(np.max(np.abs(output - expected)))
    max_reference = float(np.max(np.abs(expected)))
    relative_error = max_error / max_reference if max_reference else max_error
    requested_provider = {"cpu": "CPUExecutionProvider", "dml": "DmlExecutionProvider",
                          "qnn": "QNNExecutionProvider"}[args.provider]
    accelerated_without_cpu_nodes = (
        args.provider != "cpu"
        and provider_nodes.get(requested_provider, 0) > 0
         and provider_nodes.get("CPUExecutionProvider", 0) == 0)
    result = {
        "provider_requested": args.provider,
        "session_providers": session.get_providers(),
        "provider_options": session.get_provider_options(),
        "profile_provider_node_counts": provider_nodes,
        "runtime_version": ort.__version__,
        "python_architecture": os.environ.get("PROCESSOR_ARCHITECTURE", platform.machine()),
        "model_path": str(args.model.resolve()),
        "iterations": args.iterations,
        "load_seconds": load_seconds,
        "mean_latency_ms": sum(timings) / len(timings),
        "p50_latency_ms": percentile(timings, 0.50),
        "p95_latency_ms": percentile(timings, 0.95),
        "max_absolute_error_vs_cpu": max_error,
        "max_relative_error_vs_cpu": relative_error,
        "output_valid": bool(np.isfinite(output).all() and max_error < 0.1
                             and relative_error < 0.05),
        "accelerated_without_cpu_nodes": accelerated_without_cpu_nodes,
        "cpu_fallback_disabled": args.provider != "cpu",
        "power_information": "not exposed by this runtime",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    profile_path.unlink(missing_ok=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
