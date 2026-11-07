"""Select a source-aware context allocator on development data only."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.assessment_selector import main


if __name__ == "__main__":
    main()
