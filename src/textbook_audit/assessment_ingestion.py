"""Reproducible source ingestion with physically separated evaluation labels."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from uuid import uuid4

from .assessment_assets import (
    FileIdentity, _publish_stream, child_path, load_assets, prepare_inputs, verify_file,
)
from .assessment_protocol import (
    build_manifest, fingerprint, load_protocol, load_source, read_json, runtime_projection,
)
from .collection_index import CollectionIndex, collection_profile
from .embedding_bakeoff import load_local_model
from .experiment_tracking import sha256_file, write_json
from .source_provenance import SourceDocument, benchmark_document, pdf_document


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_VERSION = "assessment-runtime-v1"
LABEL_VERSION = "assessment-evaluation-labels-v1"


@dataclass(frozen=True)
class RuntimeQuestion:
    question_id: str
    question: str
    document_ids: tuple[str, ...]
    runtime_input_sha256: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (self.question_id, self.question)):
            raise ValueError("runtime question identity and text are required")
        if (
            not isinstance(self.document_ids, tuple) or len(self.document_ids) != 10
            or any(not isinstance(document_id, str) for document_id in self.document_ids)
            or len(set(self.document_ids)) != 10
        ):
            raise ValueError("runtime question must retain ten distinct original documents")
        if (
            not isinstance(self.runtime_input_sha256, str) or len(self.runtime_input_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.runtime_input_sha256)
        ):
            raise ValueError("runtime question must retain its frozen input fingerprint")

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id, "question": self.question,
            "document_ids": list(self.document_ids), "runtime_input_sha256": self.runtime_input_sha256,
        }

    @classmethod
    def from_dict(cls, value: Any) -> RuntimeQuestion:
        if not isinstance(value, dict) or set(value) != {
            "question_id", "question", "document_ids", "runtime_input_sha256",
        } or not isinstance(value["document_ids"], list):
            raise ValueError("runtime question contains invalid or forbidden fields")
        return cls(value["question_id"], value["question"], tuple(value["document_ids"]), value["runtime_input_sha256"])

    def validate(self, documents: dict[str, SourceDocument]) -> None:
        if set(self.document_ids) - set(documents):
            raise ValueError("runtime question refers to an unavailable source")
        original = {
            "id": self.question_id, "question": self.question,
            "context": [
                [documents[document_id].title, [unit.text for unit in documents[document_id].units]]
                for document_id in self.document_ids
            ],
        }
        if fingerprint(original) != self.runtime_input_sha256:
            raise ValueError("runtime question differs from its frozen label-isolated projection")


def compile_runtime(
    rows: Sequence[dict[str, Any]], protocol: dict[str, Any], selection: dict[str, Any],
) -> tuple[list[RuntimeQuestion], list[SourceDocument]]:
    """This projection reads identity, question and context, never reference labels."""
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("source question identities are not unique")
    documents, questions = {}, []
    for entry in selection["questions"]:
        projection = runtime_projection(by_id[entry["question_id"]], protocol["selection"])
        if fingerprint(projection) != entry["runtime_input_sha256"]:
            raise ValueError("selected runtime input changed")
        ids = []
        for title, sentences in projection["context"]:
            document = benchmark_document(title, sentences, protocol["benchmark"]["sha256"])
            if document.document_id in documents and documents[document.document_id] != document:
                raise ValueError("runtime source identity is inconsistent")
            documents[document.document_id] = document
            ids.append(document.document_id)
        questions.append(RuntimeQuestion(
            projection["id"], projection["question"], tuple(ids), entry["runtime_input_sha256"],
        ))
    if len({question.question_id for question in questions}) != len(questions):
        raise ValueError("frozen question selection contains duplicates")
    return questions, [documents[document_id] for document_id in sorted(documents)]


def compile_labels(
    rows: Sequence[dict[str, Any]], protocol: dict[str, Any], selection: dict[str, Any],
) -> dict[str, Any]:
    by_id = {row["id"]: row for row in rows}
    references = []
    for entry in selection["questions"]:
        row = by_id[entry["question_id"]]
        if fingerprint(row) != entry["source_row_sha256"]:
            raise ValueError("selected evaluation reference changed")
        references.append({
            "question_id": row["id"], "split": entry["split"], "question_type": entry["question_type"],
            "answer": row["answer"],
            "supporting_facts": [
                [title, index] for title, index in zip(
                    row["supporting_facts"]["title"], row["supporting_facts"]["sent_id"], strict=True,
                )
            ],
            "source_row_sha256": entry["source_row_sha256"],
        })
    core = {
        "version": LABEL_VERSION, "protocol_sha256": fingerprint(protocol),
        "selection_sha256": fingerprint(selection), "source_sha256": protocol["benchmark"]["sha256"],
        "dataset_license": protocol["benchmark"]["dataset_license"], "references": references,
    }
    return {**core, "checksum": fingerprint(core)}


class RuntimeCorpus:
    """An inference facade whose loader never opens the evaluation directory."""

    def __init__(self, index: CollectionIndex, questions: Sequence[RuntimeQuestion], manifest: dict[str, Any]):
        self.index = index
        self.questions = {question.question_id: question for question in questions}
        self.manifest = manifest
        if any(document.kind != "hotpotqa" for document in index.documents):
            raise ValueError("benchmark runtime corpus must contain original HotpotQA paragraphs")
        if len(self.questions) != len(questions):
            raise ValueError("runtime corpus contains duplicate questions")
        for question in questions:
            question.validate(index.catalog)

    def question(self, question_id: str) -> RuntimeQuestion:
        if question_id not in self.questions:
            raise LookupError("runtime question not found")
        return self.questions[question_id]

    def for_question(self, question_id: str) -> CollectionIndex:
        return self.index.subset(self.question(question_id).document_ids)

    @classmethod
    def load(cls, directory: Path) -> RuntimeCorpus:
        manifest = read_json(directory / "manifest.json")
        fields = {
            "version", "protocol_sha256", "selection_sha256", "source_sha256",
            "question_count", "document_count", "questions_sha256", "corpus_fingerprint",
            "profile_fingerprint", "checksum",
        }
        if not isinstance(manifest, dict) or set(manifest) != fields or manifest["version"] != RUNTIME_VERSION:
            raise ValueError("runtime corpus manifest is invalid")
        if manifest["checksum"] != fingerprint({key: value for key, value in manifest.items() if key != "checksum"}):
            raise ValueError("runtime corpus manifest checksum is invalid")
        questions_path = directory / "questions.json"
        if sha256_file(questions_path) != manifest["questions_sha256"]:
            raise ValueError("runtime question artifact changed")
        values = read_json(questions_path)
        if not isinstance(values, list):
            raise ValueError("runtime questions must be an array")
        questions = [RuntimeQuestion.from_dict(value) for value in values]
        index = CollectionIndex.load(directory / "index")
        if (
            len(questions) != manifest["question_count"] or len(index.documents) != manifest["document_count"]
            or index.corpus_fingerprint != manifest["corpus_fingerprint"]
            or index.profile_fingerprint != manifest["profile_fingerprint"]
        ):
            raise ValueError("runtime corpus counts or fingerprints changed")
        return cls(index, questions, manifest)


def read_evaluation_labels(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict) or set(payload) != {
        "version", "protocol_sha256", "selection_sha256", "source_sha256",
        "dataset_license", "references", "checksum",
    } or payload["version"] != LABEL_VERSION:
        raise ValueError("evaluation labels have invalid fields or version")
    if payload["checksum"] != fingerprint({key: value for key, value in payload.items() if key != "checksum"}):
        raise ValueError("evaluation label checksum is invalid")
    if not isinstance(payload["references"], list):
        raise ValueError("evaluation references must be an array")
    seen = set()
    for row in payload["references"]:
        if not isinstance(row, dict) or set(row) != {
            "question_id", "split", "question_type", "answer", "supporting_facts", "source_row_sha256",
        }:
            raise ValueError("evaluation reference has invalid fields")
        if (
            not isinstance(row["question_id"], str) or not row["question_id"].strip()
            or row["question_id"] in seen
            or not isinstance(row["split"], str) or row["split"] not in {"development", "held_out"}
            or not isinstance(row["question_type"], str) or row["question_type"] not in {"bridge", "comparison"}
        ):
            raise ValueError("evaluation reference identity or split/type is invalid")
        seen.add(row["question_id"])
        if not isinstance(row["answer"], str) or not row["answer"].strip() or not isinstance(row["supporting_facts"], list):
            raise ValueError("evaluation reference answer or locations are invalid")
        for pair in row["supporting_facts"]:
            if (
                not isinstance(pair, list) or len(pair) != 2 or not isinstance(pair[0], str)
                or isinstance(pair[1], bool) or not isinstance(pair[1], int) or pair[1] < 0
            ):
                raise ValueError("evaluation supporting-fact location is invalid")
    return payload


def validate_reference_alignment(labels: dict[str, Any], corpus: RuntimeCorpus) -> None:
    for key in ("protocol_sha256", "selection_sha256", "source_sha256"):
        if labels[key] != corpus.manifest[key]:
            raise ValueError("evaluation labels do not match the runtime cohort")
    if {row["question_id"] for row in labels["references"]} != set(corpus.questions):
        raise ValueError("evaluation references do not cover the exact runtime question set")
    for row in labels["references"]:
        question = corpus.question(row["question_id"])
        documents = {corpus.index.catalog[document_id].title: corpus.index.catalog[document_id]
                     for document_id in question.document_ids}
        if len({pair[0] for pair in row["supporting_facts"]}) != 2:
            raise ValueError("evaluation reference must retain two supporting documents")
        for title, index in row["supporting_facts"]:
            if title not in documents or not documents[title].unit(f"sentence:{index:06d}").text.strip():
                raise ValueError("evaluation reference points outside its runtime source text")


def load_assessment_model(root: Path) -> Any:
    assets, profile = load_assets(root), collection_profile(root)
    snapshot = child_path(root, assets["embedding"]["directory"])
    return load_local_model({
        "model_name": profile["model_name"], "revision": profile["model_revision"],
        "query_prefix": profile["query_prefix"], "document_prefix": profile["document_prefix"],
        "trust_remote_code": False,
    }, snapshot.parents[2], "cpu", profile["batch_size"])


def publish_benchmark_corpus(
    destination: Path, questions: Sequence[RuntimeQuestion], documents: Sequence[SourceDocument],
    labels: dict[str, Any], protocol: dict[str, Any], selection: dict[str, Any],
    model: Any, profile: dict[str, Any],
) -> RuntimeCorpus:
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError("assessment corpus destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".{destination.name}-{uuid4().hex}.partial"
    staging.mkdir(exist_ok=False)
    try:
        index = CollectionIndex.build(documents, model, profile)
        index.save(staging / "runtime" / "index")
        write_json(staging / "runtime" / "questions.json", [question.to_dict() for question in questions])
        core = {
            "version": RUNTIME_VERSION, "protocol_sha256": fingerprint(protocol),
            "selection_sha256": fingerprint(selection), "source_sha256": protocol["benchmark"]["sha256"],
            "question_count": len(questions), "document_count": len(documents),
            "questions_sha256": sha256_file(staging / "runtime" / "questions.json"),
            "corpus_fingerprint": index.corpus_fingerprint, "profile_fingerprint": index.profile_fingerprint,
        }
        write_json(staging / "runtime" / "manifest.json", {**core, "checksum": fingerprint(core)})
        write_json(staging / "evaluation" / "labels.json", labels)
        corpus = RuntimeCorpus.load(staging / "runtime")
        verified_labels = read_evaluation_labels(staging / "evaluation" / "labels.json")
        validate_reference_alignment(verified_labels, corpus)
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return RuntimeCorpus.load(destination / "runtime")


def ingest_benchmark(root: Path, destination: Path, *, check: bool = False) -> RuntimeCorpus:
    prepare_inputs(root, download=not check)
    assets = load_assets(root)
    protocol = load_protocol(child_path(root, assets["protocol_file"]))
    selection = read_json(child_path(root, protocol["selection"]["manifest"]))
    rows = load_source(child_path(root, assets["benchmark"]["path"]), protocol["benchmark"])
    review = read_json(child_path(root, protocol["selection"]["necessity_review"]))
    if build_manifest(rows, protocol, review) != selection:
        raise ValueError("benchmark ingestion does not reproduce frozen selection")
    questions, documents = compile_runtime(rows, protocol, selection)
    expected_labels = compile_labels(rows, protocol, selection)
    if destination.exists():
        corpus = RuntimeCorpus.load(destination / "runtime")
        labels = read_evaluation_labels(destination / "evaluation" / "labels.json")
        validate_reference_alignment(labels, corpus)
        if (
            [question.to_dict() for question in corpus.questions.values()] != [question.to_dict() for question in questions]
            or corpus.manifest["protocol_sha256"] != fingerprint(protocol)
            or corpus.index.profile != collection_profile(root) or labels != expected_labels
        ):
            raise ValueError("existing assessment corpus differs from its declared inputs")
        return corpus
    if check:
        raise FileNotFoundError("assessment runtime corpus has not been ingested")
    return publish_benchmark_corpus(
        destination, questions, documents, expected_labels, protocol, selection,
        load_assessment_model(root), collection_profile(root),
    )


def import_pdf_source(
    data_dir: Path, database: Any, source: Path, *, authorized: bool,
    title: str | None = None, book_id: str | None = None,
) -> SourceDocument:
    from textbook_chat.repositories import CollectionRepository

    if not authorized:
        raise PermissionError("PDF indexing requires authorization for local use")
    document = pdf_document(source, title)
    relative = f"sources/{document.source_sha256}/source.pdf"
    destination = child_path(data_dir, relative)
    identity = FileIdentity(source.stat().st_size, document.source_sha256)
    if destination.exists():
        verify_file(destination, identity)
    else:
        with source.open("rb") as handle:
            _publish_stream(handle, destination, identity)
    CollectionRepository(database).register_document(document, book_id=book_id, artifact_path=relative)
    return document


def ingest_demo(root: Path, *, authorized: bool) -> dict[str, Any]:
    from textbook_chat.database import Database
    from textbook_chat.repositories import CollectionRepository

    if not authorized:
        raise PermissionError("demo PDF ingestion requires --authorized-demo-use")
    prepare_inputs(root, demo_books_dir=root / "books", authorized_demo_use=True)
    assets = load_assets(root)
    data_dir = root / "app_data"
    database = Database(data_dir / "app.db")
    database.initialize()
    documents = [
        import_pdf_source(data_dir, database, root / "books" / book["filename"], authorized=True)
        for book in assets["demo_books"]["books"].values()
    ]
    store = CollectionRepository(database)
    wanted = {document.document_id for document in documents}
    collection = next((item for item in store.list() if set(item["document_ids"]) == wanted), None)
    if collection is None:
        collection = store.create("Assessment textbooks", [document.document_id for document in documents])
    profile = collection_profile(root)
    key = fingerprint({"collection": collection["fingerprint"], "profile": fingerprint(profile)})
    directory = data_dir / "assessment" / "collections" / key
    if directory.exists():
        index = CollectionIndex.load(directory)
        if index.collection_fingerprint != collection["fingerprint"] or index.profile != profile:
            raise ValueError("cached demo collection differs from its sources/profile")
    else:
        index = CollectionIndex.build(documents, load_assessment_model(root), profile)
        index.save(directory)
    return {**collection, "index_key": key, "corpus_fingerprint": index.corpus_fingerprint}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--authorized-demo-use", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.demo:
        if args.check or args.output is not None:
            raise ValueError("demo mode cannot use --check or --output")
        print(json.dumps(ingest_demo(root, authorized=args.authorized_demo_use), indent=2))
    else:
        if args.authorized_demo_use:
            raise ValueError("--authorized-demo-use belongs to --demo")
        destination = args.output.resolve() if args.output is not None else root / "app_data" / "assessment" / "inputs-v1"
        corpus = ingest_benchmark(root, destination, check=args.check)
        print(json.dumps({
            "runtime_version": RUNTIME_VERSION, "questions": len(corpus.questions),
            "documents": len(corpus.index.documents), "corpus_fingerprint": corpus.index.corpus_fingerprint,
            "profile_fingerprint": corpus.index.profile_fingerprint, "paid_model_calls": 0,
        }, indent=2))


if __name__ == "__main__":
    main()
