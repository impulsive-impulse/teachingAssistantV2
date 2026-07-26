"""Resume one approved HTTP artifact with strict range and size checks."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
import urllib.request
from pathlib import Path


CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-bytes", type=int, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    offset = args.output.stat().st_size if args.output.is_file() else 0
    if offset > args.expected_bytes:
        raise ValueError("partial file exceeds approved artifact size")
    if offset == args.expected_bytes:
        actual = sha256_file(args.output)
        if actual != args.expected_sha256:
            raise ValueError("complete-sized file has the wrong SHA-256")
        print(f"already complete sha256={actual}", flush=True)
        return 0

    request = urllib.request.Request(
        args.url,
        headers={
            "Range": f"bytes={offset}-",
            "User-Agent": "TeachingAssistantV2-controlled-model-eval/1",
        },
    )
    print(
        f"requesting range start={offset} expected_total={args.expected_bytes}",
        flush=True,
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 206:
            raise RuntimeError(
                f"server did not honor resume range: HTTP {response.status}"
            )
        match = CONTENT_RANGE.match(response.headers.get("Content-Range", ""))
        if not match:
            raise RuntimeError("missing or malformed Content-Range")
        start, end, total = map(int, match.groups())
        if start != offset or total != args.expected_bytes:
            raise RuntimeError(
                f"range mismatch: start={start}, total={total}, offset={offset}"
            )
        if end != args.expected_bytes - 1:
            raise RuntimeError("server range does not end at approved file boundary")

        downloaded = offset
        last_report = time.monotonic()
        with args.output.open("ab", buffering=0) as handle:
            while True:
                block = response.read(8 * 1024 * 1024)
                if not block:
                    break
                handle.write(block)
                downloaded += len(block)
                if downloaded > args.expected_bytes:
                    raise RuntimeError("download crossed approved file boundary")
                if time.monotonic() - last_report >= 30:
                    print(
                        f"progress bytes={downloaded} "
                        f"percent={100 * downloaded / args.expected_bytes:.1f}",
                        flush=True,
                    )
                    last_report = time.monotonic()

    if args.output.stat().st_size != args.expected_bytes:
        raise RuntimeError(
            f"incomplete transfer: {args.output.stat().st_size} bytes"
        )
    actual = sha256_file(args.output)
    if actual != args.expected_sha256:
        raise RuntimeError(f"SHA-256 mismatch: {actual}")
    print(f"complete bytes={args.expected_bytes} sha256={actual}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
