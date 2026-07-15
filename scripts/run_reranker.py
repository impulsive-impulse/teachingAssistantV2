"""Source-checkout entry point for Local Cross-Encoder Reranking v1."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Allow a clean checkout to run the script before an editable installation.
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.reranker import main


if __name__ == "__main__":
    main()
