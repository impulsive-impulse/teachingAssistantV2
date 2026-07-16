"""Source-checkout entry point for Phase A candidate-compression experiments."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.candidate_compression import main


if __name__ == "__main__":
    main()
