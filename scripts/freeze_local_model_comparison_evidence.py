"""Freeze prompt-safe development evidence for Local Model Comparison v1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "reports/local_model_comparison_v1/experiment_config.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def canonical_context_hash(evidence: list[dict]) -> str:
    body = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def freeze(config_path: Path) -> Path:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    frozen = config["frozen_inputs"]
    source = ROOT / frozen["development_evidence_source"]["path"]
    expected_source_hash = frozen["development_evidence_source"]["sha256"]
    if sha256_file(source) != expected_source_hash:
        raise ValueError("development evidence source checksum mismatch")

    historical = json.loads(
        (ROOT / frozen["historical_generation_experiment"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    expected_ids = historical["split"]["development_question_ids"]
    source_rows = read_jsonl(source)
    by_id = {row["question_id"]: row for row in source_rows}
    if list(by_id) != expected_ids:
        raise ValueError("source results do not match the frozen development order")

    snapshot_rows = []
    for question_id in expected_ids:
        row = by_id[question_id]
        evidence = row["supplied_evidence"]
        if len(evidence) != 5:
            raise ValueError(f"{question_id}: expected exactly five evidence items")
        context_hash = canonical_context_hash(evidence)
        if context_hash != row["context_sha256"]:
            raise ValueError(f"{question_id}: historical context checksum mismatch")
        snapshot_rows.append(
            {
                "schema_version": 1,
                "question_id": question_id,
                "context_strategy": "retrieved_top5_page_order_compact",
                "context_sha256": context_hash,
                "evidence": evidence,
            }
        )

    destination = ROOT / frozen["development_evidence_snapshot"]["path"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in snapshot_rows
    )
    destination.write_text(content, encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "path": str(destination),
                "questions": len(snapshot_rows),
                "sha256": sha256_file(destination),
            },
            indent=2,
        )
    )
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    freeze(args.config.resolve())


if __name__ == "__main__":
    main()
