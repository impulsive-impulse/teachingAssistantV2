"""Prepare the preselected source-review packet with opaque arm identifiers."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_audit.assessment_protocol import fingerprint, read_json
from textbook_audit.assessment_runner import ARMS, _raw_path, read_raw
from textbook_audit.experiment_tracking import write_json


def prepare(directory: Path, split: str, output: Path, key_path: Path) -> None:
    freeze = read_json(ROOT / "config" / "assessment_freeze_v1.json")
    ids = freeze["review_question_ids"][split]
    references = {r["question_id"]: r for r in read_json(directory / "references.json")["references"]}
    cards, key = [], {}
    for question_id in ids:
        for arm in ARMS:
            row = read_raw(_raw_path(directory, question_id, arm))
            card_id = hashlib.sha256(("blind-v1:" + question_id + ":" + arm).encode()).hexdigest()[:12]
            key[card_id] = {"question_id": question_id, "arm": arm}
            catalog = {d["document_id"]: d for d in row["snapshot"]["source_documents"]}
            titles = {d["title"]: d for d in catalog.values()}
            units = {s["evidence_id"]: s for s in row["context"]["segments"]}
            try:
                payload = json.loads(row["generation"]["raw_text"])
            except (json.JSONDecodeError, TypeError):
                payload = {"status": "invalid_json", "claims": [], "short_answer": ""}
            claims = []
            for claim in payload.get("claims", []):
                citations = []
                for citation in claim.get("citations", []):
                    segment = units.get(citation.get("evidence_id"))
                    document = catalog[segment["document_id"]] if segment else None
                    unit = next((u for u in document["units"] if u["unit_id"] == citation.get("unit_id")), None) if document else None
                    retained = next((u for u in segment["units"] if u["unit_id"] == citation.get("unit_id")), None) if segment else None
                    citations.append({
                        **citation, "title": document["title"] if document else None,
                        "original_unit": unit["text"] if unit else None,
                        "retained_unit": retained["text"] if retained else None,
                    })
                claims.append({"text": claim.get("text"), "citations": citations})
            reference = references[question_id]
            gold_units = [{
                "title": title, "sentence_index": number,
                "text": titles[title]["units"][number]["text"],
            } for title, number in reference["supporting_facts"]]
            cards.append({
                "card_id": card_id, "question_id": question_id, "question": row["question"],
                "short_answer": payload.get("short_answer"), "status": payload.get("status"),
                "claims": claims, "reference_answer": reference["answer"], "reference_support": gold_units,
                "validator_errors": row["generation"]["validation"].get("errors", []),
            })
    cards.sort(key=lambda card: card["card_id"])
    core = {
        "version": "assessment-source-review-packet-v1", "split": split,
        "question_ids": ids, "cards": cards,
        "rubric": {
            "semantic_support": "Each factual claim follows from its quoted sources and necessary entity links; validity alone is insufficient.",
            "completeness": "Both required source roles/intermediate facts are present; unsupported short answers, comparisons or arithmetic fail.",
            "judgment": "supported / partial / unsupported / abstained / invalid; give a source-specific reason.",
            "reviewer": "Assistant source inspection, not human signoff or a formal entailment proof.",
        },
    }
    write_json(output, {**core, "checksum": fingerprint(core)})
    write_json(key_path, key)
    readable = output.with_suffix(".jsonl")
    readable.write_text("".join(json.dumps(card, ensure_ascii=True) + "\n" for card in cards), encoding="utf-8")
    print(json.dumps({"split": split, "cards": len(cards), "question_ids": ids, "readable": str(readable)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "held_out"), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blinding-key", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.input, args.split, args.output, args.blinding_key)
