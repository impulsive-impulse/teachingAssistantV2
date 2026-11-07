"""Shared ingestion and physical separation between inference and reference labels."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from textbook_audit.assessment_ingestion import (
    RuntimeCorpus, RuntimeQuestion, compile_labels, compile_runtime, import_pdf_source,
    publish_benchmark_corpus, read_evaluation_labels, validate_reference_alignment,
)
from textbook_audit.assessment_protocol import build_manifest, fingerprint, load_protocol
from textbook_chat.database import Database
from textbook_chat.repositories import CollectionRepository
from test_assessment_collections import Model, profile
from test_assessment_protocol import example, reviewed
from test_source_provenance import synthetic_pdf


def cohort():
    protocol = copy.deepcopy(load_protocol())
    protocol["selection"]["splits"] = {
        "development": {"bridge": 1, "comparison": 1},
        "held_out": {"bridge": 1, "comparison": 1},
    }
    protocol["analysis"]["manual_claim_review_counts"] = {
        "development": {"bridge": 1, "comparison": 1},
        "held_out": {"bridge": 1, "comparison": 1},
    }
    rows = [example(f"{kind}-{number}", kind) for kind in ("bridge", "comparison") for number in range(2)]
    selection = build_manifest(rows, protocol, reviewed(rows, protocol))
    questions, documents = compile_runtime(rows, protocol, selection)
    labels = compile_labels(rows, protocol, selection)
    return rows, protocol, selection, questions, documents, labels


def test_runtime_export_is_unchanged_by_reference_answers_and_support_labels() -> None:
    rows, protocol, selection, expected, documents, _labels = cohort()
    altered = copy.deepcopy(rows)
    for row in altered:
        row["answer"] = "Different reference."
        row["supporting_facts"] = {"title": ["not a runtime source"], "sent_id": [999]}
        row["type"] = "another label"
        row["level"] = "another level"
    actual, sources = compile_runtime(altered, protocol, selection)
    assert actual == expected
    assert sources == documents
    for question in actual:
        assert set(question.to_dict()) == {"question_id", "question", "document_ids", "runtime_input_sha256"}
        assert len(question.document_ids) == 10
    with pytest.raises(ValueError, match="reference changed"):
        compile_labels(altered, protocol, selection)


def test_published_runtime_loads_and_queries_without_an_evaluation_directory(tmp_path: Path) -> None:
    _rows, protocol, selection, questions, documents, labels = cohort()
    directory = tmp_path / "corpus"
    corpus = publish_benchmark_corpus(directory, questions, documents, labels, protocol, selection, Model(), profile())
    verified = read_evaluation_labels(directory / "evaluation" / "labels.json")
    validate_reference_alignment(verified, corpus)
    (directory / "evaluation").rename(tmp_path / "hidden-reference-labels")
    inference = RuntimeCorpus.load(directory / "runtime")
    question = questions[0]
    scoped = inference.for_question(question.question_id)
    assert set(scoped.catalog) == set(question.document_ids)
    assert len(inference.questions) == 4
    assert len(inference.index.documents) == 40
    assert scoped.retrieve(question.question, Model())["document_ids"] == sorted(question.document_ids)
    assert not hasattr(inference, "labels")
    with pytest.raises(LookupError):
        inference.for_question("not selected")


def test_runtime_load_rejects_changed_questions_and_forbidden_fields(tmp_path: Path) -> None:
    _rows, protocol, selection, questions, documents, labels = cohort()
    directory = tmp_path / "corpus"
    publish_benchmark_corpus(directory, questions, documents, labels, protocol, selection, Model(), profile())
    path = directory / "runtime" / "questions.json"
    payload = json.loads(path.read_text("utf-8"))
    payload[0]["answer"] = "Leaked reference."
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="artifact changed"):
        RuntimeCorpus.load(directory / "runtime")
    with pytest.raises(ValueError, match="forbidden fields"):
        RuntimeQuestion.from_dict(payload[0])
    altered = RuntimeQuestion(
        questions[0].question_id, "A changed question?", questions[0].document_ids, questions[0].runtime_input_sha256,
    )
    with pytest.raises(ValueError, match="frozen label-isolated"):
        altered.validate({document.document_id: document for document in documents})


def test_reference_labels_cannot_be_replaced_with_out_of_scope_locations(tmp_path: Path) -> None:
    _rows, protocol, selection, questions, documents, labels = cohort()
    directory = tmp_path / "corpus"
    corpus = publish_benchmark_corpus(directory, questions, documents, labels, protocol, selection, Model(), profile())
    path = directory / "evaluation" / "labels.json"
    modified = copy.deepcopy(labels)
    modified["references"][0]["supporting_facts"][0][1] = True
    modified["checksum"] = fingerprint({key: value for key, value in modified.items() if key != "checksum"})
    path.write_text(json.dumps(modified), encoding="utf-8")
    with pytest.raises(ValueError, match="location is invalid"):
        read_evaluation_labels(path)
    modified = copy.deepcopy(labels)
    selected_ids = set(corpus.question(modified["references"][0]["question_id"]).document_ids)
    outside = next(document for document in documents if document.document_id not in selected_ids)
    modified["references"][0]["supporting_facts"][0][0] = outside.title
    with pytest.raises(ValueError, match="outside"):
        validate_reference_alignment(modified, corpus)


def test_pdf_import_uses_shared_sources_and_requires_local_use_authorization(tmp_path: Path) -> None:
    source = tmp_path / "textbook.pdf"
    synthetic_pdf(source, ["A physical source page.", "A second physical page."])
    database = Database(tmp_path / "data" / "app.db")
    database.initialize()
    with pytest.raises(PermissionError, match="authorization"):
        import_pdf_source(tmp_path / "data", database, source, authorized=False)
    assert CollectionRepository(database).list_documents() == []
    document = import_pdf_source(tmp_path / "data", database, source, authorized=True)
    assert document.kind == "pdf"
    assert len(document.units) == 2
    assert CollectionRepository(database).document(document.document_id) == document
    copied = tmp_path / "data" / "sources" / document.source_sha256 / "source.pdf"
    assert copied.read_bytes() == source.read_bytes()
    assert import_pdf_source(tmp_path / "data", database, source, authorized=True) == document
    copied.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="pinned size/SHA-256"):
        import_pdf_source(tmp_path / "data", database, source, authorized=True)
