"""Stable public runtime and validation helpers for Retrieval Baseline v1.

The module contains no benchmark/gold imports.  It loads the immutable YAML,
reuses the measured Phase H ranker, and exposes one structured ``retrieve``
interface for arbitrary student questions scoped by an explicit textbook ID.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from .chunking_bakeoff import build_corpora
from .context_assembly import assemble_context
from .embedding_bakeoff import (load_local_model, load_or_create_embeddings,
                                searchable_pages)
from .retrieval import BM25
from .specialist_retrieval import build_specialist_corpora, rank_combined_query


DEFAULT_CONFIG = Path("config/retrieval_baseline_v1.yaml")
SUPPORTED_PROFILES = ("balanced", "quality")
REQUIRED_TOP_LEVEL = {
    "schema_version", "baseline", "inputs", "chunking", "embedding", "bm25",
    "query_processing", "specialists", "fusion", "output", "context_assembly",
    "indexes", "reproducibility",
}
REQUIRED_NESTED: dict[str, set[str]] = {
    "baseline": {"name", "semantic_version", "source_winning_run_id",
                 "context_assembly_run_id", "frozen"},
    "inputs": {"supported_books", "source_pdfs", "processed_pages", "benchmark",
               "corpus_version", "benchmark_version", "searchable_text_field",
               "front_matter_rule", "search_scope"},
    "chunking": {"strategy", "target_tokens", "overlap_tokens",
                 "token_counting_method", "tokenizer_regex", "boundary_units",
                 "chapter_boundary_isolation", "overlap_unit", "chapter_metadata",
                 "section_metadata", "preserve_all_contributing_pages"},
    "embedding": {"library", "library_version", "model_name", "revision",
                  "dimensions", "normalize_embeddings", "similarity", "query_prefix",
                  "document_prefix", "trust_remote_code", "local_files_only",
                  "device_policy", "batch_size"},
    "bm25": {"implementation", "variant", "k1", "b", "tokenization", "idf"},
    "query_processing": {"method", "preserve_original_query", "append_label",
                         "matching", "deduplicate_additions",
                         "fusion_with_original_query", "synonym_resource", "rules"},
    "specialists": {"formula", "table", "visual", "specialist_retrieval",
                    "page_to_child_lifting"},
    "fusion": {"method", "rrf_k", "base_sources", "activated_source_order",
               "source_weights", "candidate_limit_per_source", "score_formula",
               "tie_break"},
    "output": {"final_top_k", "evidence_unit", "include_text_default",
               "metadata_fields"},
    "context_assembly": {"method", "input_candidate_count", "input_order",
                         "exact_overlap_tokenization", "minimum_exact_overlap_words",
                         "maximum_exact_overlap_words", "merge_without_detected_overlap",
                         "same_page_only", "preserve_source_metadata", "deduplication",
                         "additional_overlap_threshold", "token_budget"},
    "indexes": {"chunk_embeddings", "specialist_directory",
                "specialist_filename_template", "cache_validation_fields"},
    "reproducibility": {"random_seeds", "deterministic_tie_breaking",
                        "gold_labels_available_to_runtime",
                        "historical_experiment_artifacts_mutable"},
}
REQUIRED_DEEP: dict[tuple[str, ...], set[str]] = {
    ("embedding", "device_policy"): {"default", "allowed"},
    ("specialists", "formula"): {"method", "representation_version",
        "activation_version", "activation_query", "activation_pattern", "page_filter",
        "representation", "normalize_unicode_formula_operators_and_units"},
    ("specialists", "table"): {"method", "representation_version",
        "activation_version", "activation_query", "activation_pattern", "page_filter",
        "representation"},
    ("specialists", "visual"): {"method", "representation_version",
        "activation_version", "activation_query", "activation_pattern", "page_filter",
        "representation", "fallback_when_no_caption"},
    ("specialists", "specialist_retrieval"): {"dense_and_bm25_fusion", "rrf_k",
        "source_weights", "candidate_limit"},
    ("specialists", "page_to_child_lifting"): {"method",
        "unrepresented_page_position", "tie_break"},
}


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one file's exact bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_exact_keys(config: dict[str, Any]) -> None:
    """Reject missing and unknown schema fields instead of applying defaults."""
    keys = set(config)
    if keys != REQUIRED_TOP_LEVEL:
        raise ValueError(f"configuration top-level fields differ: missing={sorted(REQUIRED_TOP_LEVEL - keys)}, "
                         f"unknown={sorted(keys - REQUIRED_TOP_LEVEL)}")
    for section, expected in REQUIRED_NESTED.items():
        if not isinstance(config[section], dict):
            raise ValueError(f"configuration section {section!r} must be a mapping")
        actual = set(config[section])
        if actual != expected:
            raise ValueError(f"configuration section {section!r} differs: "
                             f"missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}")
    for path, expected in REQUIRED_DEEP.items():
        value: Any = config
        for key in path:
            value = value[key]
        if not isinstance(value, dict):
            raise ValueError(f"configuration section {'.'.join(path)!r} must be a mapping")
        actual = set(value)
        if actual != expected:
            raise ValueError(f"configuration section {'.'.join(path)!r} differs: "
                             f"missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}")
    for number, rule in enumerate(config["query_processing"]["rules"], 1):
        if not isinstance(rule, dict) or set(rule) != {"name", "triggers", "addition"}:
            raise ValueError(f"synonym rule {number} must contain exactly name/triggers/addition")


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate v1's complete schema and cross-field behavior invariants."""
    _require_exact_keys(config)
    if config["schema_version"] != 1 or config["baseline"]["semantic_version"] != "1.0.0":
        raise ValueError("only Retrieval Baseline v1 schema/version is supported")
    if config["baseline"]["source_winning_run_id"] != "phase_h_h3_combined_specialist_priors":
        raise ValueError("v1 must identify the verified winning run")
    revision = str(config["embedding"]["revision"])
    if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
        raise ValueError("embedding revision must be an exact 40-character lowercase commit")
    target, overlap = config["chunking"]["target_tokens"], config["chunking"]["overlap_tokens"]
    if not isinstance(target, int) or not isinstance(overlap, int) or not 0 <= overlap < target:
        raise ValueError("chunk target/overlap must satisfy 0 <= overlap < target")
    if config["fusion"]["rrf_k"] != 60 or config["specialists"]["specialist_retrieval"]["rrf_k"] != 60:
        raise ValueError("Retrieval Baseline v1 requires RRF k=60 at both fusion stages")
    if config["output"]["final_top_k"] != 5 or config["context_assembly"]["input_candidate_count"] != 5:
        raise ValueError("Retrieval Baseline v1 always returns and assembles five candidates")
    if config["embedding"]["dimensions"] != 384 or not config["embedding"]["normalize_embeddings"]:
        raise ValueError("v1 requires normalized 384-dimensional embeddings")
    if config["bm25"]["k1"] != 1.5 or config["bm25"]["b"] != 0.75:
        raise ValueError("Retrieval Baseline v1 requires BM25 k1=1.5 and b=0.75")
    if not config["query_processing"]["rules"]:
        raise ValueError("frozen synonym rules cannot be empty")
    return config


