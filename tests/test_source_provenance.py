"""Exact, gold-blind provenance through source, chunk, context and disk boundaries."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from textbook_audit.chunk_retrieval import fixed_chunks, structured_chunks
from textbook_audit.context_assembly import METHODS, _hard_budget, assemble_context
from textbook_audit.source_provenance import (
    ProvenanceText,
    SourceDocument,
    SourceSpan,
    SourceUnit,
    benchmark_document,
    clean_pdf_text,
    join_text,
    merge_overlap,
    normalize_words,
    pdf_document,
    physical_pages,
    read_source_bundle,
    resolve_citation,
    retrieval_units,
    source_locations,
    truncate_words,
    validate_citation,
    write_source_bundle,
)
from textbook_chat.ingestion.validator import _clean_page


ROOT = Path(__file__).resolve().parents[1]
SOURCE_HASH = "a" * 64


def synthetic_pdf(path: Path, pages: list[str], edition: str = "first") -> None:
    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    for text in pages:
        page = writer.add_blank_page(width=300, height=300)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
        })
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 200 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.add_metadata({"/Subject": edition})
    writer.write(path)


def paragraph(title: str = "Alpha", sentences: list[str] | None = None) -> SourceDocument:
    return benchmark_document(title, sentences if sentences is not None else [
        "Zero one two three four five six seven eight nine.",
        "Ten eleven twelve thirteen fourteen fifteen sixteen seventeen.",
    ], SOURCE_HASH)


def catalog(*documents: SourceDocument) -> dict[str, SourceDocument]:
    return {document.document_id: document for document in documents}


def mapped(chunk: dict) -> ProvenanceText:
    return ProvenanceText.from_dict(chunk["source_provenance"])


def test_pdf_identity_is_content_based_not_filename_or_chapter(tmp_path: Path) -> None:
    path = tmp_path / "first.pdf"
    synthetic_pdf(path, ["Source one.", "Source two."])
    first = pdf_document(path, "Display title")
    renamed = tmp_path / "renamed.pdf"
    renamed.write_bytes(path.read_bytes())
    same = pdf_document(renamed, "Another display title")
    changed = tmp_path / "new-edition.pdf"
    synthetic_pdf(changed, ["Source one.", "Source two."], edition="second")
    different = pdf_document(changed)

    assert first.document_id == same.document_id
    assert first.content_sha256 == same.content_sha256
    assert first.document_id == "pdf:" + hashlib.sha256(path.read_bytes()).hexdigest()
    assert first.document_id != different.document_id
    assert len(first.units) == 2
    assert [unit.unit_id for unit in first.units] == ["pdf_page:000001", "pdf_page:000002"]
    assert all(row["textbook_page_number"] is None for row in retrieval_units(first))
    assert SourceDocument.from_dict(first.to_dict()) == first
    assert SourceDocument.from_dict(json.loads(json.dumps(first.to_dict()))) == first


def test_benchmark_preserves_exact_titles_empty_sentences_and_original_indices() -> None:
    document = paragraph("  Exact Title \u03b2 ", ["First.", "", "   ", "Fourth."])
    assert document.title == "  Exact Title \u03b2 "
    assert len(document.units) == 4
    assert document.unit("sentence:000003").text == "Fourth."
    assert document.document_id == paragraph(document.title, ["First.", "", "   ", "Fourth."]).document_id
    assert document.document_id != paragraph(document.title.strip(), ["First.", "", "   ", "Fourth."]).document_id
    assert document.document_id != paragraph(document.title, ["First.", "", "   ", "Changed."]).document_id
    evidence = ProvenanceText.from_unit(document, "sentence:000003")
    citation = resolve_citation(evidence, document.document_id, "sentence:000003", catalog(document))
    assert citation["sentence_index"] == 3
    assert citation["pdf_page"] is None
    assert "textbook_page" not in citation
    assert citation["char_ranges"] == [[0, len("Fourth.")]]


def test_empty_runtime_paragraph_keeps_document_identity_without_inventing_evidence() -> None:
    document = benchmark_document("Empty supplied paragraph", [], SOURCE_HASH)
    assert document.units == ()
    assert SourceDocument.from_dict(document.to_dict()) == document
    assert retrieval_units(document) == []
    assert fixed_chunks(retrieval_units(document)) == []
    with pytest.raises(ValueError, match="outside its document"):
        document.unit("sentence:000000")


@pytest.mark.parametrize("sentences", ["gold answer", {"answer": "gold", "supporting_facts": []}, [False], [3]])
def test_benchmark_factory_rejects_non_runtime_sentence_content(sentences) -> None:
    with pytest.raises(ValueError):
        benchmark_document("Article", sentences, SOURCE_HASH)


def test_source_artifact_and_extraction_identity_survive_serialization() -> None:
    document = paragraph()
    another_artifact = benchmark_document(document.title, [unit.text for unit in document.units], "b" * 64)
    assert document.document_id == another_artifact.document_id
    assert document.content_sha256 != another_artifact.content_sha256
    evidence = ProvenanceText.from_unit(document, document.units[0].unit_id)
    with pytest.raises(ValueError, match="missing or has changed"):
        evidence.validate(catalog(another_artifact))
    payload = document.to_dict()
    payload["extraction_profile"] = "another-extractor"
    with pytest.raises(ValueError, match="does not match its hash"):
        SourceDocument.from_dict(json.loads(json.dumps(payload)))


def test_normalization_cleaning_and_unicode_keep_exact_raw_offsets() -> None:
    raw = "Repeated Header\r\n  photo-\r\n synthesis\tuses \u03b2 and \U0001f331.\r\nRepeated Header\r\n"
    document = paragraph("Unicode", [raw])
    original = ProvenanceText.from_unit(document, "sentence:000000")
    cleaned = clean_pdf_text(original, {"Repeated Header"})
    assert cleaned.text == _clean_page(raw, {"Repeated Header"})
    assert cleaned.text == "photosynthesis uses \u03b2 and \U0001f331."
    cleaned.validate(catalog(document))
    start = cleaned.text.index("\u03b2")
    selected = cleaned.slice(start, start + len("\u03b2 and \U0001f331"))
    selected.validate(catalog(document))
    assert selected.spans[0].source_start == raw.index("\u03b2")
    assert normalize_words(original).text == " ".join(raw.split())
    with pytest.raises(ValueError, match="must be whitespace"):
        join_text((selected,), separator="Invented evidence")


@pytest.mark.parametrize("strategy", ["fixed", "structured"])
def test_shared_chunkers_keep_legacy_text_but_add_exact_source_spans(strategy: str) -> None:
    document = paragraph("Chunks", [
        " First\t  sentence. Second sentence!\nThird sentence contains many more words than expected. ",
        "Another paragraph supplies independently located source words.",
    ])
    rows = retrieval_units(document)
    legacy = [{key: value for key, value in row.items() if key != "source_provenance"} for row in rows]
    if strategy == "fixed":
        exact = fixed_chunks(rows, target=6, overlap=2)
        old = fixed_chunks(legacy, target=6, overlap=2)
    else:
        exact = structured_chunks(rows, minimum=3, maximum=8)
        old = structured_chunks(legacy, minimum=3, maximum=8)
    assert [chunk["text"] for chunk in exact] == [chunk["text"] for chunk in old]
    assert [chunk["token_count"] for chunk in exact] == [chunk["token_count"] for chunk in old]
    assert all(chunk["document_id"] == document.document_id for chunk in exact)
    assert all(chunk["textbook_pages"] == [] for chunk in exact)
    for chunk in exact:
        evidence = mapped(chunk)
        evidence.validate(catalog(document))
        assert chunk["evidence_id"] == evidence.evidence_id


def test_structured_small_tail_merging_preserves_every_source_unit() -> None:
    document = paragraph("Tail", ["One two three four five six seven eight.", "Nine ten."])
    rows = retrieval_units(document)
    rows[0]["section_title"], rows[1]["section_title"] = "A", "B"
    chunks = structured_chunks(rows, minimum=5, maximum=15)
    assert len(chunks) == 1
    evidence = mapped(chunks[0])
    evidence.validate(catalog(document))
    assert source_locations(evidence) == {
        (document.document_id, "sentence:000000"), (document.document_id, "sentence:000001"),
    }


def test_chunking_rejects_mixed_documents_mixed_versions_and_modified_page_text() -> None:
    first, second = paragraph("First"), paragraph("Second")
    for chunker in (fixed_chunks, structured_chunks):
        with pytest.raises(ValueError, match="each source document distinct"):
            chunker(retrieval_units(first) + retrieval_units(second))
        mixed = retrieval_units(first)
        mixed[1].pop("source_provenance")
        with pytest.raises(ValueError, match="exact and legacy"):
            chunker(mixed)
    rows = retrieval_units(first)
    rows[0]["cleaned_text"] = "Altered text."
    with pytest.raises(ValueError, match="differs from its source provenance"):
        fixed_chunks(rows)
    rows = retrieval_units(first)
    rows[0]["source_unit_id"] = "sentence:000001"
    with pytest.raises(ValueError, match="document/location pair"):
        fixed_chunks(rows)
    rows = retrieval_units(first)
    rows[0]["pdf_page_number"] = 1
    with pytest.raises(ValueError, match="physical PDF address"):
        fixed_chunks(rows)


def test_overlap_removal_requires_the_same_words_at_the_same_source_location() -> None:
    document = paragraph("Overlap", ["zero one two three four five six seven eight nine"])
    original = ProvenanceText.from_unit(document, "sentence:000000")
    left = original.slice(0, original.text.index(" six"))
    right = original.slice(original.text.index("three"), len(original.text))
    combined = merge_overlap(left, right, maximum=10, minimum=1)
    assert combined.text == original.text
    combined.validate(catalog(document))
    repeated = paragraph("Repeated", ["Same exact repeated words.", "Same exact repeated words."])
    combined = merge_overlap(
        ProvenanceText.from_unit(repeated, "sentence:000000"),
        ProvenanceText.from_unit(repeated, "sentence:000001"), maximum=10, minimum=1,
    )
    assert combined.text == "Same exact repeated words. Same exact repeated words."
    assert len(source_locations(combined)) == 2
    with pytest.raises(ValueError, match="identical source document"):
        merge_overlap(
            ProvenanceText.from_unit(document, "sentence:000000"),
            ProvenanceText.from_unit(repeated, "sentence:000000"), maximum=10, minimum=1,
        )


def test_context_assembly_never_collapses_independent_documents() -> None:
    first, second = paragraph("First"), paragraph("Second")
    chunks = fixed_chunks(retrieval_units(first), target=10, overlap=2)
    chunks += fixed_chunks(retrieval_units(second), target=10, overlap=2)
    contexts = assemble_context(
        "overlap_merge_metadata_preserving", list(range(len(chunks))), chunks,
        count=len(chunks), overlap_maximum=10, overlap_minimum=1,
    )
    assert len(contexts) == 2
    assert {item["document_id"] for item in contexts} == {first.document_id, second.document_id}
    for item in contexts:
        mapped(item).validate(catalog(first, second))
        assert len(mapped(item).document_hashes) == 1
    wrong = copy.deepcopy(chunks)
    wrong[0]["document_id"] = "different-document"
    with pytest.raises(ValueError, match="addresses differ from its source provenance"):
        assemble_context("top5_relevance", [0], wrong)
    mixed = [chunks[0], {key: value for key, value in chunks[1].items() if key != "source_provenance"}]
    with pytest.raises(ValueError, match="exact and legacy evidence"):
        assemble_context("top5_relevance", [0, 1], mixed)


@pytest.mark.parametrize("method", METHODS)
def test_all_context_methods_support_sentence_addresses_without_pdf_pages(method: str) -> None:
    document = paragraph("Methods", [
        f"Sentence {index} has several independently addressable words." for index in range(8)
    ])
    chunks = fixed_chunks(retrieval_units(document), target=8, overlap=2)
    first = assemble_context(method, list(range(len(chunks))), chunks)
    assert first == assemble_context(method, list(range(len(chunks))), chunks)
    for segment in first:
        mapped(segment).validate(catalog(document))
        assert segment["pdf_pages"] == []
        assert segment["textbook_pages"] == []


def test_budget_clipping_removes_unseen_pages_and_chunk_contributors(tmp_path: Path) -> None:
    path = tmp_path / "two.pdf"
    synthetic_pdf(path, ["One two three four.", "Five six seven eight."])
    document = pdf_document(path)
    chunks = fixed_chunks(retrieval_units(document), target=4, overlap=0)
    contexts = assemble_context(
        "overlap_merge_metadata_preserving", [0, 1], chunks, overlap_minimum=1,
    )
    assert contexts[0]["pdf_pages"] == [1, 2]
    clipped = _hard_budget(contexts, 4)[0]
    assert clipped["pdf_pages"] == [1]
    assert clipped["source_chunk_ids"] == [chunks[0]["chunk_id"]]
    assert clipped["source_ranks"] == [1]
    assert clipped["source_metadata"][0]["pdf_pages"] == [1]
    assert clipped["truncated"] is True
    evidence = mapped(clipped)
    evidence.validate(catalog(document))
    assert physical_pages(evidence) == [1]
    assert truncate_words(evidence, 0).document_hashes == ()
    with pytest.raises(ValueError, match="pair is not present"):
        resolve_citation(evidence, document.document_id, "pdf_page:000002", catalog(document))
    citation = resolve_citation(evidence, document.document_id, "pdf_page:000001", catalog(document))
    with pytest.raises(ValueError, match="integer"):
        validate_citation({**citation, "pdf_page": True}, evidence, catalog(document))
    wrong = copy.deepcopy(chunks)
    wrong[0]["pdf_pages"] = [True]
    with pytest.raises(ValueError, match="addresses differ from its source provenance"):
        assemble_context("top5_relevance", [0], wrong)
    altered = {**clipped, "text": "Invented context."}
    with pytest.raises(ValueError, match="differs from its source provenance"):
        _hard_budget([altered], 1)


def test_citations_bind_document_location_and_retained_char_ranges() -> None:
    first, second = paragraph("First"), paragraph("Second")
    evidence = truncate_words(ProvenanceText.from_unit(first, "sentence:000000"), 3)
    sources = catalog(first, second)
    citation = resolve_citation(evidence, first.document_id, "sentence:000000", sources)
    validate_citation(citation, evidence, sources)
    for field, value in (
        ("document_id", second.document_id), ("unit_id", "sentence:000001"),
        ("pdf_page", 2), ("sentence_index", False), ("char_ranges", [[0, 999]]),
        ("char_ranges", [[False, 4]]),
        ("content_sha256", "b" * 64), ("evidence_id", "invented"),
    ):
        forged = {**citation, field: value}
        with pytest.raises(ValueError):
            validate_citation(forged, evidence, sources)
    with pytest.raises(ValueError, match="missing or has changed"):
        evidence.validate({first.document_id: second})


def test_gold_labels_and_question_order_cannot_change_runtime_source_identities() -> None:
    from textbook_audit.assessment_protocol import runtime_projection

    row = {
        "id": "question-one", "question": "A runtime question?",
        "context": {"title": ["A", "B"], "sentences": [["Source A."], ["Source B."]]},
        "answer": "Gold answer.", "supporting_facts": {"title": ["A"], "sent_id": [0]},
    }
    altered = {
        **row, "id": "question-two", "answer": "Another gold answer.",
        "supporting_facts": {"title": ["B"], "sent_id": [0]},
    }
    selection = {"hash_namespace": "test-context", "seed": 1729}
    before = [benchmark_document(title, sentences, SOURCE_HASH).to_dict()
              for title, sentences in runtime_projection(row, selection)["context"]]
    after = [benchmark_document(title, sentences, SOURCE_HASH).to_dict()
             for title, sentences in runtime_projection(altered, selection)["context"]]
    assert before == after


def test_persistence_is_semantic_but_rejects_text_source_and_address_tampering(tmp_path: Path) -> None:
    document = paragraph("Persisted", ["The exact \u03b2 source.", "", "Another source."])
    evidence = [mapped(chunk) for chunk in fixed_chunks(retrieval_units(document), target=5, overlap=0)]
    path = tmp_path / "bundle.json"
    write_source_bundle(path, [document], evidence)
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(payload, indent=4) + "\r\n", encoding="utf-8")
    restored_documents, restored = read_source_bundle(path)
    assert restored_documents == [document]
    assert restored == evidence
    payload["evidence"][0]["text"] = "Tampered."
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum is invalid"):
        read_source_bundle(path)
    changed = copy.deepcopy(evidence[0].to_dict())
    changed["spans"][0]["source_start"] += 1
    changed["spans"][0]["source_end"] += 1
    with pytest.raises(ValueError, match="evidence ID does not match"):
        ProvenanceText.from_dict(changed)
    original = ProvenanceText.from_unit(document, "sentence:000000")
    forged = ProvenanceText("X" + original.text[1:], original.spans, original.document_hashes)
    with pytest.raises(ValueError, match="exact source span"):
        forged.validate(catalog(document))
    extra = document.to_dict()
    extra["answer"] = "Gold label."
    with pytest.raises(ValueError, match="invalid shape"):
        SourceDocument.from_dict(extra)


@pytest.mark.parametrize("start,end,text_start,text_end", [
    (True, 2, 0, 1), (-1, 1, 0, 2), (0, 0, 0, 0), (0, 3, 0, 2), (0, 2, 1, 0),
])
def test_source_spans_reject_invalid_ranges(start, end, text_start, text_end) -> None:
    with pytest.raises(ValueError):
        SourceSpan("document", "sentence:000000", start, end, text_start, text_end)


def test_provenance_rejects_unmapped_text_unused_documents_and_unknown_locations() -> None:
    document = paragraph()
    with pytest.raises(ValueError, match="missing exact source provenance"):
        ProvenanceText("Unattributed.", (), ())
    with pytest.raises(ValueError, match="text was removed"):
        ProvenanceText("", (), ((document.document_id, document.content_sha256),))
    with pytest.raises(ValueError, match="outside its document"):
        document.unit("pdf_page:000001")
    with pytest.raises(ValueError, match="canonical ordinal"):
        SourceUnit.create("sentence", 0, "Text.").from_dict({
            "unit_id": "sentence:0000000", "text": "Text.",
            "text_sha256": hashlib.sha256(b"Text.").hexdigest(),
        })
    original = ProvenanceText.from_unit(document, "sentence:000000")
    with pytest.raises(ValueError, match="outside its text"):
        original.slice(0, len(original.text) + 1)
    with pytest.raises(ValueError, match="duplicate documents"):
        write_source_bundle(Path("not-written.json"), [document, document], [original])


def test_all_frozen_runtime_paragraphs_keep_original_benchmark_source_addresses() -> None:
    from textbook_audit.assessment_protocol import (
        fingerprint, load_protocol, load_source, read_json, runtime_projection,
    )

    pytest.importorskip("pyarrow")
    source = ROOT / "data" / "retrieval" / "cache" / "assessment_protocol_v1" / "hotpotqa-validation.parquet"
    if not source.is_file():
        pytest.skip("pinned open-benchmark source is not available in this checkout")
    protocol = load_protocol()
    rows = {row["id"]: row for row in load_source(source, protocol["benchmark"])}
    selection = read_json(ROOT / protocol["selection"]["manifest"])
    document_ids = set()
    for entry in selection["questions"]:
        runtime = runtime_projection(rows[entry["question_id"]], protocol["selection"])
        assert fingerprint(runtime) == entry["runtime_input_sha256"]
        for title, sentences in runtime["context"]:
            document = benchmark_document(title, sentences, protocol["benchmark"]["sha256"])
            document_ids.add(document.document_id)
            assert [unit.text for unit in document.units] == sentences
            chunks = fixed_chunks(retrieval_units(document), target=600, overlap=100)
            for chunk in chunks:
                evidence = mapped(chunk)
                evidence.validate(catalog(document))
                for document_id, unit_id in source_locations(evidence):
                    citation = resolve_citation(evidence, document_id, unit_id, catalog(document))
                    assert citation["document_title"] == title
                    assert sentences[citation["sentence_index"]] == document.unit(unit_id).text
                    assert citation["pdf_page"] is None
    assert len(document_ids) == 600


@pytest.mark.parametrize("filename,pages", [
    ("X Biology EM 2025-26.pdf", 257), ("X Physics EM 2025-26.pdf", 327),
])
def test_authorized_real_pdfs_keep_exact_addresses_through_chunking_and_disk(
    tmp_path: Path, filename: str, pages: int,
) -> None:
    source = ROOT / "books" / filename
    if not source.is_file():
        pytest.skip("authorized demonstration PDF is not available in this checkout")
    document = pdf_document(source)
    assert len(document.units) == pages
    chunks = fixed_chunks(retrieval_units(document), target=600, overlap=100)
    sources = catalog(document)
    for chunk in chunks:
        mapped(chunk).validate(sources)
    contexts = assemble_context(
        "overlap_merge_metadata_preserving", [0, 1, len(chunks) - 1], chunks,
        overlap_maximum=140, overlap_minimum=8,
    )
    evidence = [mapped(context) for context in contexts]
    bundle = tmp_path / "real-source.json"
    write_source_bundle(bundle, [document], evidence)
    restored_documents, restored = read_source_bundle(bundle)
    restored_sources = catalog(*restored_documents)
    for item in restored:
        for document_id, unit_id in source_locations(item):
            citation = resolve_citation(item, document_id, unit_id, restored_sources)
            assert 1 <= citation["pdf_page"] <= pages
            assert citation["sentence_index"] is None
            assert citation["char_ranges"]
            validate_citation(citation, item, restored_sources)
