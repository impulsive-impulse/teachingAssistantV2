"""Source-checkout entry point for Candidate Complementarity Audit v1."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Make the package importable without requiring an editable installation.
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.candidate_complementarity import main


if __name__ == "__main__":
    main()
