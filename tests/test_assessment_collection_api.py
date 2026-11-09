"""Additive collection surface, independent questions, exact citations and safe failures."""

import json

from fastapi.testclient import TestClient
import pytest

from textbook_chat.app import create_app
from textbook_chat.domain import Backend
from textbook_chat.generation.online import ProviderStreamEvent
from textbook_chat.repositories import CollectionQueryRepository, CollectionRepository
from textbook_audit.assessment_ingestion import import_pdf_source
from textbook_audit.assessment_budget import CallLedger
from textbook_audit.collection_index import CollectionIndex
from test_textbook_chat_app import settings
from test_assessment_generation import evidence, response
from test_assessment_collections import Model, profile, sources
from test_source_provenance import synthetic_pdf


class Offline:
    def __init__(self, raw):
        self.raw = raw

    def stream(self, _prompt, **_kwargs):
        yield ProviderStreamEvent("completed", {
            "raw_text": self.raw, "resolved_model": "fixture-offline",
            "response_status": "completed", "usage": {}, "latency_seconds": 0.01,
        })


def configure(client):
    app = client.app
    store = CollectionRepository(app.state.database)
    for document in sources()[:2]:
        store.register_document(document)
    index, context = evidence()
    service = app.state.collection_service
    service.index = lambda _collection: (index, Model())
    service.offline_provider = Offline(json.dumps(response(context)))
    return store


def test_collection_api_citations_history_restart_and_no_implicit_online(tmp_path):
    configured = settings(tmp_path)
    with TestClient(create_app(configured, run_workers=False)) as client:
        store = configure(client)
        result = client.post("/api/collections", json={
            "title": "Two sources", "document_ids": [document["id"] for document in store.list_documents()],
        })
        assert result.status_code == 201
        collection = result.json()
        url = f"/api/collections/{collection['id']}/queries"
        assert client.post(url, json={"question": "Plants?", "backend": "online"}).status_code == 409
        assert client.get(url).json() == []
        answer = client.post(url, json={"question": "Plants?", "backend": "offline"})
        assert answer.status_code == 201
        row = answer.json()
        assert row["state"] == "completed" and row["output"]["status"] == "answered"
        citation = row["output"]["claims"][0]["citations"][0]
        assert citation["source"]["document_title"] == "Plants"
        document_id = citation["source"]["document_id"]
        unit = client.get(f"/api/sources/{document_id}/units/sentence:000000")
        assert unit.status_code == 200
        assert citation["quote"] in unit.json()["unit"]["text"]
        diagnostics = client.get(f"/api/collection-queries/{row['id']}/diagnostics").json()
        assert "raw_text" in diagnostics["payload"]
        assert "payload" not in client.get(url).json()[0]
    with TestClient(create_app(configured, run_workers=False)) as client:
        assert client.get(url).json()[0]["output"] == row["output"]
        assert len(client.get("/api/collections").json()) == 1


def test_failed_partial_generation_is_durable_and_secret_safe(tmp_path):
    with TestClient(create_app(settings(tmp_path), run_workers=False)) as client:
        store = configure(client)
        collection = store.create("Fixture", [document.document_id for document in sources()[:2]])
        class Failed:
            def stream(self, _prompt, **_kwargs):
                yield ProviderStreamEvent("raw_delta", {"delta": '{"partial":'})
                raise RuntimeError("A_SECRET_MUST_NOT_APPEAR")
        client.app.state.collection_service.offline_provider = Failed()
        url = f"/api/collections/{collection['id']}/queries"
        error = client.post(url, json={"question": "Plants?"})
        assert error.status_code == 409 and "A_SECRET" not in error.text
        row = client.get(url).json()[0]
        assert row["state"] == "failed" and row["output"] is None
        details = client.get(f"/api/collection-queries/{row['id']}/diagnostics").json()
        assert details["payload"]["raw_text"] == '{"partial":'
        assert "A_SECRET" not in json.dumps(details)


