"""Command-line interface for the extraction audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import ROOT, run


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract the configured textbooks and generate the suitability audit."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Project root containing books/ (default: repository root).",
    )
    args = parser.parse_args()
    run(args.root.resolve())


if __name__ == "__main__":
    main()
