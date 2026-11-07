"""Small, offline checks of the open-benchmark selection and leakage boundary."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import textbook_audit.assessment_protocol as protocol_module

from textbook_audit.assessment_protocol import (
    DEFAULT_PROTOCOL,
    build_manifest,
    fingerprint,
    load_protocol,
    load_source,
    normalize_title,
    read_json,
    rejection_reason,
    runtime_projection,
    select_rows,
    sha256_file,
    validate_review,
    validate_source_row,
)


ROOT = Path(__file__).resolve().parents[1]


def example(qid: str, kind: str = "bridge") -> dict:
    titles = [f"{qid} article {index}" for index in range(10)]
    return {
        "id": qid,
        "question": f"What answer requires the two articles for {qid}?",
        "answer": "the answer",
        "type": kind,
        "level": "hard",
        "context": {
            "title": titles,
            "sentences": [[f"{title} first sentence.", f"{title} second sentence."] for title in titles],
        },
        "supporting_facts": {"title": titles[:2], "sent_id": [0, 1]},
    }


@pytest.fixture
def small_protocol() -> dict:
    protocol = copy.deepcopy(load_protocol())
    protocol["selection"]["splits"] = {
        "development": {"bridge": 1, "comparison": 1},
        "held_out": {"bridge": 1, "comparison": 1},
    }
    protocol["analysis"]["manual_claim_review_counts"] = {
        "development": {"bridge": 1, "comparison": 1},
        "held_out": {"bridge": 1, "comparison": 1},
    }
    protocol["paid_call_budget"].update({
        "development": 8, "final_evaluation": 8, "fresh_final_rerun": 8, "contingency": 476,
    })
    return protocol


@pytest.fixture
def examples() -> list[dict]:
    return [example(f"{kind}-{index}", kind) for kind in ("bridge", "comparison") for index in range(3)]


def reviewed(rows: list[dict], protocol: dict) -> dict:
    return {
        "protocol_id": protocol["protocol_id"],
        "source_sha256": protocol["benchmark"]["sha256"],
        "accepted": {
            row["id"]: {
                "necessity": "Both documents supply different required facts.",
                "document_requirements": {
                    title: "This document supplies a required fact."
                    for title in row["supporting_facts"]["title"]
                },
            }
            for row in rows
        },
        "excluded": {},
    }


def test_checked_in_protocol_reserves_every_paid_call() -> None:
    protocol = load_protocol()
    budget = protocol["paid_call_budget"]
    assert (budget["development"], budget["final_evaluation"], budget["fresh_final_rerun"], budget["contingency"]) == (60, 180, 180, 80)
    assert sum(budget[key] for key in ("development", "final_evaluation", "fresh_final_rerun", "contingency")) == 500


@pytest.mark.parametrize("field", ["development", "final_evaluation", "fresh_final_rerun", "maximum_attempts"])
def test_protocol_rejects_inconsistent_call_reservations(tmp_path: Path, field: str) -> None:
    protocol = copy.deepcopy(load_protocol())
    protocol["paid_call_budget"][field] += 1
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol), encoding="utf-8")
    with pytest.raises(ValueError, match="call|API"):
        load_protocol(path)


@pytest.mark.parametrize("field", ["context", "supporting_facts"])
def test_parallel_source_arrays_cannot_be_silently_truncated(field: str) -> None:
    row = example("misaligned")
    row[field]["title"].pop()
    with pytest.raises(ValueError, match="do not align"):
        validate_source_row(row)


@pytest.mark.parametrize("index", [True, 0.5, "1"])
def test_source_rejects_non_integer_sentence_indices(index: object) -> None:
    row = example("bad-index")
    row["supporting_facts"]["sent_id"][0] = index
    with pytest.raises(ValueError, match="indices must be integers"):
        validate_source_row(row)


def test_two_chunks_from_one_article_are_not_two_documents() -> None:
    row = example("one-document")
    row["supporting_facts"]["title"][1] = row["supporting_facts"]["title"][0]
    validate_source_row(row)
    assert rejection_reason(row, load_protocol()["selection"]) == "support_count_not_two_documents"


@pytest.mark.parametrize("index", [-1, 2, 999])
def test_support_locations_must_resolve(index: int) -> None:
    row = example("out-of-range")
    row["supporting_facts"]["sent_id"][0] = index
    assert rejection_reason(row, load_protocol()["selection"]) == "support_location_unresolvable"


def test_support_location_cannot_be_an_unrelated_document() -> None:
    row = example("missing-document")
    row["supporting_facts"]["title"][0] = "not in context"
    assert rejection_reason(row, load_protocol()["selection"]) == "support_location_unresolvable"


def test_empty_support_sentences_are_explicitly_rejected() -> None:
    row = example("empty-support")
    row["context"]["sentences"][0][0] = "  "
    assert rejection_reason(row, load_protocol()["selection"]) == "support_sentence_empty"


def test_context_titles_are_normalized_before_duplicate_checks() -> None:
    row = example("duplicate")
    row["context"]["title"][:2] = ["Article", " ＡＲＴＩＣＬＥ "]
    assert normalize_title(row["context"]["title"][0]) == normalize_title(row["context"]["title"][1])
    assert rejection_reason(row, load_protocol()["selection"]) == "duplicate_context_document"


def test_non_standard_context_counts_are_not_silently_repaired() -> None:
    row = example("short-context")
    row["context"]["title"].pop()
    row["context"]["sentences"].pop()
    validate_source_row(row)
    assert rejection_reason(row, load_protocol()["selection"]) == "context_count_not_ten"


def test_selection_is_stratified_disjoint_and_independent_of_input_order(examples: list[dict], small_protocol: dict) -> None:
    left, audit = select_rows(examples, small_protocol["selection"], {})
    right, other_audit = select_rows(list(reversed(examples)), small_protocol["selection"], {})
    assert left == right
    assert audit == other_audit
    assert [(split, row["type"]) for split, row in left] == [
        ("development", "bridge"), ("development", "comparison"),
        ("held_out", "bridge"), ("held_out", "comparison"),
    ]
    assert audit["distinct_context_titles"] == 40
    assert len({row["id"] for _, row in left}) == 4


def test_selection_never_reuses_articles_across_questions(examples: list[dict], small_protocol: dict) -> None:
    examples[1]["context"]["title"][9] = examples[0]["context"]["title"][9]
    selected, _ = select_rows(examples, small_protocol["selection"], {})
    titles = [normalize_title(title) for _, row in selected for title in row["context"]["title"]]
    assert len(set(titles)) == len(titles)


def test_duplicate_question_ids_fail_before_selection(examples: list[dict], small_protocol: dict) -> None:
    examples[1]["id"] = examples[0]["id"]
    with pytest.raises(ValueError, match="unique"):
        select_rows(examples, small_protocol["selection"], {})


def test_documented_exclusions_and_shortfalls_are_visible(examples: list[dict], small_protocol: dict) -> None:
    exclusions = {row["id"]: {"reason": "single_source", "evidence": "Source review."} for row in examples if row["type"] == "bridge"}
    with pytest.raises(ValueError, match="requested 1 rows, found 0"):
        select_rows(examples, small_protocol["selection"], exclusions)
    with pytest.raises(ValueError, match="unknown exclusions"):
        select_rows(examples, small_protocol["selection"], {"unknown": {}})


def test_runtime_projection_is_independent_of_labels_and_context_order() -> None:
    protocol = load_protocol()
    row = example("leakage")
    expected = runtime_projection(row, protocol["selection"])
    assert set(expected) == {"id", "question", "context"}
    row["answer"] = "different gold answer"
    row["supporting_facts"] = {"title": ["another title"], "sent_id": [99]}
    row["type"] = "comparison"
    row["level"] = "easy"
    row["context"]["title"].reverse()
    row["context"]["sentences"].reverse()
    assert runtime_projection(row, protocol["selection"]) == expected
    expected["context"][0][1][0] = "changed copy"
    assert all("changed copy" not in sentences for sentences in row["context"]["sentences"])


def test_reviews_require_both_document_roles_before_freezing(examples: list[dict], small_protocol: dict) -> None:
    selected, _ = select_rows(examples, small_protocol["selection"], {})
    review = reviewed(examples, small_protocol)
    qid = selected[0][1]["id"]
    del review["accepted"][qid]
    with pytest.raises(ValueError, match="no completed necessity review"):
        validate_review(selected, review, small_protocol)
    review = reviewed(examples, small_protocol)
    review["accepted"][qid]["document_requirements"].popitem()
    with pytest.raises(ValueError, match="both supporting documents"):
        validate_review(selected, review, small_protocol)


def test_review_is_pinned_to_the_exact_source(examples: list[dict], small_protocol: dict) -> None:
    selected, _ = select_rows(examples, small_protocol["selection"], {})
    review = reviewed(examples, small_protocol)
    review["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="pinned source"):
        validate_review(selected, review, small_protocol)


def test_manifest_is_deterministic_and_pins_both_evaluation_and_runtime_inputs(examples: list[dict], small_protocol: dict) -> None:
    review = reviewed(examples, small_protocol)
    manifest = build_manifest(examples, small_protocol, review)
    assert build_manifest(list(reversed(examples)), small_protocol, review) == manifest
    assert manifest["selected_count"] == 4
    for split in ("development", "held_out"):
        entries = [entry for entry in manifest["questions"] if entry["split"] == split]
        assert set(manifest["manual_claim_review_question_ids"][split]) == {entry["question_id"] for entry in entries}
    selected, _ = select_rows(examples, small_protocol["selection"], {})
    selected[0][1]["answer"] = "a new reference"
    changed = build_manifest(examples, small_protocol, review)
    assert manifest["questions"][0]["source_row_sha256"] != changed["questions"][0]["source_row_sha256"]
    assert manifest["questions"][0]["runtime_input_sha256"] == changed["questions"][0]["runtime_input_sha256"]


def test_semantic_json_hashes_survive_lf_and_crlf_checkouts(tmp_path: Path) -> None:
    value = {"question": "A question", "nested": {"answer": "A reference"}}
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    text = json.dumps(value, indent=2) + "\n"
    lf.write_bytes(text.encode("utf-8"))
    crlf.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert fingerprint(read_json(lf)) == fingerprint(read_json(crlf))


def test_missing_or_modified_raw_sources_fail_before_parquet_reading(tmp_path: Path) -> None:
    benchmark = load_protocol()["benchmark"]
    with pytest.raises(FileNotFoundError, match="source is missing"):
        load_source(tmp_path / "missing.parquet", benchmark)
    path = tmp_path / "wrong.parquet"
    path.write_bytes(b"not the benchmark")
    with pytest.raises(ValueError, match="pinned size and SHA"):
        load_source(path, benchmark)


def test_parquet_reader_preserves_the_source_and_checks_row_count(tmp_path: Path, examples: list[dict]) -> None:
    pyarrow = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")
    source = tmp_path / "source.parquet"
    parquet.write_table(pyarrow.Table.from_pylist(examples), source)
    benchmark = {"size_bytes": source.stat().st_size, "sha256": sha256_file(source), "expected_rows": len(examples)}
    assert load_source(source, benchmark) == examples
    benchmark["expected_rows"] += 1
    with pytest.raises(ValueError, match="source rows"):
        load_source(source, benchmark)


def test_checked_in_selection_has_sixty_reviewed_two_document_questions() -> None:
    protocol = load_protocol(DEFAULT_PROTOCOL)
    manifest = read_json(ROOT / protocol["selection"]["manifest"])
    review = read_json(ROOT / protocol["selection"]["necessity_review"])
    assert manifest["selected_count"] == 60
    assert manifest["split_counts"] == protocol["selection"]["splits"]
    assert manifest["protocol_semantic_sha256"] == fingerprint(protocol)
    assert manifest["necessity_review_semantic_sha256"] == fingerprint(review)
    assert manifest["source_sha256"] == protocol["benchmark"]["sha256"]
    assert manifest["source_audit"]["distinct_context_titles"] == 600
    ids = [entry["question_id"] for entry in manifest["questions"]]
    assert len(set(ids)) == 60
    assert set(ids) <= set(review["accepted"])
    for entry in manifest["questions"]:
        assert len(entry["supporting_document_titles"]) == 2
        assert entry["context_document_count"] == 10
        assert len(entry["source_row_sha256"]) == 64
        assert len(entry["runtime_input_sha256"]) == 64


def command_fixture(tmp_path: Path, small_protocol: dict, examples: list[dict], monkeypatch) -> tuple[list[str], Path]:
    config = tmp_path / "config" / "assessment_protocol_v1.json"
    config.parent.mkdir()
    config.write_text(json.dumps(small_protocol), encoding="utf-8")
    review_path = tmp_path / small_protocol["selection"]["necessity_review"]
    review_path.parent.mkdir(parents=True)
    review_path.write_text(json.dumps(reviewed(examples, small_protocol)), encoding="utf-8")
    monkeypatch.setattr(protocol_module, "load_source", lambda _path, _benchmark: examples)
    return ["--protocol", str(config), "--source", str(tmp_path / "source.parquet")], tmp_path / small_protocol["selection"]["manifest"]


def test_command_build_and_check_are_idempotent(tmp_path: Path, small_protocol: dict, examples: list[dict], monkeypatch, capsys) -> None:
    args, manifest = command_fixture(tmp_path, small_protocol, examples, monkeypatch)
    protocol_module.main(args)
    assert json.loads(capsys.readouterr().out)["selected_count"] == 4
    original = manifest.read_bytes()
    protocol_module.main([*args, "--check"])
    result = json.loads(capsys.readouterr().out)
    assert result["selected_count"] == 4
    assert result["check_only"] is True
    assert result["paid_api_calls"] == 0
    assert manifest.read_bytes() == original


def test_command_refuses_to_overwrite_a_changed_frozen_selection(tmp_path: Path, small_protocol: dict, examples: list[dict], monkeypatch) -> None:
    args, manifest = command_fixture(tmp_path, small_protocol, examples, monkeypatch)
    protocol_module.main(args)
    original = manifest.read_bytes()
    selected, _ = select_rows(examples, small_protocol["selection"], {})
    selected[0][1]["answer"] = "different reference"
    with pytest.raises(ValueError, match="refusing to overwrite a frozen selection"):
        protocol_module.main(args)
    assert manifest.read_bytes() == original
    with pytest.raises(ValueError, match="differs from the reproducible selection"):
        protocol_module.main([*args, "--check"])


def test_preview_never_freezes_unreviewed_questions(tmp_path: Path, small_protocol: dict, examples: list[dict], monkeypatch, capsys) -> None:
    args, manifest = command_fixture(tmp_path, small_protocol, examples, monkeypatch)
    review_path = tmp_path / small_protocol["selection"]["necessity_review"]
    review = read_json(review_path)
    review["accepted"] = {}
    review_path.write_text(json.dumps(review), encoding="utf-8")
    protocol_module.main([*args, "--preview"])
    result = json.loads(capsys.readouterr().out)
    assert all(candidate["reviewed"] is False for candidate in result["candidates"])
    assert not manifest.exists()
    with pytest.raises(ValueError, match="no completed necessity review"):
        protocol_module.main(args)
    assert not manifest.exists()