def load_config(path: Path | str = DEFAULT_CONFIG, root: Path | None = None) -> dict[str, Any]:
    """Load and strictly validate a repository-relative or absolute YAML file."""
    root = (root or Path.cwd()).resolve()
    candidate = Path(path)
    resolved = candidate if candidate.is_absolute() else root / candidate
    if not resolved.is_file():
        raise FileNotFoundError(f"retrieval baseline configuration is missing: {resolved}")
    parsed = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("retrieval baseline configuration must contain a mapping")
    parsed["_config_path"] = str(resolved)
    # Internal provenance is removed while validating the exact public schema.
    public = {key: value for key, value in parsed.items() if key != "_config_path"}
    validate_config(public)
    public["_config_path"] = str(resolved)
    return public


@dataclass(frozen=True)
class EvidenceResult:
    """One ranked fixed chunk with complete retrieval and source provenance."""

    rank: int
    evidence_id: str
    book_id: str
    pdf_pages: list[int]
    textbook_pages: list[Any]
    chapter: str | None
    section: str | None
    text_snippet: str
    evidence_text: str | None
    contributing_retrievers: list[str]
    component_ranks: dict[str, int]
    component_scores: dict[str, float]
    fused_score: float
    activated_specialist_signals: list[str]


@dataclass(frozen=True)
class RetrievalResult:
    """Deterministic structured response from the frozen retrieval pipeline."""

    baseline_name: str
    baseline_version: str
    question: str
    processed_query: str
    book_id: str
    activated_specialist_signals: list[str]
    evidence: list[EvidenceResult]
    assembled_context: list[dict[str, Any]]
    retrieval_latency_ms: float
    model: dict[str, Any]
    cache: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert nested dataclasses to a JSON-serializable mapping."""
        return asdict(self)


class RetrievalBaseline:
    """Loaded immutable v1 model, indexes, BM25 structures, and query API."""

    def __init__(self, root: Path, config: dict[str, Any], device: str | None = None):
        """Build deterministic corpora and reuse validated local embedding caches."""
        self.root = root.resolve()
        self.config = config
        embedding = config["embedding"]
        chosen_device = device or embedding["device_policy"]["default"]
        if chosen_device not in embedding["device_policy"]["allowed"]:
            raise ValueError(f"device must be one of {embedding['device_policy']['allowed']}")
        model_config = {
            "model_name": embedding["model_name"], "revision": embedding["revision"],
            "query_prefix": embedding["query_prefix"],
            "document_prefix": embedding["document_prefix"],
            "trust_remote_code": embedding["trust_remote_code"],
        }
        pages = searchable_pages(self.root)
        self.chunks = build_corpora(self.root)["fixed_600_100"]
        self.loaded = load_local_model(
            model_config, self.root / "data/retrieval/cache/models", chosen_device,
            embedding["batch_size"])
        if self.loaded.metadata["resolved_model_revision"] != embedding["revision"]:
            raise RuntimeError("resolved embedding revision differs from frozen configuration")
        chunk_paths = config["indexes"]["chunk_embeddings"]
        first_path = self.root / next(iter(chunk_paths.values()))
        chunk_key = first_path.stem.rsplit("_", 1)[0]
        self.matrices, self.chunk_index = load_or_create_embeddings(
            self.loaded, self.chunks, first_path.parent, chunk_key,
            embedding["batch_size"], document_prefix=embedding["document_prefix"])
        specialist_corpora = build_specialist_corpora(pages)
        specialist_dir = self.root / config["indexes"]["specialist_directory"]
        self.resources: dict[str, Any] = {}
        self.specialist_indexes: dict[str, Any] = {}
        for branch in ("formula", "table", "visual"):
            method = config["specialists"][branch]["method"]
            matrices, metadata = load_or_create_embeddings(
                self.loaded, specialist_corpora[method], specialist_dir,
                f"phase_h_{method}", embedding["batch_size"],
                document_prefix=embedding["document_prefix"])
            self.resources[method] = specialist_corpora[method], matrices
            self.specialist_indexes[method] = metadata
        bm25 = config["bm25"]
        self.child_bm25 = {book: BM25((item["text"] for item in chunks), bm25["k1"], bm25["b"])
                           for book, chunks in self.chunks.items()}
        self.specialist_bm25 = {
            method: {book: BM25((item["text"] for item in documents), bm25["k1"], bm25["b"])
                     for book, documents in corpora.items()}
            for method, (corpora, _) in self.resources.items()
        }

    def _rank(self, question: str, book_id: str) -> dict[str, Any]:
        """Return the complete gold-blind ranking for evaluation/runtime reuse."""
        if not question.strip():
            raise ValueError("question must not be empty")
        if book_id not in self.config["inputs"]["supported_books"]:
            raise ValueError("book_id must be one of: " + ", ".join(self.config["inputs"]["supported_books"]))
        chunks = self.chunks[book_id]
        runtime_config = {
            "rrf_constant": self.config["fusion"]["rrf_k"],
            "synonym_rules": self.config["query_processing"]["rules"],
            "specialists": [
                {"method": value["method"], "branch": branch,
                 "activation_version": value["activation_version"],
                 "activation_pattern": value["activation_pattern"],
                 "activation_query": value["activation_query"]}
                for branch, value in ((name, self.config["specialists"][name])
                                      for name in ("formula", "table", "visual"))
            ],
        }
        return rank_combined_query(
            question, book_id, self.loaded,
            {"query_prefix": self.config["embedding"]["query_prefix"]}, chunks,
            self.matrices[book_id], self.resources, self.child_bm25[book_id],
            self.specialist_bm25, runtime_config=runtime_config)

    def retrieve(self, question: str, book_id: str,
                 include_text: bool | None = None) -> RetrievalResult:
        """Retrieve five book-local chunks and assemble provenance-rich context."""
        include = (self.config["output"]["include_text_default"]
                   if include_text is None else include_text)
        chunks = self.chunks.get(book_id, [])
        ranked = self._rank(question, book_id)
        ranking = [int(index) for index in ranked["ranking"]]
        component_ranks = ranked["component_rankings"]
        raw_scores = ranked["component_raw_scores"]
        evidence: list[EvidenceResult] = []
        for rank, index in enumerate(ranking[:self.config["output"]["final_top_k"]], 1):
            chunk = chunks[index]
            ranks = {name: positions[index] for name, positions in component_ranks.items()}
            component_scores = {
                name: (float(raw_scores[name][index]) if name in raw_scores
                       else 1.0 / (self.config["fusion"]["rrf_k"] + source_rank))
                for name, source_rank in ranks.items()
            }
            evidence.append(EvidenceResult(
                rank=rank, evidence_id=chunk["chunk_id"], book_id=book_id,
                pdf_pages=[int(value) for value in chunk["pdf_pages"]],
                textbook_pages=chunk["textbook_pages"],
                chapter=chunk.get("chapter_title"), section=chunk.get("section_title"),
                text_snippet=" ".join(chunk["text"].split())[:500],
                evidence_text=chunk["text"] if include else None,
                contributing_retrievers=list(ranks), component_ranks=ranks,
                component_scores=component_scores,
                fused_score=float(ranked["scores"][index]),
                activated_specialist_signals=list(ranked["activated_specialists"]),
            ))
        assembly = self.config["context_assembly"]
        segments = assemble_context(
            "overlap_merge_metadata_preserving", ranking, chunks,
            count=assembly["input_candidate_count"],
            overlap_maximum=assembly["maximum_exact_overlap_words"],
            overlap_minimum=assembly["minimum_exact_overlap_words"])
        context = [
            ({**segment} if include else
             {**{key: value for key, value in segment.items() if key != "text"},
              "text_snippet": " ".join(segment["text"].split())[:1000]})
            for segment in segments
        ]
        return RetrievalResult(
            baseline_name=self.config["baseline"]["name"],
            baseline_version=self.config["baseline"]["semantic_version"],
            question=question, processed_query=ranked["processed_query"], book_id=book_id,
            activated_specialist_signals=list(ranked["activated_specialists"]),
            evidence=evidence, assembled_context=context,
            retrieval_latency_ms=float(ranked["latency_ms"]),
            model=self.loaded.metadata,
            cache={"chunks": self.chunk_index, "specialists": self.specialist_indexes},
        )


_RUNTIME_CACHE: dict[tuple[str, str, str], RetrievalBaseline] = {}


def retrieve(question: str, book_id: str, config: Path | str = DEFAULT_CONFIG,
             include_text: bool = False, profile: str = "balanced",
             root: Path | None = None, device: str | None = None) -> RetrievalResult:
    """Stable public entry point: retrieve one question with frozen v1 behavior."""
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"profile must be one of {SUPPORTED_PROFILES}; both are frozen v1 aliases")
    root = (root or Path.cwd()).resolve()
    loaded_config = load_config(config, root)
    key = (str(root), loaded_config["_config_path"], device or loaded_config["embedding"]["device_policy"]["default"])
    if key not in _RUNTIME_CACHE:
        _RUNTIME_CACHE[key] = RetrievalBaseline(root, loaded_config, device)
    return _RUNTIME_CACHE[key].retrieve(question, book_id, include_text)


def main(argv: list[str] | None = None) -> None:
    """Query Retrieval Baseline v1 from a source checkout or installed script."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--book-id", required=True, choices=("biology", "physical_sciences"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--profile", choices=SUPPORTED_PROFILES, default="balanced")
    parser.add_argument("--include-text", action="store_true")
    parser.add_argument("--device")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = retrieve(args.question, args.book_id, args.config, args.include_text,
                      args.profile, args.root, args.device).to_dict()
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        path = args.output if args.output.is_absolute() else args.root / args.output
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
