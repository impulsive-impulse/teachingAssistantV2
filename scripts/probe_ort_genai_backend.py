"""Run the same Gemma-3 ONNX prompt on CPU or DirectML via ORT GenAI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import time
from pathlib import Path

import onnxruntime_genai as og
import psutil


def sha256_tree(path: Path) -> str:
    """Hash model files in stable relative-path order without loading them at once."""
    digest = hashlib.sha256()
    for item in sorted(file for file in path.rglob("*") if file.is_file() and ".cache" not in file.parts):
        digest.update(str(item.relative_to(path)).replace("\\", "/").encode())
        with item.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def main() -> None:
    """Load one execution provider, generate greedily, and persist timing/output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("cpu", "dml"), required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--prompt", default="Why does a pencil look bent when partly submerged in water?")
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load_started = time.perf_counter()
    config = og.Config(str(args.model))
    config.clear_providers()
    if args.provider == "dml":
        config.append_provider("dml")
    model = og.Model(config)
    load_seconds = time.perf_counter() - load_started
    tokenizer = og.Tokenizer(model)
    stream = tokenizer.create_stream()
    processor = model.create_multimodal_processor()
    messages = json.dumps([{"role": "user", "content": args.prompt}])
    template = (args.model / "chat_template.jinja").read_text(encoding="utf-8")
    prompt = tokenizer.apply_chat_template(
        messages=messages, add_generation_prompt=True, template_str=template
    )
    inputs = processor(prompt, images=None, audios=None)
    params = og.GeneratorParams(model)
    params.set_search_options(max_length=args.max_length, do_sample=False, batch_size=1)
    generator = og.Generator(model, params)
    generator.set_inputs(inputs)
    input_tokens = generator.token_count()
    started = time.perf_counter()
    first_token_seconds = None
    pieces = []
    generated_tokens = 0
    while not generator.is_done():
        generator.generate_next_token()
        if first_token_seconds is None:
            first_token_seconds = time.perf_counter() - started
        pieces.append(stream.decode(generator.get_next_tokens()[0]))
        generated_tokens += 1
    latency = time.perf_counter() - started
    memory = psutil.Process().memory_info()
    output_text = "".join(pieces).strip()
    # The controlled fixture has one unambiguous expected concept. This catches
    # backend-corrupted token streams such as repeated <unused...> vocabulary.
    output_valid = ("refraction" in output_text.lower()
                    and "<unused" not in output_text.lower())
    result = {
        "provider": args.provider,
        "runtime": "onnxruntime-genai-directml",
        "runtime_version": og.__version__,
        "architecture": os.environ.get("PROCESSOR_ARCHITECTURE", platform.machine()),
        "model_path": str(args.model.resolve()),
        "model_tree_sha256": sha256_tree(args.model),
        "prompt": args.prompt,
        "load_seconds": load_seconds,
        "time_to_first_token_seconds": first_token_seconds,
        "latency_seconds": latency,
        "prompt_tokens": input_tokens,
        "generated_tokens": generated_tokens,
        "tokens_per_second": generated_tokens / latency if latency else None,
        "peak_rss_bytes": getattr(memory, "peak_wset", memory.rss),
        "output": output_text,
        "output_valid": output_valid,
        "power_information": "not exposed by ORT GenAI",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
