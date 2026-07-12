"""Source-checkout entry point for the page-level retrieval baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# A source checkout has not necessarily been installed, so expose ``src`` to
# Python before importing the real CLI. All retrieval logic remains in the
# package module and is shared with the installed ``page-retrieval`` command.
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.retrieval import main


if __name__ == "__main__":
    main()
