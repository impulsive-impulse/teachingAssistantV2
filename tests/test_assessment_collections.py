"""Collection persistence, source isolation, index integrity and legacy migrations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from textbook_audit.collection_index import CollectionIndex, collection_profile
from textbook_audit.assessment_protocol import fingerprint
from textbook_audit.source_provenance import benchmark_document, document_set_fingerprint, pdf_document
from textbook_chat.database import Database, MIGRATION_1, MIGRATION_2, MIGRATION_3
from textbook_chat.repositories import BookRepository, CollectionRepository, utc_now
from test_source_provenance import synthetic_pdf


ROOT = Path(__file__).resolve().parents[1]


def sources():
    return [
        benchmark_document("Plants", ["Plants absorb light and grow."], "a" * 64),
        benchmark_document("Circuits", ["Circuits conduct electricity through wires."], "a" * 64),
        benchmark_document("Outside", ["Outside secret saffron information."], "a" * 64),
    ]


def repository(tmp_path: Path) -> CollectionRepository:
    database = Database(tmp_path / "app.db")
    database.initialize()
    return CollectionRepository(database)


class Encoder:
    def encode(self, texts, **_kwargs):
        matrix = np.zeros((len(texts), 3), dtype=np.float32)
        for index, text in enumerate(texts):
            lower = text.lower()
            matrix[index, 0] = "plants" in lower
            matrix[index, 1] = "circuits" in lower
            if not matrix[index].any():
                matrix[index, 2] = 1
            matrix[index] /= np.linalg.norm(matrix[index])
        return matrix


class Model:
    model = Encoder()
    metadata = {"model_name": "fixture", "resolved_model_revision": "fixture-v1", "dimensions": 3}


def profile():
    return {
        **collection_profile(ROOT), "model_name": "fixture", "model_revision": "fixture-v1",
        "dimensions": 3, "query_prefix": "", "document_prefix": "",
    }


def test_additive_migration_keeps_existing_books_chats_and_messages(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(MIGRATION_1 + MIGRATION_2 + MIGRATION_3)
        connection.executemany(
            "INSERT INTO schema_migrations(version,applied_at) VALUES (?, 'old')", [(1,), (2,), (3,)],
        )
        connection.execute(
            "INSERT INTO books(id,book_id,sha256,original_filename,title,status,"
            "ingestion_policy_version,runtime_profile_version,created_at) "
            "VALUES ('book','old-id',?,'old.pdf','Original','ready','upload-policy-v1','retrieval-v1-derived-v1','old')",
            ("a" * 64,),
        )
        connection.execute(
            "INSERT INTO chats(id,book_id,title,default_backend,created_at,updated_at) "
            "VALUES ('chat','book','Old chat','offline','old','old')",
        )
        connection.execute(
            "INSERT INTO user_messages(id,chat_id,question,created_at) VALUES ('message','chat','Original?','old')",
        )
    database = Database(path)
    database.initialize()
    database.initialize()
    with database.connect() as connection:
        assert connection.execute("SELECT title FROM books WHERE id='book'").fetchone()["title"] == "Original"
        assert connection.execute("SELECT book_id FROM chats WHERE id='chat'").fetchone()["book_id"] == "book"
        assert connection.execute("SELECT question FROM user_messages WHERE id='message'").fetchone()["question"] == "Original?"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) AS n FROM source_documents").fetchone()["n"] == 0


def test_document_registration_and_collection_scope_survive_restart(tmp_path: Path) -> None:
    store = repository(tmp_path)
    first, second, outside = sources()
    for document in (first, second, outside):
        store.register_document(document)
    collection = store.create(" Two sources ", [second.document_id, first.document_id])
    restarted = CollectionRepository(Database(store.database.path))
    assert restarted.get(collection["id"]) == collection
    assert collection["title"] == "Two sources"
    assert collection["fingerprint"] == document_set_fingerprint([first, second])
    assert restarted.sources(collection["id"], collection["fingerprint"]) == sorted(
        [first, second], key=lambda document: document.document_id,
    )
    assert outside.document_id not in collection["document_ids"]
    assert len(restarted.list_documents()) == 3
    assert restarted.rename(collection["id"], "Renamed")["fingerprint"] == collection["fingerprint"]


def test_membership_changes_are_atomic_and_stale_readers_cannot_broaden_scope(tmp_path: Path) -> None:
    store = repository(tmp_path)
    first, second, third = sources()
    for document in (first, second, third):
        store.register_document(document)
    collection = store.create("Original", [first.document_id, second.document_id])
    for invalid in ([], [first.document_id, first.document_id], ["unknown"]):
        with pytest.raises((ValueError, LookupError)):
            store.replace_documents(collection["id"], invalid, collection["fingerprint"])
        assert store.get(collection["id"]) == collection
    changed = store.replace_documents(
        collection["id"], [second.document_id, third.document_id], collection["fingerprint"],
    )
    with pytest.raises(RuntimeError, match="reload before"):
        store.sources(collection["id"], collection["fingerprint"])
    with pytest.raises(RuntimeError, match="reload before"):
        store.replace_documents(collection["id"], [first.document_id], collection["fingerprint"])
    assert store.get(collection["id"]) == changed
    store.delete(collection["id"])
    assert store.list() == []
    assert store.document(first.document_id) == first


def test_sources_cannot_be_silently_replaced_or_loaded_after_tampering(tmp_path: Path) -> None:
    store = repository(tmp_path)
    first = sources()[0]
    store.register_document(first)
    assert store.register_document(first)["id"] == first.document_id
    changed = benchmark_document(first.title, [unit.text for unit in first.units], "b" * 64)
    with pytest.raises(ValueError, match="ownership differs"):
        store.register_document(changed)
    assert store.document(first.document_id) == first
    with pytest.raises(ValueError, match="relative"):
        store.register_document(first, artifact_path="..\\escape.pdf")
    with store.database.connect() as connection:
        payload = first.to_dict()
        payload["units"][0]["text"] = "Changed."
        connection.execute(
            "UPDATE source_documents SET source_json=? WHERE id=?", (json.dumps(payload), first.document_id),
        )
    with pytest.raises(ValueError, match="does not match its hash"):
        store.document(first.document_id)


def test_library_book_deletion_cannot_break_collection_source_ownership(tmp_path: Path) -> None:
    store = repository(tmp_path)
    path = tmp_path / "original.pdf"
    synthetic_pdf(path, ["A source textbook."])
    document = pdf_document(path)
    with store.database.connect() as connection:
        connection.execute(
            "INSERT INTO books(id,book_id,sha256,original_filename,title,status,"
            "ingestion_policy_version,runtime_profile_version,created_at) "
            "VALUES ('book','book-source',?,'original.pdf','Book','ready','upload-policy-v1','retrieval-v1-derived-v1',?)",
            (document.source_sha256, utc_now()),
        )
    store.register_document(document, book_id="book", artifact_path="books\\book\\source.pdf")
    collection = store.create("Referenced", [document.document_id])
    books = BookRepository(store.database)
    with pytest.raises(RuntimeError, match="Remove this textbook"):
        books.begin_delete("book")
    assert books.get("book")["status"] == "ready"
    store.delete(collection["id"])
    books.begin_delete("book")
    books.finish_delete("book")
    with pytest.raises(LookupError):
        store.document(document.document_id)


def test_dense_search_really_competes_across_documents_and_subset_has_no_leakage() -> None:
    first, second, outside = sources()
    index = CollectionIndex.build([first, second, outside], Model(), profile())
    scoped = index.subset([first.document_id, second.document_id])
    result = scoped.retrieve("Plants and circuits?", Model())
    assert {item["document_id"] for item in result["evidence"]} == {first.document_id, second.document_id}
    assert len(result["assembled_context"]) == 2
    assert outside.document_id not in json.dumps(result)
    assert scoped.retrieve("plants", Model())["evidence"][0]["document_id"] == first.document_id
    assert scoped.retrieve("circuits", Model())["evidence"][0]["document_id"] == second.document_id
    assert result["checksum"] == scoped.retrieve("Plants and circuits?", Model())["checksum"]
    assert scoped.collection_fingerprint == document_set_fingerprint([first, second])
    assert scoped.corpus_fingerprint != index.corpus_fingerprint
    with pytest.raises(ValueError, match="outside this collection"):
        scoped.subset([outside.document_id])
    with pytest.raises(ValueError, match="read-only"):
        scoped.embeddings[0, 0] = 99


def test_saved_index_reconstructs_provenance_and_detects_corruption(tmp_path: Path) -> None:
    first, second, _ = sources()
    index = CollectionIndex.build([second, first], Model(), profile())
    path = tmp_path / "index"
    index.save(path)
    restored = CollectionIndex.load(path)
    assert restored.profile_fingerprint == index.profile_fingerprint
    assert restored.corpus_fingerprint == index.corpus_fingerprint
    assert restored.chunks == index.chunks
    assert restored.retrieve("plants", Model())["checksum"] == index.retrieve("plants", Model())["checksum"]
    snapshot = restored.retrieve("Plants and circuits?", Model())
    snapshot_path = tmp_path / "retrieval.json"
    restored.write_snapshot(snapshot_path, snapshot)
    assert CollectionIndex.load(path).read_snapshot(snapshot_path) == snapshot
    broadened = {**snapshot, "document_ids": snapshot["document_ids"] + [sources()[2].document_id]}
    with pytest.raises(ValueError):
        restored.write_snapshot(tmp_path / "not-written.json", broadened)
    modified = json.loads(json.dumps(snapshot))
    modified["assembled_context"][0]["text"] = "Invented."
    modified["checksum"] = fingerprint({
        key: value for key, value in modified.items() if key not in {"checksum", "retrieval_latency_ms"}
    })
    with pytest.raises(ValueError, match="text was altered"):
        restored.validate_snapshot(modified)
    with pytest.raises(FileExistsError):
        index.save(path)
    with (path / "embeddings.npz").open("ab") as handle:
        handle.write(b"corrupt")
    with pytest.raises(ValueError, match="integrity verification"):
        CollectionIndex.load(path)
    assert not list(tmp_path.glob("*.partial"))


@pytest.mark.parametrize("matrix", [
    np.zeros((2, 3), dtype=np.float32), np.full((2, 3), np.nan), np.ones((3, 3)),
])
def test_invalid_vectors_cannot_be_published_as_a_ready_collection(matrix) -> None:
    with pytest.raises(ValueError):
        CollectionIndex(sources()[:2], matrix, profile())


def test_invalid_query_scope_profile_and_encoder_fail_explicitly() -> None:
    index = CollectionIndex.build(sources()[:2], Model(), profile())
    for value in ("", "   ", None):
        with pytest.raises(ValueError):
            index.retrieve(value, Model())
    for ids in ([], [sources()[0].document_id] * 2, [None]):
        with pytest.raises(ValueError):
            index.subset(ids)
    with pytest.raises(ValueError, match="top-k"):
        index.retrieve("plants", Model(), top_k=True)
    with pytest.raises(ValueError, match="smaller than"):
        CollectionIndex.build(sources()[:2], Model(), {**profile(), "chunk_overlap": 600})
    with pytest.raises(ValueError, match="encoder differs"):
        CollectionIndex.build(sources()[:2], Model(), {**profile(), "model_revision": "different"})


def test_snapshot_cannot_add_nonretrieved_characters_from_the_same_source_unit() -> None:
    document = benchmark_document(
        "One long source", ["Plants alpha beta gamma delta epsilon zeta eta theta iota."], "a" * 64,
    )
    configured = {**profile(), "chunk_target": 3, "chunk_overlap": 0}
    index = CollectionIndex.build([document], Model(), configured)
    snapshot = index.retrieve("plants", Model(), top_k=1)
    altered = json.loads(json.dumps(snapshot))
    altered["assembled_context"][0]["text"] = index.chunks[-1]["text"]
    altered["assembled_context"][0]["source_provenance"] = index.chunks[-1]["source_provenance"]
    altered["checksum"] = fingerprint({
        key: value for key, value in altered.items() if key not in {"checksum", "retrieval_latency_ms"}
    })
    with pytest.raises(ValueError, match="outside selected evidence"):
        index.validate_snapshot(altered)


def test_pinned_encoder_builds_and_reloads_a_real_multi_document_scope(tmp_path: Path, monkeypatch) -> None:
    from textbook_audit.assessment_protocol import load_protocol, load_source, read_json, runtime_projection
    from textbook_audit.embedding_bakeoff import load_local_model

    pytest.importorskip("sentence_transformers")
    source = ROOT / "data" / "retrieval" / "cache" / "assessment_protocol_v1" / "hotpotqa-validation.parquet"
    cache = ROOT / "app_data" / "models" / "embeddings"
    revision = collection_profile(ROOT)["model_revision"]
    if not source.is_file() or not (cache / "models--BAAI--bge-small-en-v1.5" / "snapshots" / revision).is_dir():
        pytest.skip("verified assessment benchmark and encoder inputs are unavailable")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    protocol = load_protocol()
    selection = read_json(ROOT / protocol["selection"]["manifest"])
    question_id = selection["questions"][0]["question_id"]
    row = next(row for row in load_source(source, protocol["benchmark"]) if row["id"] == question_id)
    runtime = runtime_projection(row, protocol["selection"])
    documents = [
        benchmark_document(title, sentences, protocol["benchmark"]["sha256"])
        for title, sentences in runtime["context"]
    ]
    configured = collection_profile(ROOT)
    model = load_local_model({
        "model_name": configured["model_name"], "revision": configured["model_revision"],
        "query_prefix": configured["query_prefix"], "document_prefix": configured["document_prefix"],
        "trust_remote_code": False,
    }, cache, "cpu", configured["batch_size"])
    index = CollectionIndex.build(documents, model, configured)
    index.save(tmp_path / "real-index")
    restored = CollectionIndex.load(tmp_path / "real-index")
    result = restored.retrieve(runtime["question"], model)
    assert len(result["document_ids"]) == 10
    assert len(result["evidence"]) == 5
    assert all(item["document_id"] in result["document_ids"] for item in result["evidence"])
    assert result["collection_fingerprint"] == document_set_fingerprint(documents)
    assert result["embedding_fingerprint"] == index.embedding_fingerprint