def test_original_pdf_route_verifies_bytes_and_physical_unit(tmp_path):
    with TestClient(create_app(settings(tmp_path), run_workers=False)) as client:
        path = tmp_path / "source.pdf"
        synthetic_pdf(path, ["Plants absorb light."])
        document = import_pdf_source(
            client.app.state.settings.data_dir, client.app.state.database, path, authorized=True,
        )
        result = client.get(f"/api/sources/{document.document_id}/file")
        assert result.status_code == 200 and result.content == path.read_bytes()
        result = client.get(f"/api/sources/{document.document_id}/units/pdf_page:000001")
        assert result.status_code == 200
        original = client.app.state.settings.data_dir / "sources" / document.source_sha256 / "source.pdf"
        original.write_bytes(b"changed")
        assert client.get(f"/api/sources/{document.document_id}/file").status_code == 409


def test_active_question_is_exclusive_and_restart_preserves_snapshot(tmp_path):
    with TestClient(create_app(settings(tmp_path), run_workers=False)) as client:
        store = configure(client)
        collection = store.create("Fixture", [document.document_id for document in sources()[:2]])
        queries = CollectionQueryRepository(client.app.state.database)
        query = queries.create(collection, "Plants?", Backend.OFFLINE)
        with pytest.raises(RuntimeError, match="active question"):
            queries.create(collection, "Circuits?", Backend.OFFLINE)
        queries.update(query, "generating", {"snapshot": {"checksum": "retained"}})
        queries.interrupt_active()
        assert queries.get(query)["payload"]["snapshot"]["checksum"] == "retained"
        assert queries.get(query)["error_code"] == "application_restarted"
        with pytest.raises(RuntimeError, match="terminal"):
            queries.update(query, "completed", {})


def test_public_history_does_not_decode_private_source_snapshots(tmp_path, monkeypatch):
    with TestClient(create_app(settings(tmp_path), run_workers=False)) as client:
        store = configure(client)
        collection = store.create("Fixture", [document.document_id for document in sources()[:2]])
        queries = CollectionQueryRepository(client.app.state.database)
        query_id = queries.create(collection, "Plants?", Backend.OFFLINE)
        queries.update(query_id, "failed", {
            "snapshot": {"text": "PRIVATE_SOURCE_" + "S" * 2_000_000}, "raw_text": "PRIVATE_RAW",
            "validation": {"valid": False, "errors": ["fixture failure"]}, "usage": {"input_tokens": 10},
        }, "fixture_failure")
        decode = queries._decode

        def bounded_decode(row):
            assert len(row["payload_json"]) < 1000
            assert "PRIVATE_" not in row["payload_json"]
            return decode(row)

        monkeypatch.setattr(CollectionQueryRepository, "_decode", staticmethod(bounded_decode))
        history = client.get(f"/api/collections/{collection['id']}/queries").json()
        assert history[0]["validation_errors"] == ["fixture failure"]
        assert history[0]["usage"] == {"input_tokens": 10}
        monkeypatch.setattr(CollectionQueryRepository, "_decode", staticmethod(decode))
        diagnostics = client.get(f"/api/collection-queries/{query_id}/diagnostics").json()
        assert diagnostics["payload"]["raw_text"] == "PRIVATE_RAW"
        assert diagnostics["payload"]["snapshot"]["text"].startswith("PRIVATE_SOURCE_")


