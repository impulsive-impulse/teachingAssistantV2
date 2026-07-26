"""Download disjoint verified ranges, assemble them, and verify one artifact."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import os
import re
import shutil
import threading
import time
import urllib.request
from pathlib import Path


CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
PRINT_LOCK = threading.Lock()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ranges(start: int, total: int, count: int) -> list[tuple[int, int]]:
    remaining = total - start
    width = (remaining + count - 1) // count
    return [
        (part_start, min(total - 1, part_start + width - 1))
        for part_start in range(start, total, width)
    ]


def download_range(
    *,
    url: str,
    destination: Path,
    range_start: int,
    range_end: int,
    total: int,
) -> Path:
    expected_size = range_end - range_start + 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 6):
        present = destination.stat().st_size if destination.is_file() else 0
        if present > expected_size:
            raise RuntimeError(f"{destination.name} exceeds its range")
        if present == expected_size:
            return destination
        request_start = range_start + present
        request = urllib.request.Request(
            url,
            headers={
                "Range": f"bytes={request_start}-{range_end}",
                "User-Agent": "TeachingAssistantV2-controlled-model-eval/1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.status != 206:
                    raise RuntimeError(f"range HTTP status {response.status}")
                match = CONTENT_RANGE.match(
                    response.headers.get("Content-Range", "")
                )
                if not match:
                    raise RuntimeError("missing or malformed Content-Range")
                actual_start, actual_end, actual_total = map(int, match.groups())
                if (
                    actual_start != request_start
                    or actual_end != range_end
                    or actual_total != total
                ):
                    raise RuntimeError(
                        "server returned a different byte interval: "
                        f"{actual_start}-{actual_end}/{actual_total}"
                    )
                last_report = time.monotonic()
                with destination.open("ab", buffering=0) as handle:
                    while True:
                        block = response.read(4 * 1024 * 1024)
                        if not block:
                            break
                        handle.write(block)
                        present += len(block)
                        if present > expected_size:
                            raise RuntimeError("range crossed its approved boundary")
                        if time.monotonic() - last_report >= 30:
                            with PRINT_LOCK:
                                print(
                                    f"part={destination.name} "
                                    f"percent={100 * present / expected_size:.1f}",
                                    flush=True,
                                )
                            last_report = time.monotonic()
            if destination.stat().st_size == expected_size:
                return destination
            raise RuntimeError("range response ended before its boundary")
        except Exception:
            if attempt == 5:
                raise
            time.sleep(5 * attempt)
    raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--parts-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-bytes", type=int, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    if args.output.is_file():
        if (
            args.output.stat().st_size == args.expected_bytes
            and sha256_file(args.output) == args.expected_sha256
        ):
            print("already complete and verified", flush=True)
            return 0
        raise RuntimeError("existing final output does not match approved artifact")

    prefix_size = args.prefix.stat().st_size
    if not 0 <= prefix_size < args.expected_bytes:
        raise ValueError("prefix size must be within the approved artifact")
    intervals = ranges(prefix_size, args.expected_bytes, args.workers)
    jobs = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(intervals)
    ) as executor:
        for start, end in intervals:
            destination = args.parts_dir / f"bytes_{start}_{end}.part"
            jobs.append(
                executor.submit(
                    download_range,
                    url=args.url,
                    destination=destination,
                    range_start=start,
                    range_end=end,
                    total=args.expected_bytes,
                )
            )
        parts = [job.result() for job in jobs]

    assembling = args.output.with_name(args.output.name + ".assembling")
    with assembling.open("wb") as target, args.prefix.open("rb") as source:
        shutil.copyfileobj(source, target, length=8 * 1024 * 1024)
        for part in parts:
            with part.open("rb") as source:
                shutil.copyfileobj(source, target, length=8 * 1024 * 1024)
    if assembling.stat().st_size != args.expected_bytes:
        raise RuntimeError("assembled artifact has the wrong byte count")
    actual = sha256_file(assembling)
    if actual != args.expected_sha256:
        raise RuntimeError(f"assembled artifact SHA-256 mismatch: {actual}")
    os.replace(assembling, args.output)
    print(
        f"complete bytes={args.expected_bytes} sha256={actual}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
