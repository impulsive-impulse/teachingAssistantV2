"""PDF-kind addressing and honest missing, conflicting and one-source support."""

import json
import runpy

import pytest

from textbook_audit.assessment_context import context_encoder, pack_units
from textbook_audit.assessment_generation import validate_answer
from textbook_audit.assessment_budget import CallLedger
from textbook_audit.assessment_inference import load_pipeline
from textbook_audit.collection_index import CollectionIndex
from textbook_audit.source_provenance import benchmark_document, pdf_document
from textbook_chat.services.collections import CollectionService
from textbook_chat.database import Database
from textbook_chat.generation.online import ProviderStreamEvent
from textbook_chat.repositories import CollectionRepository
from textbook_chat.domain import Backend
from test_assessment_collections import ROOT, Model, profile
from test_source_provenance import synthetic_pdf
from test_textbook_chat_app import settings


def test_pdf_prompt_uses_physical_units_not_the_benchmark_sentence_example(tmp_path):
    documents = []
    for name, text in (("plants", "Plants capture solar energy."), ("circuits", "Circuits carry electric current.")):
        path = tmp_path / (name + ".pdf")
        synthetic_pdf(path, [text])
        documents.append(pdf_document(path))
    index = CollectionIndex.build(documents, Model(), profile())
    context = pack_units(index.retrieve("Plants circuits?", Model())["evidence"], index.catalog, context_encoder(ROOT))
    prompt = CollectionService.local_prompt("Plants circuits?", context)
    assert '"unit_id": "sentence:000000"' not in prompt["prompt"]
    assert '"unit_id": "pdf_page:000001"' in prompt["prompt"]
    assert "not sentence units" in prompt["prompt"]
    assert prompt["version"] == "collection-local-extractive-v1"
    assert "SOURCE CLAUSE OPTIONS" in prompt["prompt"]
    assert "selected_clause_ids" in prompt["schema"]["properties"]
    assert all(
        choice["citations"][0]["unit_id"] == "pdf_page:000001"
        for choice in prompt["source_clauses"].values()
    )


def local_pdf_context(tmp_path):
    documents = []
    for name, text in (
        ("plants", "Plants capture sunlight. This process stores chemical energy. Activity 1 Hold a plant."),
        ("mirrors", "Parallel sunlight rays converge at the focal point of the concave mirror."),
    ):
        path = tmp_path / (name + ".pdf")
        synthetic_pdf(path, [text])
        documents.append(pdf_document(path))
    index = CollectionIndex.build(documents, Model(), profile())
    context = pack_units(
        index.retrieve("Plants sunlight mirrors chemical energy?", Model())["evidence"],
        index.catalog, context_encoder(ROOT),
    )
    return index, context


def test_local_clause_adapter_preserves_context_and_exact_source_pairs(tmp_path):
    index, context = local_pdf_context(tmp_path)
    package = CollectionService.local_prompt("Compare sunlight and chemical energy in both textbooks.", context)
    choices = package["source_clauses"]
    assert not any(choice["text"].startswith("Activity") for choice in choices.values())
    connected = next(key for key, choice in choices.items() if "This process" in choice["text"])
    assert choices[connected]["text"].startswith("Plants capture sunlight.")
    mirror = next(key for key, choice in choices.items() if "concave mirror" in choice["text"])
    native = json.dumps({
        "status": "answered", "short_answer": "Chemical energy; focal point",
        "selected_clause_ids": [connected, mirror], "missing_information": [],
    })
    raw = CollectionService.local_answer(package, native)
    result = validate_answer(raw, context, index.catalog)
    assert result["valid"]
    assert len({citation["source"]["document_id"] for claim in result["claims"] for citation in claim["citations"]}) == 2
    for claim in json.loads(raw)["claims"]:
        citation = claim["citations"][0]
        segment = next(item for item in context["segments"] if item["evidence_id"] == citation["evidence_id"])
        unit = next(item for item in segment["units"] if item["unit_id"] == citation["unit_id"])
        assert claim["text"] == citation["quote"]
        assert citation["quote"] in unit["text"]


class OnlineSelections:
    def __init__(self, raw=None, error=None):
        self.raw, self.error, self.calls = raw, error, 0
        self.schema = None

    def stream(self, _prompt, *, json_schema):
        self.calls += 1
        self.schema = json_schema
        if self.error:
            raise RuntimeError(self.error)
        yield ProviderStreamEvent("completed", {
            "raw_text": self.raw, "response_status": "completed", "resolved_model": "gpt-4o-2024-08-06",
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        })


