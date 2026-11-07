"""Explicit fresh evaluation or zero-call replay of saved raw assessment outputs."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.assessment_runner import main


if __name__ == "__main__":
    main()
