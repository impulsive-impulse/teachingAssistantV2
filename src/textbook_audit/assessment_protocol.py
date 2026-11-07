"""Gold-isolated, deterministic selection for the assessment's open benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from .experiment_tracking import sha256_file, write_json


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROTOCOL = ROOT / "config" / "assessment_protocol_v1.json"
SPLITS = ("development", "held_out")
QUESTION_TYPES = ("bridge", "comparison")
SOURCE_FIELDS = {"id", "question", "answer", "type", "level", "context", "supporting_facts"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    """Hash semantic JSON, independently of checkout line endings."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    protocol = read_json(path)
    if not isinstance(protocol, dict) or protocol.get("schema_version") != 1:
        raise ValueError("assessment protocol must use schema_version 1")
    selection = protocol["selection"]
    if set(selection["splits"]) != set(SPLITS):
        raise ValueError("protocol must define development and held_out splits")
    for split in SPLITS:
        quotas = selection["splits"][split]
        if set(quotas) != set(QUESTION_TYPES) or any(
            isinstance(count, bool) or not isinstance(count, int) or count < 1
            for count in quotas.values()
        ):
            raise ValueError(f"{split}: positive bridge/comparison quotas are required")
    if selection["support_document_count"] != 2 or selection["context_document_count"] != 10:
        raise ValueError("distractor protocol requires two supporting documents and ten contexts")
    if selection["disjoint_context_titles"] is not True:
        raise ValueError("protocol requires disjoint context titles")
    arms = protocol["comparison_arms"]
    arm_ids = [arm["id"] for arm in arms]
    if len(arms) != 4 or len(set(arm_ids)) != 4:
        raise ValueError("protocol requires four unique comparison arms")
    budget = protocol["paid_call_budget"]
    expected = {
        "development": sum(selection["splits"]["development"].values()) * len(arms),
        "final_evaluation": sum(selection["splits"]["held_out"].values()) * len(arms),
        "fresh_final_rerun": sum(selection["splits"]["held_out"].values()) * len(arms),
    }
    if any(budget[key] != count for key, count in expected.items()):
        raise ValueError("API call reservations do not match the selected questions and arms")
    contingency = budget["contingency"]
    if isinstance(contingency, bool) or not isinstance(contingency, int) or contingency < 0:
        raise ValueError("contingency must be a non-negative call count")
    if sum(expected.values()) + contingency != budget["maximum_attempts"]:
        raise ValueError("API call allocations must sum to the maximum")
    if budget["maximum_attempts"] != 500 or budget["counts_failed_and_retried_requests"] is not True:
        raise ValueError("the approved cap is 500 attempts including failures and retries")
    return protocol