def paid_pdf_fixture(tmp_path, provider):
    index, context = local_pdf_context(tmp_path)
    configured = settings(tmp_path)
    database = Database(configured.database_path)
    database.initialize()
    service = CollectionService(configured, CollectionRepository(database), lambda: Model(), None, online_provider=provider)
    pipeline = load_pipeline(ROOT)
    ledger = CallLedger(tmp_path / "test-ledger.sqlite", pipeline["protocol_sha256"])
    return service, index, context, pipeline, ledger


def test_online_pdf_selection_is_counted_once_and_adapted_to_exact_source_claims(tmp_path):
    provider = OnlineSelections()
    service, index, context, pipeline, ledger = paid_pdf_fixture(tmp_path, provider)
    question = "Compare sunlight and chemical energy in both textbooks."
    package = service.local_prompt(question, context)
    provider.raw = json.dumps({
        "status": "answered", "short_answer": "Sunlight",
        "selected_clause_ids": list(package["source_clauses"]), "missing_information": [],
    })
    result = service.paid_pdf_answer(question, context, index, pipeline, ledger, "query", context_encoder(ROOT))
    assert result["validation"]["valid"]
    assert result["native_raw_text"] == provider.raw and "selected_clause_ids" not in result["raw_text"]
    assert result["online_prompt_profile"] == "collection-online-extractive-v1"
    assert provider.schema["properties"]["selected_clause_ids"]["items"]["enum"] == list(package["source_clauses"])
    assert provider.calls == ledger.status()["reserved_or_attempted"] == 1
    assert ledger.status()["phase_counts"]["contingency"] == 1
    for claim in json.loads(result["raw_text"])["claims"]:
        assert claim["text"] == claim["citations"][0]["quote"]


@pytest.mark.parametrize("raw,error", [
    ('{"status":"answered","short_answer":"No","selected_clause_ids":["UNKNOWN"],"missing_information":[]}', None),
    (None, "SECRET_MUST_NOT_BE_RECORDED"),
])
def test_online_pdf_failure_is_retained_and_never_automatically_retried(tmp_path, raw, error):
    provider = OnlineSelections(raw, error)
    service, index, context, pipeline, ledger = paid_pdf_fixture(tmp_path, provider)
    result = service.paid_pdf_answer("Compare sunlight.", context, index, pipeline, ledger, "query", context_encoder(ROOT))
    assert not result["validation"]["valid"] and result["error_code"]
    assert provider.calls == ledger.status()["reserved_or_attempted"] == ledger.status()["failed"] == 1
    assert "SECRET_MUST_NOT_BE_RECORDED" not in json.dumps(result)
    assert result["native_raw_text"] == (raw or "")
    if error:
        assert result["estimated_api_cost_usd"] is None
    else:
        assert result["estimated_api_cost_usd"] > 0


def test_online_pdf_input_bound_fails_before_reserving_or_dispatching(tmp_path):
    provider = OnlineSelections()
    service, index, context, pipeline, ledger = paid_pdf_fixture(tmp_path, provider)
    pipeline = {**pipeline, "maximum_input_tokens": 1}
    with pytest.raises(ValueError, match="approved input"):
        service.paid_pdf_answer("Compare sunlight.", context, index, pipeline, ledger, "query", context_encoder(ROOT))
    assert provider.calls == ledger.status()["reserved_or_attempted"] == 0


@pytest.mark.parametrize("short,expected", [
    ("No, different mechanisms.", "No"), ("Yes: the source agrees.", "Yes"),
    ("No one knows", "No one knows"), ("None", "None"),
])
def test_explicit_yes_no_adapter_extracts_only_an_unambiguous_model_prefix(tmp_path, short, expected):
    _index, context = local_pdf_context(tmp_path)
    package = CollectionService.local_prompt("Compare sunlight. Answer yes or no.", context)
    native = json.dumps({"status": "answered", "short_answer": short,
                         "selected_clause_ids": list(package["source_clauses"]), "missing_information": []})
    assert json.loads(CollectionService.local_answer(package, native))["short_answer"] == expected
    package["question"] = "Name the mechanism."
    assert json.loads(CollectionService.local_answer(package, native))["short_answer"] == short


def test_boolean_adapter_rejects_a_contradictory_native_short_answer(tmp_path):
    _index, context = local_pdf_context(tmp_path)
    package = CollectionService.local_prompt("Answer yes or no.", context)
    with pytest.raises(ValueError, match="ambiguous"):
        CollectionService.local_answer(package, json.dumps({
            "status": "answered", "short_answer": "No, but yes.",
            "selected_clause_ids": list(package["source_clauses"]), "missing_information": [],
        }))


