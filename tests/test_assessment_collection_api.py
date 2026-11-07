"""Additive collection surface, independent questions, exact citations and safe failures."""

import json

from fastapi.testclient import TestClient
import pytest

from textbook_chat.app import create_app
from textbook_chat.domain import Backend
from textbook_chat.generation.online import ProviderStreamEvent
from textbook_chat.repositories import CollectionQueryRepository, CollectionRepository
from textbook_audit.assessment_ingestion import import_pdf_source
from test_textbook_chat_app import settings
from test_assessment_generation import evidence, response
from test_assessment_collections import Model, sources
from test_source_provenance import synthetic_pdf


class Offline:
    def __init__(self, raw):
        self.raw = raw

    def stream(self, _prompt):
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
            def stream(self, _prompt):
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
