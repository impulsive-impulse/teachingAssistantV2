"""Build manifest-derived tables for a versioned local-model comparison."""

import argparse
from pathlib import Path

from textbook_audit.local_model_report import write_tables


ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experiment-dir",
        type=Path,
        default=ROOT / "reports/local_model_comparison_v1",
    )
    args = parser.parse_args()
    print(write_tables(args.experiment_dir.resolve()))