def test_pdf_adapter_replay_is_zero_call_and_preserves_the_original_failure(tmp_path, monkeypatch):
    provider = OnlineSelections()
    service, index, context, _pipeline, ledger = paid_pdf_fixture(tmp_path, provider)
    for document in index.documents:
        service.repository.register_document(document)
    collection = service.repository.create("Replay fixture", list(index.catalog))
    question = "Do plants and mirrors use the same mechanism? Answer yes or no."
    package = service.local_prompt(question, context)
    native = json.dumps({
        "status": "answered", "short_answer": "No, different mechanisms.",
        "selected_clause_ids": list(package["source_clauses"]), "missing_information": [],
    })
    legacy = service.local_answer({"source_clauses": package["source_clauses"]}, native)
    assert not validate_answer(legacy, context, index.catalog)["valid"]
    original_id = service.queries.create(collection, question, Backend.ONLINE)
    service.queries.update(original_id, "failed", {
        "raw_text": legacy, "native_raw_text": native, "online_source_clauses": package["source_clauses"],
        "context": context, "snapshot": {"source_documents": [document.to_dict() for document in index.documents]},
        "validation": validate_answer(legacy, context, index.catalog), "error_code": "claim_validation_failed",
    }, "claim_validation_failed")
    original = service.queries.get(original_id)
    replayed = service.replay_pdf_query(original_id)
    assert replayed["state"] == "completed" and replayed["output"]["short_answer"] == "No"
    assert replayed["execution_mode"] == "cached_pdf_adapter_replay"
    assert service.queries.get(original_id) == original
    assert provider.calls == ledger.status()["reserved_or_attempted"] == 0
    public = service.queries.list_public(collection["id"])
    assert next(row for row in public if row["id"] == replayed["id"])["payload"]["execution_mode"] == "cached_pdf_adapter_replay"
    monkeypatch.setattr(service.repository, "get", lambda _id: {**collection, "fingerprint": "b" * 64})
    with pytest.raises(ValueError, match="collection changed"):
        service.replay_pdf_query(original_id)


@pytest.mark.parametrize("ids", [["UNKNOWN"], ["C1", "C1"], "C1", [None]])
def test_local_clause_adapter_rejects_unknown_duplicate_and_malformed_ids(tmp_path, ids):
    _index, context = local_pdf_context(tmp_path)
    package = CollectionService.local_prompt("Plants sunlight?", context)
    with pytest.raises(ValueError, match="source IDs"):
        CollectionService.local_answer(package, json.dumps({
            "status": "answered", "short_answer": "Plants",
            "selected_clause_ids": ids, "missing_information": [],
        }))


def test_local_clause_adapter_allows_abstention_and_one_source_without_forcing_two(tmp_path):
    index, context = local_pdf_context(tmp_path)
    package = CollectionService.local_prompt("Plants sunlight?", context)
    native = json.dumps({
        "status": "insufficient_evidence", "short_answer": "", "selected_clause_ids": [],
        "missing_information": ["No matching source explains the requested measurement."],
    })
    assert validate_answer(CollectionService.local_answer(package, native), context, index.catalog)["valid"]
    key = next(key for key, choice in package["source_clauses"].items() if "Plants capture sunlight" in choice["text"])
    native = json.dumps({
        "status": "answered", "short_answer": "Sunlight", "selected_clause_ids": [key], "missing_information": [],
    })
    result = validate_answer(CollectionService.local_answer(package, native), context, index.catalog)
    assert result["valid"] and len(result["claims"]) == 1


def test_demo_completion_requires_source_review_bound_to_each_actual_answer():
    verify = runpy.run_path(str(ROOT / "scripts" / "validate_assessment_demo.py"))["verify_review"]
    outcome = {
        "case_id": "fixture", "query_id": "query-1", "state": "completed",
        "both_sources_cited": True, "raw_output_sha256": "a" * 64,
    }
    judgment = {
        "case_id": "fixture", "query_id": "query-1", "raw_output_sha256": "a" * 64,
        "verdict": "supported", "checks": {
            "answers_requested_question": True, "both_source_roles_supported": True,
            "short_answer_supported": True, "valid_locations": True,
        },
    }
    receipt = {"outcomes": [outcome]}
    review = {"version": "assessment-demo-source-review-v1", "reviewer_kind": "assistant source inspection",
              "outcomes": [judgment]}
    verify(receipt, review)
    for changed in ({"verdict": "partial"}, {"query_id": "another-query"}, {"checks": {}},
                    {"raw_output_sha256": "b" * 64}):
        with pytest.raises(ValueError, match="incomplete"):
            verify(receipt, {**review, "outcomes": [{**judgment, **changed}]})
    with pytest.raises(ValueError, match="incomplete"):
        verify({"outcomes": [{**outcome, "both_sources_cited": False}]}, review)


