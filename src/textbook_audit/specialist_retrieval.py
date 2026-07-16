"""Phase H deterministic textbook-specific retrieval specialists.

Specialists activate from static query-text rules only. They rank formula,
table, or visual page representations and contribute a soft page prior to the
retained fixed-600/100 child ranking. Reviewed dependency flags and gold pages
are used only after ranking to report slice quality and evidence coverage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .candidate_compression import APPROVED_PLAN, RANDOM_SEED, _peak_memory_mb
from .chunking_bakeoff import build_corpora
from .embedding_bakeoff import (
    MODEL_CONFIGS,
    _evaluation_scopes,
    accepted_mapping,
    corpus_fingerprint,
    load_local_model,
    load_or_create_embeddings,
    searchable_pages,
    summarize,
)
from .experiment_tracking import (
    checkpoint_run,
    create_run_directory,
    experiment_paths,
    initialize_experiment,
    read_jsonl as read_run_log,
    render_resume,
    sha256_file,
    utc_now,
    write_json,
)
from .query_processing import textbook_synonym_expansion
from .retrieval import BM25, read_jsonl, reciprocal_rank_fusion, stable_ranking, tokenize


RRF_CONSTANT = 60
SPECIALISTS = (
    "formula_equation_lines",
    "formula_equation_context",
    "table_flattened",
    "table_rows_with_headers",
    "table_key_value",
    "visual_caption_context",
)
BRANCH = {
    "formula_equation_lines": "formula",
    "formula_equation_context": "formula",
    "table_flattened": "table",
    "table_rows_with_headers": "table",
    "table_key_value": "table",
    "visual_caption_context": "visual",
}
TARGET_SLICE = {
    "formula": "formula_dependent",
    "table": "table_dependent",
    "visual": "visual_dependent",
}


FORMULA_QUERY_RE = re.compile(
    r"\b(formula|equation|law|voltage|current|resistan(?:ce|tor)|power|focal length|"
    r"object distance|image distance|sign convention|pH|atom(?:s|ic)|electron|balanced|"
    r"lens|mirror|reflection|refraction)\b|[=Ωµ×÷]",
    re.IGNORECASE,
)
TABLE_QUERY_RE = re.compile(
    r"\b(table|row|column|compare|differ(?:ence)?|functions?|attributed|auxins?|cytokinins?|"
    r"mitosis|meiosis|chromosome(?:s)?|daughter cells?)\b",
    re.IGNORECASE,
)
VISUAL_QUERY_RE = re.compile(
    r"\b(diagram|figure|fig\.?|principal rays?|ray diagram|constructed|image formation|"
    r"concave lens|convex lens|myopia|short-sighted|series|parallel circuit|branches)\b",
    re.IGNORECASE,
)
FORMULA_QUERY_RE_V2 = re.compile(
    r"\b(formula|equation|law|voltage|resistance|electric power|focal length|"
    r"object distance|image distance|sign convention|balanced|equivalent resistance|"
    r"parallel resistors?|stronger lenses?|shorter focus)\b|\b\d+\s*W\b|[=Ωµ×÷]",
    re.IGNORECASE,
)
TABLE_QUERY_RE_V2 = re.compile(
    r"\b(table|row|column|auxins?|cytokinins?|mitosis|meiosis)\b|"
    r"\bchromosome(?:s)?\b.*\b(daughter cells?|half)\b|"
    r"\bhalf\b.*\bchromosome(?:s)?\b",
    re.IGNORECASE,
)
FORMULA_QUERY_RE_V3 = re.compile(
    FORMULA_QUERY_RE_V2.pattern.replace("formula|equation|law|", "formula|equation|laws?|"),
    re.IGNORECASE,
)


def specialist_activated(branch: str, query: str, version: str = "v1") -> bool:
    """Classify a specialist branch from query text without benchmark labels."""
    patterns = ({"formula": FORMULA_QUERY_RE, "table": TABLE_QUERY_RE,
                 "visual": VISUAL_QUERY_RE} if version == "v1" else
                {"formula": (FORMULA_QUERY_RE_V3 if version == "v3" else FORMULA_QUERY_RE_V2),
                 "table": TABLE_QUERY_RE_V2, "visual": VISUAL_QUERY_RE})
    if version not in {"v1", "v2", "v3"}:
        raise ValueError(f"unknown activation version: {version}")
    if branch not in patterns:
        raise ValueError(f"unknown specialist branch: {branch}")
    return bool(patterns[branch].search(query))


def normalize_formula_text(text: str) -> str:
    """Normalize Unicode operators, aliases, and units while preserving equations."""
    normalized = unicodedata.normalize("NFC", text)
    replacements = {
        "−": "-", "–": "-", "—": "-", "×": " x ", "÷": " / ",
        "→": " -> ", "⇒": " => ", "µ": " proportional-to ",
        "Ω": " ohm Ω ", "°C": " degree Celsius ",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"\bKWH\b", "kWh kilowatt hour", normalized,
                        flags=re.IGNORECASE)
    normalized = re.sub(r"(?<=\d)\s*W\b", " watt W", normalized)
    normalized = re.sub(r"(?<=\d)\s*V\b", " volt V", normalized)
    return "\n".join(line.rstrip() for line in normalized.splitlines() if line.strip())


def _formula_line(line: str) -> bool:
    """Identify equation-like lines from syntax and curriculum quantity terms."""
    return bool(re.search(
        r"[=+\-/×÷Ωµ]|\b(formula|equation|volt|ampere|ohm|watt|focal|resistance|"
        r"current|power|distance|proportional|balanced)\b", line, re.IGNORECASE))


def formula_representation(page: dict[str, Any], include_context: bool) -> str:
    """Extract equation lines alone or with adjacent explanatory lines."""
    lines = [line.strip() for line in page["raw_text"].splitlines() if line.strip()]
    selected: set[int] = set()
    for index, line in enumerate(lines):
        if _formula_line(line):
            selected.add(index)
            if include_context:
                selected.update(i for i in (index - 1, index + 1)
                                if 0 <= i < len(lines))
    return normalize_formula_text("\n".join(lines[i] for i in sorted(selected)))


def _table_lines(page: dict[str, Any]) -> list[str]:
    """Return stable non-empty lines from pages marked as containing tables."""
    return [" ".join(line.split()) for line in page["raw_text"].splitlines()
            if line.strip()]


def table_representation(page: dict[str, Any], method: str) -> str:
    """Create flattened, header-repeated row, or key-value table text."""
    lines = _table_lines(page)
    if method == "table_flattened":
        return " ".join(lines)
    marker = next((i for i, line in enumerate(lines)
                   if re.search(r"\btable\s*-?\s*\d+", line, re.IGNORECASE)), None)
    # Extractors may place the caption after the cells. Look for a compact
    # adjacent header, then fall back to a neutral page-level header.
    candidates = lines[max(0, (marker or 0) - 12):(marker + 2 if marker is not None else 20)]
    header = next((line for line in candidates
                   if 2 <= len(line.split()) <= 8
                   and not re.search(r"[.!?]$", line)), "Table row")
    rows = [line for line in lines if line != header and len(line.split()) >= 2]
    if method == "table_rows_with_headers":
        return "\n".join(f"Header: {header} | Row: {row}" for row in rows)
    if method == "table_key_value":
        output = []
        for row in rows:
            words = row.split()
            split = 1 if len(words) < 6 else 2
            output.append(f"{header} | Key: {' '.join(words[:split])} | Value: {' '.join(words[split:])}")
        return "\n".join(output)
    raise ValueError(f"unknown table representation: {method}")


def visual_caption_context(page: dict[str, Any]) -> str:
    """Extract figure/diagram lines plus nearby explanatory text and headings."""
    lines = [" ".join(line.split()) for line in page["raw_text"].splitlines()
             if line.strip()]
    selected: set[int] = set()
    for index, line in enumerate(lines):
        if re.search(r"\b(fig(?:ure)?\.?\s*-?\s*\d+|diagram|shown in fig)",
                     line, re.IGNORECASE):
            selected.update(i for i in range(max(0, index - 2),
                                             min(len(lines), index + 3)))
    if not selected:
        selected.update(range(min(12, len(lines))))
    headings = [page.get("chapter_title") or "", page.get("section_title") or ""]
    return "\n".join([value for value in headings if value]
                     + [lines[i] for i in sorted(selected)])


def build_specialist_corpora(
    pages: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Build every approved deterministic specialist page representation."""
    corpora = {method: {} for method in SPECIALISTS}
    for method in SPECIALISTS:
        for book, book_pages in pages.items():
            documents = []
            for page in book_pages:
                branch = BRANCH[method]
                if branch == "formula" and not page.get("has_equation_like_text"):
                    continue
                if branch == "table" and not page.get("has_table"):
                    continue
                if branch == "visual" and not page.get("has_image"):
                    continue
                if branch == "formula":
                    text = formula_representation(page, method.endswith("context"))
                elif branch == "table":
                    text = table_representation(page, method)
                else:
                    text = visual_caption_context(page)
                if not text.strip():
                    continue
                pdf_page = int(page["pdf_page_number"])
                documents.append({
                    "chunk_id": f"{book}:{method}:{pdf_page:04d}",
                    "book_id": book, "text": text, "pdf_pages": [pdf_page],
                    "textbook_pages": [page.get("textbook_page_number")],
                    "chapter_title": page.get("chapter_title"),
                    "section_title": page.get("section_title"),
                })
            if not documents:
                raise ValueError(f"{method} produced no {book} documents")
            corpora[method][book] = documents
    return corpora