def test_authorized_online_collection_uses_only_contingency_and_sends_context_not_snapshots(tmp_path, monkeypatch):
    ledgers = []

    def ledger(_path, protocol):
        created = CallLedger(tmp_path / "test-ledger.sqlite", protocol)
        ledgers.append(created)
        return created

    monkeypatch.setattr("textbook_chat.services.collections.CallLedger", ledger)
    with TestClient(create_app(settings(tmp_path), run_workers=False)) as client:
        store = configure(client)
        collection = store.create("Fixture", [document.document_id for document in sources()[:2]])
        service = client.app.state.collection_service
        index, _model = service.index(collection)
        snapshot = index.snapshot

        def private_snapshot(*args, **kwargs):
            return {**snapshot(*args, **kwargs), "private_diagnostic": "SNAPSHOT_MUST_NOT_BE_SENT"}

        monkeypatch.setattr(index, "snapshot", private_snapshot)
        _fixture_index, context = evidence()
        raw = json.dumps(response(context))

        class Online:
            calls = 0

            def stream(self, prompt, *, json_schema):
                self.calls += 1
                assert "SNAPSHOT_MUST_NOT_BE_SENT" not in prompt
                assert "SOURCE EVIDENCE" in prompt
                assert json_schema["properties"]["claims"]["type"] == "array"
                yield ProviderStreamEvent("completed", {
                    "raw_text": raw, "resolved_model": "gpt-4o-2024-08-06",
                    "response_status": "completed", "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                    "latency_seconds": 0.01,
                })

        provider = Online()
        service.online_provider = provider
        url = f"/api/collections/{collection['id']}/queries"
        assert client.post(url, json={"question": "Plants?", "backend": "online"}).status_code == 409
        assert provider.calls == 0 and ledgers == []
        result = client.post(url, json={
            "question": "Plants?", "backend": "online", "online_disclosure_acknowledged": True,
        })
        assert result.status_code == 201 and result.json()["state"] == "completed"
        assert provider.calls == 1
        assert ledgers[0].status()["phase_counts"] == {
            "development": 0, "final_evaluation": 0, "fresh_final_rerun": 0, "contingency": 1,
        }


def test_online_pdf_api_uses_selected_ids_without_rewriting_source_punctuation(tmp_path, monkeypatch):
    pipeline_ledger = None

    def ledger(_path, protocol):
        nonlocal pipeline_ledger
        pipeline_ledger = CallLedger(tmp_path / "pdf-test-ledger.sqlite", protocol)
        return pipeline_ledger

    monkeypatch.setattr("textbook_chat.services.collections.CallLedger", ledger)
    with TestClient(create_app(settings(tmp_path), run_workers=False)) as client:
        documents = []
        for name, text in (
            ("plants", "Plants use sunlight to store chemical energy."),
            ("rays", "A ray bends in a denser medium ."),
        ):
            path = tmp_path / (name + ".pdf")
            synthetic_pdf(path, [text])
            documents.append(import_pdf_source(
                client.app.state.settings.data_dir, client.app.state.database, path, authorized=True,
            ))
        store = CollectionRepository(client.app.state.database)
        collection = store.create("PDF fixture", [document.document_id for document in documents])
        index = CollectionIndex.build(documents, Model(), profile())
        service = client.app.state.collection_service
        service.index = lambda _collection: (index, Model())

        class Select:
            calls = 0

            def stream(self, prompt, *, json_schema):
                self.calls += 1
                assert "selected_clause_ids" in json_schema["properties"]
                options = json.loads(prompt.split("SOURCE CLAUSE OPTIONS:\n", 1)[1])
                yield ProviderStreamEvent("completed", {
                    "raw_text": json.dumps({"status": "answered", "short_answer": "Sunlight; ray",
                                            "selected_clause_ids": list(options), "missing_information": []}),
                    "response_status": "completed", "resolved_model": "gpt-4o-2024-08-06",
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20},
                })

        provider = Select()
        service.online_provider = provider
        url = f"/api/collections/{collection['id']}/queries"
        result = client.post(url, json={
            "question": "Compare sunlight energy with the ray medium.", "backend": "online",
            "online_disclosure_acknowledged": True,
        })
        assert result.status_code == 201 and result.json()["state"] == "completed"
        claims = result.json()["output"]["claims"]
        assert any(claim["citations"][0]["quote"].endswith("medium .") for claim in claims)
        assert {citation["source"]["pdf_page"] for claim in claims for citation in claim["citations"]} == {1}
        assert len({citation["source"]["document_id"] for claim in claims for citation in claim["citations"]}) == 2
        assert provider.calls == pipeline_ledger.status()["reserved_or_attempted"] == 1
        saved = client.get(f"/api/collection-queries/{result.json()['id']}/diagnostics").json()["payload"]
        assert saved["online_prompt_profile"] == "collection-online-extractive-v1"
        assert "selected_clause_ids" in saved["native_raw_text"] and "claims" in saved["raw_text"]