def test_demo_online_requires_explicit_permission_but_cached_check_never_dispatches():
    arguments = runpy.run_path(str(ROOT / "scripts" / "validate_assessment_demo.py"))["arguments"]
    assert arguments([]).backend == "offline"
    with pytest.raises(SystemExit):
        arguments(["--backend", "online"])
    assert arguments(["--backend", "online", "--authorize-online-transmission"]).authorize_online_transmission
    assert arguments(["--backend", "online", "--check"]).check
    assert arguments(["--reuse-query", "fixture"]).reuse_query == ["fixture"]
    assert arguments(["--backend", "online", "--replay-query", "fixture"]).replay_query == ["fixture"]
    with pytest.raises(SystemExit):
        arguments(["--check", "--reuse-query", "fixture"])


def test_demo_query_reuse_requires_the_same_question_collection_backend_and_valid_two_source_claims(tmp_path):
    verify = runpy.run_path(str(ROOT / "scripts" / "validate_assessment_demo.py"))["verify_retained_query"]
    index, context = local_pdf_context(tmp_path)
    package = CollectionService.local_prompt("Compare sunlight and chemical energy.", context)
    raw = CollectionService.local_answer(package, json.dumps({
        "status": "answered", "short_answer": "Sunlight",
        "selected_clause_ids": list(package["source_clauses"]), "missing_information": [],
    }))
    collection = {"id": "collection", "fingerprint": "a" * 64, "document_ids": list(index.catalog)}
    query = {
        "question": "Compare sunlight.", "backend": "online", "state": "completed",
        "collection_id": collection["id"], "collection_fingerprint": collection["fingerprint"],
        "payload": {"raw_text": raw, "context": context,
                    "snapshot": {"source_documents": [document.to_dict() for document in index.documents]}},
    }
    verify(query, collection, query["question"], "online")
    for changed in (
        {"question": "Another question"}, {"backend": "offline"}, {"state": "failed"},
        {"collection_id": "another"}, {"collection_fingerprint": "b" * 64},
    ):
        with pytest.raises(ValueError, match="another demonstration"):
            verify({**query, **changed}, collection, query["question"], "online")
    altered = json.loads(raw)
    altered["claims"][0]["citations"][0]["quote"] = "Invented quotation."
    with pytest.raises(ValueError, match="valid claims"):
        verify({**query, "payload": {**query["payload"], "raw_text": json.dumps(altered)}},
               collection, query["question"], "online")


def test_conflicting_sources_are_resolved_as_two_distinct_quoted_claims():
    documents = [
        benchmark_document("Plants record A", ["Plants have a recorded value of 10."], "a" * 64),
        benchmark_document("Plants record B", ["Plants have a recorded value of 20."], "a" * 64),
    ]
    index = CollectionIndex.build(documents, Model(), profile())
    context = pack_units(index.retrieve("Plants recorded value?", Model())["evidence"], index.catalog, context_encoder(ROOT))
    claims = [{
        "text": segment["units"][0]["text"],
        "citations": [{"evidence_id": segment["evidence_id"], "unit_id": segment["units"][0]["unit_id"],
                       "quote": segment["units"][0]["text"]}],
    } for segment in context["segments"]]
    raw = json.dumps({"status": "answered", "short_answer": "10 and 20", "claims": claims, "missing_information": []})
    result = validate_answer(raw, context, index.catalog)
    assert result["valid"]
    assert len({c["source"]["document_id"] for claim in result["claims"] for c in claim["citations"]}) == 2
    # Valid addresses do not choose which conflicting value is true.
    assert "requires source review" in result["semantic_support"]


def test_missing_evidence_cannot_be_filled_with_an_invented_quote():
    context = pack_units([], {}, context_encoder(ROOT))
    raw = json.dumps({"status": "insufficient_evidence", "short_answer": "", "claims": [],
                      "missing_information": ["No matching source fact was retrieved."]})
    assert validate_answer(raw, context, {})["valid"]
    invented = json.dumps({"status": "answered", "short_answer": "Plants",
                          "claims": [{"text": "Plants capture light.", "citations": [
                              {"evidence_id": "E1", "unit_id": "pdf_page:000001", "quote": "Plants capture light."}]}],
                          "missing_information": []})
    assert not validate_answer(invented, context, {})["valid"]


def test_one_source_answer_does_not_force_a_second_document():
    from test_assessment_generation import evidence, response
    index, context = evidence()
    result = validate_answer(json.dumps(response(context)), context, index.catalog)
    assert result["valid"]
    assert len({c["source"]["document_id"] for claim in result["claims"] for c in claim["citations"]}) == 1
