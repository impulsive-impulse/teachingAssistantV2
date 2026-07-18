"""Build reports and the blinded review packet from completed generation runs."""

import json

from textbook_audit.generation_experiment_report import build_report


if __name__ == "__main__":
    print(json.dumps(build_report(), indent=2))
