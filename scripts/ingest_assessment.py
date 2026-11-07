"""Build or verify the assessment's shared source corpora."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.assessment_ingestion import main


if __name__ == "__main__":
    main()