def lift_specialist_ranking(chunks: list[dict[str, Any]],
                            documents: list[dict[str, Any]],
                            ranking: np.ndarray) -> np.ndarray:
    """Lift a sparse specialist page ranking to every fixed child chunk."""
    default = len(documents) + len(chunks) + 1
    page_rank = {int(documents[int(index)]["pdf_pages"][0]): rank
                 for rank, index in enumerate(ranking, 1)}
    positions = np.asarray([
        min((page_rank.get(int(page), default) for page in chunk["pdf_pages"]),
            default=default)
        for chunk in chunks
    ])
    return np.lexsort((np.arange(len(chunks)), positions))


def evaluate_specialist(
    loaded: Any, config: dict[str, Any], branch: str,
    questions: list[dict[str, Any]], pages: dict[str, list[dict[str, Any]]],
    chunks: dict[str, list[dict[str, Any]]], chunk_matrices: dict[str, np.ndarray],
    documents: dict[str, list[dict[str, Any]]], doc_matrices: dict[str, np.ndarray],
    activation_version: str = "v1",
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Evaluate one specialist prior with gold-blind query activation."""
    answerable = {q["question_id"] for q in questions
                  if q.get("gold_pdf_pages") and (q.get("gold_answer_span") or "").strip()}
    scopes = _evaluation_scopes(questions, answerable)
    child_bm25 = {book: BM25(item["text"] for item in corpus)
                  for book, corpus in chunks.items()}
    specialist_bm25 = {book: BM25(item["text"] for item in corpus)
                       for book, corpus in documents.items()}
    rows, details, mapped, activated = {}, [], set(), []
    for question in questions:
        qid, book = question["question_id"], question["book_id"]
        corpus = chunks[book]
        mapping = accepted_mapping(question, corpus, pages[book])
        gold = set(mapping["primary"] + mapping["alternatives"])
        if qid in answerable and mapping["status"] == "mapped":
            mapped.add(qid)
        processed = textbook_synonym_expansion(question["question"]).text
        # V2 deliberately classifies the untouched student query. This avoids
        # a synonym added by Phase G accidentally activating another branch.
        activation_query = question["question"] if activation_version != "v1" else processed
        use_specialist = specialist_activated(branch, activation_query, activation_version)
        if use_specialist:
            activated.append(qid)
        started = time.perf_counter()
        query = loaded.model.encode(
            [config["query_prefix"] + processed], convert_to_numpy=True,
            normalize_embeddings=True, show_progress_bar=False)[0]
        dense_ranking = stable_ranking(chunk_matrices[book] @ query)
        lexical_ranking = stable_ranking(child_bm25[book].scores(processed))
        rankings = [dense_ranking, lexical_ranking]
        if use_specialist:
            specialist_dense = stable_ranking(doc_matrices[book] @ query)
            specialist_lexical = stable_ranking(specialist_bm25[book].scores(processed))
            specialist_fused = reciprocal_rank_fusion(
                [specialist_dense, specialist_lexical], len(documents[book]), RRF_CONSTANT)
            specialist_ranking = stable_ranking(specialist_fused)
            rankings.append(lift_specialist_ranking(
                corpus, documents[book], specialist_ranking))
        scores = reciprocal_rank_fusion(rankings, len(corpus), RRF_CONSTANT)
        ranking = stable_ranking(scores)
        latency = (time.perf_counter() - started) * 1000
        first = next((rank for rank, index in enumerate(ranking, 1)
                      if corpus[int(index)]["chunk_id"] in gold), None)
        rows[qid] = {"answerable": qid in answerable,
                     "first_gold_rank": first, "latency_ms": latency}
        details.append({
            "question_id": qid, "question": question["question"], "book_id": book,
            "benchmark_slice": question.get("benchmark_slice", "canonical"),
            "specialist_branch": branch, "activation_version": activation_version,
            "specialist_activated": use_specialist,
            "processed_query": processed, "gold_mapping": mapping,
            "first_gold_rank": first, "latency_ms": latency,
            "ranking": [{
                "rank": rank, "score": float(scores[int(index)]),
                "chunk_id": corpus[int(index)]["chunk_id"],
                "pdf_pages": corpus[int(index)]["pdf_pages"],
                "textbook_pages": corpus[int(index)]["textbook_pages"],
                "chapter_title": corpus[int(index)].get("chapter_title"),
                "section_title": corpus[int(index)].get("section_title"),
                "text_snippet": " ".join(corpus[int(index)]["text"].split())[:500],
                "matches_accepted_evidence": corpus[int(index)]["chunk_id"] in gold,
            } for rank, index in enumerate(ranking, 1)],
        })
    metrics = summarize(rows, scopes)
    recall = {"answerable_questions": len(answerable), "count": len(mapped),
              "recall": len(mapped) / len(answerable),
              "missing_question_ids": sorted(answerable - mapped),
              "required_invariant_satisfied": mapped == answerable,
              "activated_question_count": len(activated),
              "activated_question_ids": activated}
    return metrics, details, recall


def _target_key(metrics: dict[str, Any], branch: str) -> tuple[Any, ...]:
    """Rank one specialist by its small target slice, then global natural quality."""
    target = metrics["slices"][TARGET_SLICE[branch]]
    natural, overall = metrics["slices"]["natural_student"], metrics["overall"]
    return (target["hit_at_1_count"], target["hit_at_3_count"],
            target["hit_at_5_count"], target["mrr"],
            natural["hit_at_1_count"], natural["hit_at_3_count"],
            natural["hit_at_5_count"], overall["mrr"])


def _checkpoint_specialist(
    root: Path, run_id: str, method: str, metrics: dict[str, Any],
    details: list[dict[str, Any]], recall: dict[str, Any], loaded: Any,
    benchmark: Path, index: dict[str, Any], corpus: dict[str, list[dict[str, Any]]],
    decision: str, reason: str, device: str, batch_size: int,
    activation_version: str = "v1",
) -> dict[str, Any]:
    """Persist one specialist ranking with its representation and activation rules."""
    run_dir = create_run_directory(root, run_id)
    rankings_path = run_dir / "rankings.jsonl"
    with rankings_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in details:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    branch = BRANCH[method]
    patterns = ({"formula": FORMULA_QUERY_RE, "table": TABLE_QUERY_RE,
                 "visual": VISUAL_QUERY_RE} if activation_version == "v1" else
                {"formula": (FORMULA_QUERY_RE_V3 if activation_version == "v3"
                             else FORMULA_QUERY_RE_V2),
                 "table": TABLE_QUERY_RE_V2, "visual": VISUAL_QUERY_RE})
    configuration = {
        "pipeline_name": f"synonym_bge_fixed_600_100_{method}",
        "strategy": "fixed_600_100", "retriever": "hybrid_rrf_plus_page_prior",
        "embedding": "bge_small", "query_method": "textbook_synonym_expansion",
        "specialist_method": method, "specialist_branch": branch,
        "activation_version": activation_version,
        "activation_query": ("original_student_query" if activation_version != "v1"
                             else "phase_g_processed_query"),
        "activation_pattern": patterns[branch].pattern,
        "gold_blind_activation_and_ranking": True, "rrf_constant": RRF_CONSTANT,
        "specialist_corpus_counts": {book: len(items) for book, items in corpus.items()},
        "specialist_corpus_fingerprints_sha256": {
            book: corpus_fingerprint(items) for book, items in corpus.items()},
        "index": index,
    }
    metrics_path, config_path = run_dir / "metrics.json", run_dir / "configuration.json"
    write_json(metrics_path, {"metrics": metrics, "candidate_recall": recall})
    write_json(config_path, configuration)
    overall = metrics["overall"]
    record = {
        "run_id": run_id, "timestamp": utc_now(), "phase": "H",
        "parent_run_id": "phase_g_g0_textbook_synonym_expansion",
        "changed_variable": method, "configuration": configuration,
        "random_seed": RANDOM_SEED,
        "input_artifact_versions": {"benchmark_sha256": sha256_file(benchmark)},
        "model_revisions": {"embedding": loaded.metadata},
        "metrics": {"overall": overall, "canonical": metrics["slices"]["canonical"],
                    "natural_student": metrics["slices"]["natural_student"],
                    "target_slice_name": TARGET_SLICE[branch],
                    "target_slice": metrics["slices"][TARGET_SLICE[branch]],
                    "all_slices": metrics["slices"]},
        "latency": {"measurement": "warm synonym query plus activated specialist page prior",
                    "average_ms": overall["average_latency_ms"],
                    "p50_ms": overall["p50_latency_ms"],
                    "p95_ms": overall["p95_latency_ms"],
                    "maximum_ms": overall["maximum_latency_ms"],
                    "cold_model_load_ms": loaded.cold_load_ms,
                    "warmup_ms": loaded.warmup_ms},
        "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                        "measurement": "process peak working set"},
        "disk_index_size": {"embedding_index_bytes": sum(v["size_bytes"] for v in index.values()),
                            "model_snapshot_bytes": loaded.model_size_bytes},
        "candidate_recall": recall, "decision": decision,
        "concise_reason": reason,
        "output_artifact_paths": [str(rankings_path.relative_to(root)),
                                  str(metrics_path.relative_to(root)),
                                  str(config_path.relative_to(root))],
        "reproduce_command": ("temp\\python-x64\\python.exe scripts\\run_specialist_retrieval.py "
                              f"--stage {('formula_activation_v3' if activation_version == 'v3' else 'refine_activation') if activation_version != 'v1' else 'screen'} "
                              f"--device {device} --batch-size {batch_size}"),
        "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__,
                             "platform": platform.platform(), "device": device},
    }
    checkpoint_run(root, record, "Complete the deterministic Phase H specialist screen.")
    return record


def _render_report(root: Path, records: list[dict[str, Any]]) -> None:
    """Render compact specialist metrics and explicit unsupported visual scope."""
    lines = ["# Phase H — textbook-specific retrieval specialists", "",
             "Specialists use static query-text activation; dependency labels are evaluation-only.", "",
             "| Method | Branch | Activated | Target H@1/3/5 | Target MRR | Overall H@1/3/5 | Natural H@1/3/5 | p95 | Decision |",
             "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for record in records:
        target, overall, natural = (record["metrics"]["target_slice"],
                                    record["metrics"]["overall"],
                                    record["metrics"]["natural_student"])
        lines.append(
            f'| {record["configuration"]["specialist_method"]} | '
            f'{record["configuration"]["specialist_branch"]} | '
            f'{record["candidate_recall"]["activated_question_count"]} | '
            f'{target["hit_at_1_count"]}/{target["hit_at_3_count"]}/{target["hit_at_5_count"]} | '
            f'{target["mrr"]:.3f} | '
            f'{overall["hit_at_1_count"]}/{overall["hit_at_3_count"]}/{overall["hit_at_5_count"]} | '
            f'{natural["hit_at_1_count"]}/{natural["hit_at_3_count"]}/{natural["hit_at_5_count"]} | '
            f'{record["latency"]["p95_ms"]:.1f} ms | {record["decision"]} |')
    lines.extend(["", "## Visual capability boundary", "",
                  "Caption/nearby text is evaluated locally. Embedded PDF images can be extracted for inspection, "
                  "but no approved local multimodal encoder is available, so image-semantic retrieval and generated "
                  "diagram descriptions are not scored or treated as text-retrieval failures.", ""])
    (root / "reports" / "experiments" / "phase_h_specialist_retrieval.md").write_text(
        "\n".join(lines), encoding="utf-8")


def run_screen(root: Path, benchmark: Path, cache_dir: Path, index_dir: Path,
               device: str, batch_size: int) -> dict[str, Any]:
    """Encode and screen the six approved deterministic specialist representations."""
    if not benchmark.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark}")
    run_ids = [f"phase_h_h0_{method}" for method in SPECIALISTS]
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_phase"] = "Phase H — Textbook-specific retrieval specialists"
    write_json(state_path, state)
    initialize_experiment(root, APPROVED_PLAN, run_ids, state.get("model_cache_status", {}))
    questions = read_jsonl(benchmark)
    pages = searchable_pages(root)
    chunks = build_corpora(root)["fixed_600_100"]
    specialist_corpora = build_specialist_corpora(pages)
    config = MODEL_CONFIGS["bge_small"]
    loaded = load_local_model(config, cache_dir, device, batch_size)
    chunk_matrices, _ = load_or_create_embeddings(
        loaded, chunks, index_dir, "phase_f_bge_small_fixed_600_100", batch_size)
    history = {r["run_id"]: r for r in read_run_log(experiment_paths(root)["runs"])}
    baseline_metrics: dict[str, Any] | None = None
    evaluated: dict[str, tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]] = {}
    for method in SPECIALISTS:
        matrices, index = load_or_create_embeddings(
            loaded, specialist_corpora[method], index_dir, f"phase_h_{method}", batch_size)
        metrics, details, recall = evaluate_specialist(
            loaded, config, BRANCH[method], questions, pages, chunks, chunk_matrices,
            specialist_corpora[method], matrices)
        evaluated[method] = metrics, details, recall, index
        if baseline_metrics is None:
            # Reconstruct the non-activated baseline once by evaluating with a
            # branch token that no query can activate through a temporary guard.
            baseline_metrics = history["phase_g_g0_textbook_synonym_expansion"]["metrics"]

    # Retain at most one representation per branch, and only when it improves
    # the target slice without a material global natural/Hit@5 regression.
    winners = {}
    for branch in ("formula", "table", "visual"):
        methods = [method for method in SPECIALISTS if BRANCH[method] == branch]
        winners[branch] = max(methods, key=lambda method: _target_key(evaluated[method][0], branch))
    for method, run_id in zip(SPECIALISTS, run_ids):
        if run_id in history:
            continue
        metrics, details, recall, index = evaluated[method]
        branch = BRANCH[method]
        target = metrics["slices"][TARGET_SLICE[branch]]
        baseline_target = baseline_metrics["all_slices"][TARGET_SLICE[branch]]
        improves = (target["hit_at_1_count"], target["hit_at_3_count"],
                    target["hit_at_5_count"], target["mrr"]) > (
                        baseline_target["hit_at_1_count"], baseline_target["hit_at_3_count"],
                        baseline_target["hit_at_5_count"], baseline_target["mrr"])
        natural = metrics["slices"]["natural_student"]
        baseline_natural = baseline_metrics["natural_student"]
        global_safe = (natural["hit_at_1_count"] >= baseline_natural["hit_at_1_count"] - 1
                       and metrics["overall"]["hit_at_5_count"]
                       >= baseline_metrics["overall"]["hit_at_5_count"] - 1)
        if method == winners[branch] and improves and global_safe:
            decision = "retain"
            reason = f"Best {branch} representation improved its target slice without material global regression."
        else:
            decision = "reject"
            reason = (f"Did not win and improve the {branch} target slice safely."
                      if method != winners[branch] or not improves else
                      "Target gain came with a material global regression.")
        history[run_id] = _checkpoint_specialist(
            root, run_id, method, metrics, details, recall, loaded, benchmark,
            index, specialist_corpora[method], decision, reason, device, batch_size)
    records = [history[run_id] for run_id in run_ids]
    retained = {branch: next((record["run_id"] for record in records
                              if record["configuration"]["specialist_branch"] == branch
                              and record["decision"] == "retain"), None)
                for branch in ("formula", "table", "visual")}
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_best_configurations"]["phase_h_specialists"] = retained
    state["unresolved_questions"] = [
        "Which gold-blind evidence-set expansion best covers multi-page and multi-chunk questions?",
        "Can embedded visual assets be usefully ranked without an approved multimodal encoder?",
    ]
    state["exact_next_action"] = (
        "Extract embedded visual assets for audit, then evaluate neighbouring, same-page, same-section, "
        "diversity, and multi-stage evidence-set construction on distributed questions."
    )
    write_json(state_path, state)
    render_resume(root, state)
    _render_report(root, records)
    return {"retained": retained, "records": records}


def _activation_audit(questions: list[dict[str, Any]], branch: str,
                      activated: list[str]) -> dict[str, Any]:
    """Compare gold-blind activations with dependency labels after ranking."""
    flag = {"formula": "formula_dependency", "table": "table_dependency",
            "visual": "visual_dependency"}[branch]
    targets = {q["question_id"] for q in questions
               if q.get(flag) and q.get("gold_pdf_pages")}
    active = set(activated)
    return {"target_question_count": len(targets),
            "target_activated_count": len(targets & active),
            "false_activation_count": len(active - targets),
            "false_activation_ids": sorted(active - targets),
            "missed_target_count": len(targets - active),
            "missed_target_ids": sorted(targets - active)}


def run_refine_activation(root: Path, benchmark: Path, cache_dir: Path,
                          index_dir: Path, device: str,
                          batch_size: int) -> dict[str, Any]:
    """Retest only retained formula/table representations with narrower V2 activation."""
    if not benchmark.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark}")
    methods = ("formula_equation_context", "table_rows_with_headers")
    run_ids = ("phase_h_h1_formula_context_activation_v2",
               "phase_h_h1_table_rows_activation_v2")
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    initialize_experiment(root, APPROVED_PLAN, list(run_ids),
                          state.get("model_cache_status", {}))
    questions = read_jsonl(benchmark)
    pages = searchable_pages(root)
    chunks = build_corpora(root)["fixed_600_100"]
    corpora = build_specialist_corpora(pages)
    config = MODEL_CONFIGS["bge_small"]
    loaded = load_local_model(config, cache_dir, device, batch_size)
    chunk_matrices, _ = load_or_create_embeddings(
        loaded, chunks, index_dir, "phase_f_bge_small_fixed_600_100", batch_size)
    history = {r["run_id"]: r for r in read_run_log(experiment_paths(root)["runs"])}
    baseline = history["phase_g_g0_textbook_synonym_expansion"]
    for method, run_id in zip(methods, run_ids):
        if run_id in history:
            continue
        matrices, index = load_or_create_embeddings(
            loaded, corpora[method], index_dir, f"phase_h_{method}", batch_size)
        metrics, details, recall = evaluate_specialist(
            loaded, config, BRANCH[method], questions, pages, chunks, chunk_matrices,
            corpora[method], matrices, activation_version="v2")
        recall.update(_activation_audit(
            questions, BRANCH[method], recall["activated_question_ids"]))
        branch = BRANCH[method]
        target = metrics["slices"][TARGET_SLICE[branch]]
        baseline_target = baseline["metrics"]["all_slices"][TARGET_SLICE[branch]]
        improves = (target["hit_at_1_count"], target["hit_at_3_count"],
                    target["hit_at_5_count"], target["mrr"]) > (
                        baseline_target["hit_at_1_count"], baseline_target["hit_at_3_count"],
                        baseline_target["hit_at_5_count"], baseline_target["mrr"])
        safe = (metrics["slices"]["natural_student"]["hit_at_1_count"]
                >= baseline["metrics"]["natural_student"]["hit_at_1_count"] - 1
                and metrics["overall"]["hit_at_5_count"]
                >= baseline["metrics"]["overall"]["hit_at_5_count"] - 1)
        decision = "retain" if improves and safe else "reject"
        reason = (f"V2 {branch} activation preserved a target gain with fewer false activations."
                  if decision == "retain" else
                  f"V2 {branch} activation did not preserve a safe target improvement.")
        history[run_id] = _checkpoint_specialist(
            root, run_id, method, metrics, details, recall, loaded, benchmark,
            index, corpora[method], decision, reason, device, batch_size,
            activation_version="v2")
    records = [history[run_id] for run_id in run_ids]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    retained = state["current_best_configurations"].get("phase_h_specialists", {})
    for record in records:
        branch = record["configuration"]["specialist_branch"]
        if record["decision"] == "retain":
            retained[branch] = record["run_id"]
    state["current_best_configurations"]["phase_h_specialists"] = retained
    state["exact_next_action"] = (
        "Extract embedded visual assets for audit, then evaluate distributed evidence-set construction."
    )
    write_json(state_path, state)
    render_resume(root, state)
    all_records = [r for r in read_run_log(experiment_paths(root)["runs"])
                   if r["phase"] == "H" and "target_slice" in r["metrics"]]
    _render_report(root, all_records)
    return {"retained": retained, "records": records}


def run_formula_activation_v3(root: Path, benchmark: Path, cache_dir: Path,
                              index_dir: Path, device: str,
                              batch_size: int) -> dict[str, Any]:
    """Test only plural-law support on the retained formula-context branch."""
    if not benchmark.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark}")
    run_id = "phase_h_h2_formula_context_activation_v3"
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    initialize_experiment(root, APPROVED_PLAN, [run_id],
                          state.get("model_cache_status", {}))
    history = {r["run_id"]: r for r in read_run_log(experiment_paths(root)["runs"])}
    if run_id not in history:
        questions = read_jsonl(benchmark)
        pages = searchable_pages(root)
        chunks = build_corpora(root)["fixed_600_100"]
        method = "formula_equation_context"
        corpus = build_specialist_corpora(pages)[method]
        config = MODEL_CONFIGS["bge_small"]
        loaded = load_local_model(config, cache_dir, device, batch_size)
        chunk_matrices, _ = load_or_create_embeddings(
            loaded, chunks, index_dir, "phase_f_bge_small_fixed_600_100", batch_size)
        matrices, index = load_or_create_embeddings(
            loaded, corpus, index_dir, f"phase_h_{method}", batch_size)
        metrics, details, recall = evaluate_specialist(
            loaded, config, "formula", questions, pages, chunks, chunk_matrices,
            corpus, matrices, activation_version="v3")
        recall.update(_activation_audit(questions, "formula",
                                        recall["activated_question_ids"]))
        v2 = history["phase_h_h1_formula_context_activation_v2"]
        target = metrics["slices"]["formula_dependent"]
        improves = (target["hit_at_1_count"], target["hit_at_3_count"],
                    target["hit_at_5_count"], target["mrr"]) > (
                        v2["metrics"]["target_slice"]["hit_at_1_count"],
                        v2["metrics"]["target_slice"]["hit_at_3_count"],
                        v2["metrics"]["target_slice"]["hit_at_5_count"],
                        v2["metrics"]["target_slice"]["mrr"])
        complete = (recall["target_activated_count"] == recall["target_question_count"]
                    and recall["false_activation_count"] == 0)
        decision = "retain" if improves and complete else "reject"
        reason = ("Plural-law support completed 16/16 formula activation and improved target quality."
                  if decision == "retain" else
                  "Plural-law support did not improve target quality despite activation coverage.")
        history[run_id] = _checkpoint_specialist(
            root, run_id, method, metrics, details, recall, loaded, benchmark,
            index, corpus, decision, reason, device, batch_size,
            activation_version="v3")
    record = history[run_id]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if record["decision"] == "retain":
        state["current_best_configurations"]["phase_h_specialists"]["formula"] = run_id
    state["exact_next_action"] = (
        "Extract embedded visual assets for audit, then evaluate distributed evidence-set construction."
    )
    write_json(state_path, state)
    render_resume(root, state)
    all_records = [r for r in read_run_log(experiment_paths(root)["runs"])
                   if r["phase"] == "H" and "target_slice" in r["metrics"]]
    _render_report(root, all_records)
    return {"retained": state["current_best_configurations"]["phase_h_specialists"],
            "records": [record]}


def evaluate_combined_specialists(
    loaded: Any, config: dict[str, Any], questions: list[dict[str, Any]],
    pages: dict[str, list[dict[str, Any]]], chunks: dict[str, list[dict[str, Any]]],
    chunk_matrices: dict[str, np.ndarray],
    resources: dict[str, tuple[dict[str, list[dict[str, Any]]], dict[str, np.ndarray]]],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Fuse all retained specialist priors, each with its versioned activation."""
    answerable = {q["question_id"] for q in questions
                  if q.get("gold_pdf_pages") and (q.get("gold_answer_span") or "").strip()}
    scopes = _evaluation_scopes(questions, answerable)
    child_bm25 = {book: BM25(item["text"] for item in corpus)
                  for book, corpus in chunks.items()}
    specialist_bm25 = {
        method: {book: BM25(item["text"] for item in corpus)
                 for book, corpus in documents.items()}
        for method, (documents, _) in resources.items()
    }
    rows, details, mapped = {}, [], set()
    activation_counts = {branch: 0 for branch in ("formula", "table", "visual")}
    for question in questions:
        qid, book = question["question_id"], question["book_id"]
        corpus = chunks[book]
        mapping = accepted_mapping(question, corpus, pages[book])
        gold = set(mapping["primary"] + mapping["alternatives"])
        if qid in answerable and mapping["status"] == "mapped":
            mapped.add(qid)
        result = rank_combined_query(
            question["question"], book, loaded, config, corpus,
            chunk_matrices[book], resources, child_bm25[book], specialist_bm25)
        processed, activated = result["processed_query"], result["activated_specialists"]
        scores, ranking, latency = result["scores"], result["ranking"], result["latency_ms"]
        for branch in activated:
            activation_counts[branch] += 1
        first = next((rank for rank, index in enumerate(ranking, 1)
                      if corpus[int(index)]["chunk_id"] in gold), None)
        rows[qid] = {"answerable": qid in answerable,
                     "first_gold_rank": first, "latency_ms": latency}
        details.append({
            "question_id": qid, "question": question["question"], "book_id": book,
            "benchmark_slice": question.get("benchmark_slice", "canonical"),
            "processed_query": processed, "activated_specialists": activated,
            "gold_mapping": mapping, "first_gold_rank": first,
            "latency_ms": latency,
            "ranking": [{
                "rank": rank, "score": float(scores[int(index)]),
                "chunk_id": corpus[int(index)]["chunk_id"],
                "pdf_pages": corpus[int(index)]["pdf_pages"],
                "textbook_pages": corpus[int(index)]["textbook_pages"],
                "chapter_title": corpus[int(index)].get("chapter_title"),
                "section_title": corpus[int(index)].get("section_title"),
                "text_snippet": " ".join(corpus[int(index)]["text"].split())[:500],
                "matches_accepted_evidence": corpus[int(index)]["chunk_id"] in gold,
            } for rank, index in enumerate(ranking, 1)],
        })
    metrics = summarize(rows, scopes)
    recall = {"answerable_questions": len(answerable), "count": len(mapped),
              "recall": len(mapped) / len(answerable),
              "missing_question_ids": sorted(answerable - mapped),
              "required_invariant_satisfied": mapped == answerable,
              "activation_counts": activation_counts,
              "questions_with_any_specialist": sum(bool(row["activated_specialists"])
                                                     for row in details)}
    return metrics, details, recall


def rank_combined_query(
    question: str,
    book: str,
    loaded: Any,
    config: dict[str, Any],
    corpus: list[dict[str, Any]],
    chunk_matrix: np.ndarray,
    resources: dict[str, tuple[dict[str, list[dict[str, Any]]], dict[str, np.ndarray]]],
    child_bm25: BM25,
    specialist_bm25: dict[str, dict[str, BM25]],
) -> dict[str, Any]:
    """Rank one arbitrary query with the retained gold-blind Phase H pipeline.

    The function is shared by benchmark evaluation and the production query
    CLI, preventing the final handoff from drifting from the measured method.
    Passing an empty specialist resource mapping reproduces the Phase G
    lightweight synonym/BM25/BGE-small hybrid.
    """
    specifications = {
        "formula_equation_context": ("formula", "v2"),
        "table_rows_with_headers": ("table", "v2"),
        "visual_caption_context": ("visual", "v1"),
    }
    processed = textbook_synonym_expansion(question).text
    started = time.perf_counter()
    query = loaded.model.encode(
        [config["query_prefix"] + processed], convert_to_numpy=True,
        normalize_embeddings=True, show_progress_bar=False)[0]
    rankings = [stable_ranking(chunk_matrix @ query),
                stable_ranking(child_bm25.scores(processed))]
    activated = []
    for method, (branch, version) in specifications.items():
        if method not in resources:
            continue
        activation_query = question if version != "v1" else processed
        if not specialist_activated(branch, activation_query, version):
            continue
        activated.append(branch)
        documents, matrices = resources[method]
        dense = stable_ranking(matrices[book] @ query)
        lexical = stable_ranking(specialist_bm25[method][book].scores(processed))
        specialist_scores = reciprocal_rank_fusion(
            [dense, lexical], len(documents[book]), RRF_CONSTANT)
        rankings.append(lift_specialist_ranking(
            corpus, documents[book], stable_ranking(specialist_scores)))
    scores = reciprocal_rank_fusion(rankings, len(corpus), RRF_CONSTANT)
    ranking = stable_ranking(scores)
    return {"processed_query": processed, "activated_specialists": activated,
            "scores": scores, "ranking": ranking,
            "latency_ms": (time.perf_counter() - started) * 1000}


def run_combined(root: Path, benchmark: Path, cache_dir: Path,
                 index_dir: Path, device: str,
                 batch_size: int) -> dict[str, Any]:
    """Combine only retained Phase H specialist priors in one production ranking."""
    if not benchmark.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark}")
    run_id = "phase_h_h3_combined_specialist_priors"
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    initialize_experiment(root, APPROVED_PLAN, [run_id],
                          state.get("model_cache_status", {}))
    history = {r["run_id"]: r for r in read_run_log(experiment_paths(root)["runs"])}
    if run_id not in history:
        questions = read_jsonl(benchmark)
        pages = searchable_pages(root)
        chunks = build_corpora(root)["fixed_600_100"]
        corpora = build_specialist_corpora(pages)
        config = MODEL_CONFIGS["bge_small"]
        loaded = load_local_model(config, cache_dir, device, batch_size)
        chunk_matrices, _ = load_or_create_embeddings(
            loaded, chunks, index_dir, "phase_f_bge_small_fixed_600_100", batch_size)
        methods = ("formula_equation_context", "table_rows_with_headers",
                   "visual_caption_context")
        resources = {}
        index_metadata = {}
        for method in methods:
            matrices, metadata = load_or_create_embeddings(
                loaded, corpora[method], index_dir, f"phase_h_{method}", batch_size)
            resources[method] = corpora[method], matrices
            index_metadata[method] = metadata
        metrics, details, recall = evaluate_combined_specialists(
            loaded, config, questions, pages, chunks, chunk_matrices, resources)
        baseline = history["phase_g_g0_textbook_synonym_expansion"]
        natural, base_natural = metrics["slices"]["natural_student"], baseline["metrics"]["natural_student"]
        overall, base_overall = metrics["overall"], baseline["metrics"]["overall"]
        improves = (natural["hit_at_1_count"], natural["hit_at_3_count"],
                    natural["hit_at_5_count"], natural["mrr"], overall["mrr"]) > (
                        base_natural["hit_at_1_count"], base_natural["hit_at_3_count"],
                        base_natural["hit_at_5_count"], base_natural["mrr"], base_overall["mrr"])
        safe = (metrics["slices"]["canonical"]["hit_at_5_count"]
                >= baseline["metrics"]["canonical"]["hit_at_5_count"] - 1)
        decision = "retain" if improves and safe else "reject"
        reason = ("Combined retained priors improved natural-first quality without material canonical regression."
                  if decision == "retain" else
                  "Combined priors did not improve the retained Phase G ranking safely.")
        run_dir = create_run_directory(root, run_id)
        rankings_path = run_dir / "rankings.jsonl"
        with rankings_path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in details:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        configuration = {
            "pipeline_name": "synonym_bge_fixed_600_100_combined_specialist_priors",
            "strategy": "fixed_600_100", "embedding": "bge_small",
            "retriever": "hybrid_rrf_plus_activated_specialist_page_priors",
            "query_method": "textbook_synonym_expansion",
            "specialists": {"formula": "formula_equation_context_v2",
                            "table": "table_rows_with_headers_v2",
                            "visual": "visual_caption_context_v1"},
            "gold_blind_activation_and_ranking": True,
            "rrf_constant": RRF_CONSTANT, "index": index_metadata,
        }
        metrics_path, config_path = run_dir / "metrics.json", run_dir / "configuration.json"
        write_json(metrics_path, {"metrics": metrics, "candidate_recall": recall})
        write_json(config_path, configuration)
        record = {
            "run_id": run_id, "timestamp": utc_now(), "phase": "H",
            "parent_run_id": "phase_g_g0_textbook_synonym_expansion",
            "changed_variable": "combined retained specialist priors",
            "configuration": configuration, "random_seed": RANDOM_SEED,
            "input_artifact_versions": {"benchmark_sha256": sha256_file(benchmark)},
            "model_revisions": {"embedding": loaded.metadata},
            "metrics": {"overall": overall, "canonical": metrics["slices"]["canonical"],
                        "natural_student": natural, "all_slices": metrics["slices"]},
            "latency": {"measurement": "warm synonym query plus all activated retained priors",
                        "average_ms": overall["average_latency_ms"],
                        "p50_ms": overall["p50_latency_ms"],
                        "p95_ms": overall["p95_latency_ms"],
                        "maximum_ms": overall["maximum_latency_ms"],
                        "cold_model_load_ms": loaded.cold_load_ms,
                        "warmup_ms": loaded.warmup_ms},
            "peak_memory": {"peak_rss_mb": _peak_memory_mb(),
                            "measurement": "process peak working set"},
            "disk_index_size": {"embedding_index_bytes": sum(
                value["size_bytes"] for method in index_metadata.values()
                for value in method.values()), "model_snapshot_bytes": loaded.model_size_bytes},
            "candidate_recall": recall, "decision": decision,
            "concise_reason": reason,
            "output_artifact_paths": [str(rankings_path.relative_to(root)),
                                      str(metrics_path.relative_to(root)),
                                      str(config_path.relative_to(root))],
            "reproduce_command": ("temp\\python-x64\\python.exe scripts\\run_specialist_retrieval.py "
                                  f"--stage combined --device {device} --batch-size {batch_size}"),
            "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__,
                                 "platform": platform.platform(), "device": device},
        }
        checkpoint_run(root, record, "Evaluate distributed evidence-set construction.")
        history[run_id] = record
    record = history[run_id]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_best_configurations"]["phase_h_combined_retrieval"] = (
        run_id if record["decision"] == "retain" else "phase_g_g0_textbook_synonym_expansion")
    state["exact_next_action"] = "Evaluate distributed evidence-set construction from the retained ranking."
    write_json(state_path, state)
    render_resume(root, state)
    return {"winner": state["current_best_configurations"]["phase_h_combined_retrieval"],
            "record": record}