def normalize_title(title: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", title).casefold().split())


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def validate_source_row(row: Any) -> None:
    """Validate the mirror's parallel arrays before any zip or selection."""
    if not isinstance(row, dict) or set(row) != SOURCE_FIELDS:
        raise ValueError("HotpotQA row must contain the seven source fields")
    qid = _nonempty_string(row["id"], "question id")
    for field in ("question", "answer"):
        _nonempty_string(row[field], f"{qid}: {field}")
    if row["type"] not in QUESTION_TYPES or row["level"] != "hard":
        raise ValueError(f"{qid}: unexpected development-set type or difficulty")
    for field, keys in (("context", {"title", "sentences"}),
                        ("supporting_facts", {"title", "sent_id"})):
        value = row[field]
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError(f"{qid}: invalid {field} object")
        if any(not isinstance(value[key], list) for key in keys):
            raise ValueError(f"{qid}: {field} must contain parallel arrays")
        if len({len(value[key]) for key in keys}) != 1:
            raise ValueError(f"{qid}: {field} arrays do not align")
        for title in value["title"]:
            _nonempty_string(title, f"{qid}: {field} title")
    for sentences in row["context"]["sentences"]:
        if not isinstance(sentences, list) or any(not isinstance(text, str) for text in sentences):
            raise ValueError(f"{qid}: context sentences must be string arrays")
    if any(isinstance(index, bool) or not isinstance(index, int)
           for index in row["supporting_facts"]["sent_id"]):
        raise ValueError(f"{qid}: supporting sentence indices must be integers")


def load_source(path: Path, benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"benchmark source is missing: {path}")
    if path.stat().st_size != benchmark["size_bytes"] or sha256_file(path) != benchmark["sha256"]:
        raise ValueError("benchmark source does not match the pinned size and SHA-256")
    try:
        import pyarrow.parquet as parquet
    except ModuleNotFoundError as exc:
        raise RuntimeError('Install the benchmark reader: python -m pip install -e ".[assessment]"') from exc
    rows = parquet.read_table(path).to_pylist()
    if len(rows) != benchmark["expected_rows"]:
        raise ValueError(f"expected {benchmark['expected_rows']} source rows, found {len(rows)}")
    for row in rows:
        validate_source_row(row)
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("benchmark source contains duplicate question IDs")
    return rows


def support_references(row: dict[str, Any]) -> list[tuple[str, int]]:
    return list(zip(
        row["supporting_facts"]["title"], row["supporting_facts"]["sent_id"], strict=True
    ))


def rejection_reason(row: dict[str, Any], selection: dict[str, Any]) -> str | None:
    titles = row["context"]["title"]
    if len(titles) != selection["context_document_count"]:
        return "context_count_not_ten"
    if len({normalize_title(title) for title in titles}) != len(titles):
        return "duplicate_context_document"
    references = support_references(row)
    if len({normalize_title(title) for title, _ in references}) != selection["support_document_count"]:
        return "support_count_not_two_documents"
    by_title = dict(zip(titles, row["context"]["sentences"], strict=True))
    for title, index in references:
        if title not in by_title or not 0 <= index < len(by_title[title]):
            return "support_location_unresolvable"
        if not by_title[title][index].strip():
            return "support_sentence_empty"
    return None


def selection_key(qid: str, selection: dict[str, Any], purpose: str = "") -> tuple[str, str]:
    prefix = selection["hash_namespace"]
    if purpose:
        prefix += f":{purpose}"
    key = f"{prefix}:{selection['seed']}:{qid}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest(), qid


def select_rows(
    rows: list[dict[str, Any]], selection: dict[str, Any], excluded: dict[str, Any]
) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, Any]]:
    ids = {row["id"] for row in rows}
    if len(ids) != len(rows):
        raise ValueError("source question IDs must be unique")
    if set(excluded) - ids:
        raise ValueError(f"review contains unknown exclusions: {sorted(set(excluded) - ids)}")
    eligible: dict[str, list[dict[str, Any]]] = {kind: [] for kind in QUESTION_TYPES}
    rejections: Counter[str] = Counter()
    rejected_questions = []
    for row in rows:
        validate_source_row(row)
        reason = rejection_reason(row, selection)
        if row["id"] in excluded:
            reason = f"source_review:{excluded[row['id']]['reason']}"
        if reason:
            rejections[reason] += 1
            rejected_questions.append({"question_id": row["id"], "reason": reason})
        else:
            eligible[row["type"]].append(row)
    for candidates in eligible.values():
        candidates.sort(key=lambda row: selection_key(row["id"], selection))
    selected: list[tuple[str, dict[str, Any]]] = []
    used_titles: set[str] = set()
    used_questions: set[str] = set()
    skipped: Counter[str] = Counter()
    for split in SPLITS:
        for kind in QUESTION_TYPES:
            count = 0
            target = selection["splits"][split][kind]
            for row in eligible[kind]:
                titles = {normalize_title(title) for title in row["context"]["title"]}
                question = normalize_title(row["question"])
                if titles & used_titles:
                    skipped["overlapping_context_titles"] += 1
                    continue
                if question in used_questions:
                    skipped["duplicate_normalized_question"] += 1
                    continue
                selected.append((split, row))
                used_titles.update(titles)
                used_questions.add(question)
                count += 1
                if count == target:
                    break
            if count != target:
                raise ValueError(f"{split}/{kind}: requested {target} rows, found {count}")
    audit = {
        "eligible_counts": {kind: len(values) for kind, values in eligible.items()},
        "rejection_counts": dict(sorted(rejections.items())),
        "rejected_questions": sorted(rejected_questions, key=lambda item: item["question_id"]),
        "selection_skip_counts": dict(sorted(skipped.items())),
        "distinct_context_titles": len(used_titles),
    }
    return selected, audit


def runtime_projection(row: dict[str, Any], selection: dict[str, Any]) -> dict[str, Any]:
    """Only question, identity, and label-independent contexts cross the boundary."""
    contexts = list(zip(row["context"]["title"], row["context"]["sentences"], strict=True))
    contexts.sort(key=lambda context: selection_key(normalize_title(context[0]), selection, "context"))
    return {
        "id": row["id"],
        "question": row["question"],
        "context": [[title, list(sentences)] for title, sentences in contexts],
    }


