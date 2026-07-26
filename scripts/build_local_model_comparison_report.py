"""Build manifest-derived Local Model Comparison v1 tables."""

from pathlib import Path

from textbook_audit.local_model_report import write_tables


ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    print(write_tables(ROOT / "reports/local_model_comparison_v1"))