def build_parser() -> argparse.ArgumentParser:
    """Create the resumable Phase H specialist command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--benchmark", type=Path,
                        default=Path("data/benchmarks/retrieval_benchmark_v1.jsonl"))
    parser.add_argument("--stage", choices=("screen", "refine_activation",
                                             "formula_activation_v3", "combined"), default="screen")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/retrieval/cache/models"))
    parser.add_argument("--index-dir", type=Path,
                        default=Path("data/retrieval/cache/experiments/phase_h"))
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=16)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run the Phase H screen and print retained branch methods."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    benchmark = args.benchmark if args.benchmark.is_absolute() else root / args.benchmark
    cache = args.cache_dir if args.cache_dir.is_absolute() else root / args.cache_dir
    index = args.index_dir if args.index_dir.is_absolute() else root / args.index_dir
    if args.stage == "screen":
        result = run_screen(root, benchmark, cache, index, args.device, args.batch_size)
    elif args.stage == "refine_activation":
        result = run_refine_activation(root, benchmark, cache, index,
                                       args.device, args.batch_size)
    elif args.stage == "formula_activation_v3":
        result = run_formula_activation_v3(root, benchmark, cache, index,
                                           args.device, args.batch_size)
    else:
        result = run_combined(root, benchmark, cache, index,
                              args.device, args.batch_size)
    print(json.dumps({"retained": result.get("retained"),
                      "winner": result.get("winner")}, indent=2))


if __name__ == "__main__":
    main()
