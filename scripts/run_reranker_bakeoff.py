"""Repository entry point for the pinned local Phase D reranker bake-off."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.reranker_bakeoff import main


if __name__ == "__main__":
    main()