def validate_review(
    selected: list[tuple[str, dict[str, Any]]], review: dict[str, Any], protocol: dict[str, Any]
) -> None:
    if review.get("protocol_id") != protocol["protocol_id"] or review.get("source_sha256") != protocol["benchmark"]["sha256"]:
        raise ValueError("necessity review does not match the protocol and pinned source")
    accepted = review["accepted"]
    for _split, row in selected:
        qid = row["id"]
        case = accepted.get(qid)
        if not isinstance(case, dict):
            raise ValueError(f"{qid}: selected question has no completed necessity review")
        _nonempty_string(case.get("necessity"), f"{qid}: necessity rationale")
        requirements = case.get("document_requirements")
        if not isinstance(requirements, dict) or set(requirements) != set(row["supporting_facts"]["title"]):
            raise ValueError(f"{qid}: review must state a requirement for both supporting documents")
        for title, need in requirements.items():
            _nonempty_string(need, f"{qid}: requirement for {title}")
    if set(accepted) & set(review["excluded"]):
        raise ValueError("a question cannot be both accepted and excluded")
    for qid, case in review["excluded"].items():
        _nonempty_string(case.get("reason"), f"{qid}: exclusion reason")
        _nonempty_string(case.get("evidence"), f"{qid}: exclusion evidence")


def build_manifest(
    rows: list[dict[str, Any]], protocol: dict[str, Any], review: dict[str, Any]
) -> dict[str, Any]:
    selected, audit = select_rows(rows, protocol["selection"], review["excluded"])
    validate_review(selected, review, protocol)
    entries = []
    for split, row in selected:
        entries.append({
            "question_id": row["id"],
            "split": split,
            "question_type": row["type"],
            "level": row["level"],
            "context_document_count": len(row["context"]["title"]),
            "supporting_document_titles": sorted(set(row["supporting_facts"]["title"])),
            "supporting_fact_count": len(set(support_references(row))),
            "source_row_sha256": fingerprint(row),
            "runtime_input_sha256": fingerprint(runtime_projection(row, protocol["selection"])),
        })
    manual_ids = {}
    for split in SPLITS:
        review_ids = []
        for kind in QUESTION_TYPES:
            candidates = [entry for entry in entries if entry["split"] == split and entry["question_type"] == kind]
            candidates.sort(key=lambda entry: selection_key(
                entry["question_id"], protocol["selection"], "claim-review"
            ))
            count = protocol["analysis"]["manual_claim_review_counts"][split][kind]
            if not 0 <= count <= len(candidates):
                raise ValueError(f"{split}/{kind}: invalid manual claim-review count")
            review_ids.extend(entry["question_id"] for entry in candidates[:count])
        manual_ids[split] = review_ids
    return {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "dataset_license": protocol["benchmark"]["dataset_license"],
        "protocol_semantic_sha256": fingerprint(protocol),
        "source_sha256": protocol["benchmark"]["sha256"],
        "necessity_review_semantic_sha256": fingerprint(review),
        "selection_seed": protocol["selection"]["seed"],
        "selected_count": len(entries),
        "split_counts": {
            split: dict(Counter(entry["question_type"] for entry in entries if entry["split"] == split))
            for split in SPLITS
        },
        "source_audit": audit,
        "manual_claim_review_question_ids": manual_ids,
        "questions": entries,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--source", type=Path, required=True)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--check", action="store_true", help="Recompute and verify; do not write.")
    actions.add_argument("--preview", action="store_true", help="List candidate IDs and pending reviews; do not freeze.")
    args = parser.parse_args(argv)
    protocol = load_protocol(args.protocol)
    root = args.protocol.resolve().parents[1]
    review = read_json(root / protocol["selection"]["necessity_review"])
    rows = load_source(args.source, protocol["benchmark"])
    if args.preview:
        selected, audit = select_rows(rows, protocol["selection"], review["excluded"])
        print(json.dumps({
            "source_audit": audit,
            "candidates": [
                {"split": split, "question_id": row["id"], "question_type": row["type"],
                 "reviewed": row["id"] in review["accepted"]}
                for split, row in selected
            ],
        }, indent=2))
        return
    manifest = build_manifest(rows, protocol, review)
    output = root / protocol["selection"]["manifest"]
    if args.check:
        if not output.is_file() or read_json(output) != manifest:
            raise ValueError("selection manifest is missing or differs from the reproducible selection")
    elif output.is_file():
        if read_json(output) != manifest:
            raise ValueError("refusing to overwrite a frozen selection; create a new protocol version")
    else:
        write_json(output, manifest)
    print(json.dumps({
        "protocol_id": manifest["protocol_id"],
        "selected_count": manifest["selected_count"],
        "split_counts": manifest["split_counts"],
        "distinct_context_titles": manifest["source_audit"]["distinct_context_titles"],
        "reviewed_questions": len(manifest["questions"]),
        "manifest": str(output),
        "check_only": args.check,
        "paid_api_calls": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
