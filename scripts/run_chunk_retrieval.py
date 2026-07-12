"""Run chunk retrieval directly from a source checkout without installation."""

from pathlib import Path
import sys

# Make the src-layout package importable when this file is invoked directly.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.chunk_retrieval import main


if __name__ == "__main__":
    main()
