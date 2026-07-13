"""Run hierarchical retrieval directly from a source checkout."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.hierarchical_retrieval import main


if __name__ == "__main__":
    main()
