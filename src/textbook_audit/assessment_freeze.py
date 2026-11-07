"""Freeze development choices and verify the exact final execution code/config."""

import hashlib
from pathlib import Path
from typing import Any

from .assessment_assets import child_path
from .assessment_generation import GENERATION_VERSION
from .assessment_inference import load_pipeline
from .assessment_protocol import fingerprint, read_json
from .experiment_tracking import write_json


def code_identity(root: Path) -> dict[str, str]:
    paths = list((root / "src" / "textbook_audit").glob("assessment_*.py"))
    paths += [root / "src" / "textbook_audit" / (name + ".py") for name in (
        "collection_index", "source_provenance", "chunk_retrieval", "context_assembly",
        "retrieval", "embedding_bakeoff", "generation_phase_a",
    )]
    paths += [root / "src" / "textbook_chat" / "generation" / "online.py"]
    return {
        str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(
            path.read_text("utf-8").encode("utf-8")
        ).hexdigest()
        for path in sorted(paths)
    }


def verify_freeze(root: Path) -> dict[str, Any]:
    manifest = read_json(root / "config" / "assessment_freeze_v1.json")
    core = {key: value for key, value in manifest.items() if key != "checksum"}
    if manifest["checksum"] != fingerprint(core) or manifest["version"] != "assessment-freeze-v1":
        raise ValueError("final pipeline freeze manifest changed")
    pipeline = load_pipeline(root)
    if (
        pipeline["status"] != "frozen" or fingerprint(pipeline) != manifest["pipeline_sha256"]
        or pipeline["generation_contract"] != GENERATION_VERSION
    ):
        raise ValueError("final pipeline is not the development-selected frozen configuration")
    for name, expected in manifest["code_sha256_lf"].items():
        if hashlib.sha256(child_path(root, name).read_text("utf-8").encode("utf-8")).hexdigest() != expected:
            raise ValueError("frozen final execution code changed: " + name)
    return manifest


def freeze(root: Path) -> dict[str, Any]:
    destination = root / "config" / "assessment_freeze_v1.json"
    if destination.exists():
        raise FileExistsError("final configuration is already frozen; do not retune against final outcomes")
    base = root / "reports" / "assessment_results_v1"
    confirmation = read_json(base / "development_confirmation" / "metrics.json")
    initial = read_json(base / "development_initial" / "metrics.json")
    if confirmation["phase"] != "development" or len(confirmation["question_ids"]) != 15:
        raise ValueError("a complete 15-question development report is required")
    labels = read_json(base / "development_confirmation" / "references.json")
    review_ids = {}
    for split, counts in (("development", {"bridge": 4, "comparison": 1}), ("held_out", {"bridge": 8, "comparison": 2})):
        review_ids[split] = []
        for kind, count in counts.items():
            candidates = [row["question_id"] for row in labels["references"] if row["split"] == split and row["question_type"] == kind]
            candidates.sort(key=lambda q: (hashlib.sha256(("sarvam-context-v1:claim-review:1729:" + q).encode()).hexdigest(), q))
            review_ids[split].extend(candidates[:count])
    pipeline = {
        **load_pipeline(root), "status": "frozen", "generation_contract": GENERATION_VERSION,
        "same_run_reuse": "completed-provider-response-including-invalid-claims",
    }
    core = {
        "version": "assessment-freeze-v1", "pipeline_sha256": fingerprint(pipeline),
        "protocol_sha256": pipeline["protocol_sha256"], "code_sha256_lf": code_identity(root),
        "development_initial_run": initial["run_id"], "development_confirmation_run": confirmation["run_id"],
        "initial_metrics": initial["metrics"], "confirmation_metrics": confirmation["metrics"],
        "review_question_ids": review_ids,
        "selection_rationale": (
            "Select six documents, three units and 0.2 title links from the predeclared retrieval-only grid. "
            "Keep the 0.25 weak-dense threshold. Revision 2 emphasizes literal contiguous quotes without "
            "loosening validation; confirmation remains on exactly the 15 development rows."
        ),
        "ablation_correction": (
            "Early development reused only valid outputs, so identical hybrid/ablation requests with invalid "
            "claims were independently sampled and sometimes differed despite temperature zero. Final execution "
            "reuses every completed provider response, including invalid claims; both development runs remain retained."
        ),
        "held_out_effectiveness_seen": False, "paid_judge_calls": 0,
    }
    write_json(root / "config" / "assessment_pipeline_v1.json", pipeline)
    write_json(destination, {**core, "checksum": fingerprint(core)})
    return verify_freeze(root)
