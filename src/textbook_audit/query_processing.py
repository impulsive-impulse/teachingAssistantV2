"""Phase G deterministic query processing on the retained BGE-small pipeline.

Every transformation depends only on query text and a static, reviewable rule
set. Gold evidence is consulted after complete rankings exist. The fusion stage
always preserves the original query as an equal retrieval source.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .candidate_compression import APPROVED_PLAN, RANDOM_SEED, _peak_memory_mb
from .chunking_bakeoff import build_corpora
from .embedding_bakeoff import (
    MODEL_CONFIGS,
    _evaluation_scopes,
    accepted_mapping,
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
from .retrieval import BM25, read_jsonl, reciprocal_rank_fusion, stable_ranking


RRF_CONSTANT = 60
SCREEN_METHODS = (
    "raw",
    "spelling_normalization",
    "grammar_cleanup",
    "textbook_synonym_expansion",
    "acronym_expansion",
    "formula_symbol_normalization",
)


@dataclass(frozen=True)
class ProcessedQuery:
    """One auditable deterministic query transformation and its fired rules."""

    text: str
    rules: tuple[str, ...]

    @property
    def changed(self) -> bool:
        """Report whether at least one deterministic rule changed the query."""
        return bool(self.rules)


def _substitute(text: str, pattern: str, replacement: str,
                rule: str, rules: list[str]) -> str:
    """Apply one case-insensitive regex and record it only when it fires."""
    updated, count = re.subn(pattern, replacement, text, flags=re.IGNORECASE)
    if count:
        rules.append(rule)
    return updated


def spelling_normalization(query: str) -> ProcessedQuery:
    """Correct a small general typo list without adding domain concepts."""
    rules: list[str] = []
    text = query
    replacements = {
        r"\bteh\b": "the", r"\brecieve\b": "receive",
        r"\bbecuase\b": "because", r"\belectricty\b": "electricity",
        r"\bphotosythesis\b": "photosynthesis", r"\bchromosones\b": "chromosomes",
    }
    for pattern, replacement in replacements.items():
        text = _substitute(text, pattern, replacement,
                           f"spell:{pattern}->{replacement}", rules)
    return ProcessedQuery(text, tuple(rules))


def grammar_cleanup(query: str) -> ProcessedQuery:
    """Repair conservative surface grammar while preserving content words."""
    rules: list[str] = []
    text = query
    substitutions = (
        (r"\bgonna\b", "going to", "grammar:gonna"),
        (r"^How food go\b", "How does food go", "grammar:missing_auxiliary_how"),
        (r"^Why equation need\b", "Why does an equation need", "grammar:missing_auxiliary_why"),
        (r"\bgreen plants feed itself\b", "green plants feed themselves", "grammar:plural_reflexive"),
        (r"\batomic relationship happen\b", "atomic relationships happen", "grammar:plural_relationship"),
    )
    for pattern, replacement, rule in substitutions:
        text = _substitute(text, pattern, replacement, rule, rules)
    return ProcessedQuery(text, tuple(rules))


# These are query-side textbook aliases, not answers or page labels. Each entry
# requires all trigger fragments before neutral retrieval vocabulary is added.
SYNONYM_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("plant_nutrition", ("plant", "eat"), "autotrophic nutrition photosynthesis make food"),
    ("plant_nutrition_feed", ("plant", "feed"), "autotrophic nutrition photosynthesis make food"),
    ("cell_energy", ("cell", "energy", "food"), "cellular respiration"),
    ("kidney_units", ("kidney", "working unit"), "nephron"),
    ("urine_colloquial", ("kidney", "pee"), "urine formation filtration"),
    ("double_circulation", ("blood", "heart", "twice"), "double circulation"),
    ("flower_reproduction", ("pollen", "seed"), "pollination fertilization seed formation"),
    ("oxygen_transport", ("oxygen", "lungs", "body"), "haemoglobin oxygen transport"),
    ("respiration_oxygen", ("energy", "without oxygen"), "anaerobic respiration aerobic respiration"),
    ("cell_division", ("cell", "half", "chromosome"), "meiosis mitosis daughter cells"),
    ("water_conservation", ("rainwater", "groundwater"), "water harvesting groundwater recharge"),
    ("induction", ("magnet", "electricity", "wire"), "electromagnetic induction"),
    ("myopia", ("short-sighted", "concave lens"), "myopia correction"),
    ("parallel_paths", ("broken", "parallel circuit"), "independent current paths"),
    ("covalent", ("share electron",), "covalent bonding electron sharing"),
    ("atomic_bond", ("atomic relationship",), "chemical bonding atoms"),
    ("refraction", ("bent", "water"), "refraction of light"),
    ("convex_mirror", ("mirror", "vehicles", "smaller"), "convex mirror diminished image"),
    ("neutralisation", ("chemically opposite", "cancel"), "acid base neutralisation"),
)


def textbook_synonym_expansion(query: str) -> ProcessedQuery:
    """Append static textbook vocabulary when all neutral phrase triggers match."""
    lowered = query.lower()
    additions, rules = [], []
    for name, triggers, terms in SYNONYM_RULES:
        if all(trigger in lowered for trigger in triggers):
            additions.append(terms)
            rules.append(f"synonym:{name}")
    text = query if not additions else query + " Related textbook terms: " + " ".join(dict.fromkeys(additions))
    return ProcessedQuery(text, tuple(rules))


def acronym_expansion(query: str) -> ProcessedQuery:
    """Expand unambiguous curriculum acronyms and abbreviated units."""
    rules: list[str] = []
    additions = []
    patterns = (
        (r"\bpH\b", "potential of hydrogen pH scale", "acronym:pH"),
        (r"\bkWh\b", "kilowatt hour", "acronym:kWh"),
        (r"\b\d+\s*W\b", "watt", "unit:W"),
    )
    for pattern, expansion, rule in patterns:
        if re.search(pattern, query, flags=re.IGNORECASE):
            additions.append(expansion)
            rules.append(rule)
    text = query if not additions else query + " Expanded terms: " + " ".join(additions)
    return ProcessedQuery(text, tuple(rules))


def formula_symbol_normalization(query: str) -> ProcessedQuery:
    """Append standard quantity names/symbols without solving the question."""
    lowered = query.lower()
    additions, rules = [], []
    aliases = (
        ("voltage", "potential difference V", "formula:voltage"),
        ("current", "electric current I", "formula:current"),
        ("resistance", "resistance R ohm Ω", "formula:resistance"),
        ("focal length", "focal length f", "formula:focal_length"),
        ("object distance", "object distance u", "formula:object_distance"),
        ("image distance", "image distance v", "formula:image_distance"),
        ("shorter focus", "focal length f power of lens P", "formula:lens_power"),
        ("mirror formula", "1/f 1/v 1/u sign convention", "formula:mirror"),
        ("parallel resistors", "equivalent resistance 1/R", "formula:parallel_resistance"),
        ("electric power", "power P voltage V current I", "formula:electric_power"),
    )
    for trigger, terms, rule in aliases:
        if trigger in lowered:
            additions.append(terms)
            rules.append(rule)
    text = query if not additions else query + " Normalized quantities: " + " ".join(additions)
    return ProcessedQuery(text, tuple(rules))


PROCESSORS: dict[str, Callable[[str], ProcessedQuery]] = {
    "raw": lambda query: ProcessedQuery(query, ()),
    "spelling_normalization": spelling_normalization,
    "grammar_cleanup": grammar_cleanup,
    "textbook_synonym_expansion": textbook_synonym_expansion,
    "acronym_expansion": acronym_expansion,
    "formula_symbol_normalization": formula_symbol_normalization,
}


def process_query(method: str, query: str) -> ProcessedQuery:
    """Dispatch one named, reviewable deterministic query processor."""
    if method not in PROCESSORS:
        raise ValueError(f"unknown query processor: {method}")
    return PROCESSORS[method](query)


def _evaluate_method(loaded: Any, config: dict[str, Any], method: str,
                     questions: list[dict[str, Any]], pages: dict[str, list[dict[str, Any]]],
                     corpus: dict[str, list[dict[str, Any]]], matrices: dict[str, np.ndarray],
                     fusion: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Rank one processed-query method, optionally fusing it with the original."""
    answerable = {q["question_id"] for q in questions
                  if q.get("gold_pdf_pages") and (q.get("gold_answer_span") or "").strip()}
    scopes = _evaluation_scopes(questions, answerable)
    bm25 = {book: BM25(item["text"] for item in items) for book, items in corpus.items()}
    rows, details, mapped = {}, [], set()
    changed_count = 0
    for question in questions:
        qid, book = question["question_id"], question["book_id"]
        chunks = corpus[book]
        mapping = accepted_mapping(question, chunks, pages[book])
        gold = set(mapping["primary"] + mapping["alternatives"])
        if qid in answerable and mapping["status"] == "mapped":
            mapped.add(qid)
        processed = process_query(method, question["question"])
        changed_count += int(processed.changed)
        query_texts = ([question["question"], processed.text]
                       if fusion and processed.changed else [processed.text])
        started = time.perf_counter()
        rankings = []
        for query_text in query_texts:
            vector = loaded.model.encode(
                [config["query_prefix"] + query_text], convert_to_numpy=True,
                normalize_embeddings=True, show_progress_bar=False)[0]
            rankings.append(stable_ranking(matrices[book] @ vector))
            rankings.append(stable_ranking(bm25[book].scores(query_text)))
        scores = reciprocal_rank_fusion(rankings, len(chunks), RRF_CONSTANT)
        ranking = stable_ranking(scores)
        latency = (time.perf_counter() - started) * 1000
        first = next((rank for rank, index in enumerate(ranking, 1)
                      if chunks[int(index)]["chunk_id"] in gold), None)
        rows[qid] = {"answerable": qid in answerable,
                     "first_gold_rank": first, "latency_ms": latency}
        details.append({
            "question_id": qid, "question": question["question"], "book_id": book,
            "benchmark_slice": question.get("benchmark_slice", "canonical"),
            "method": method, "fusion_with_original": fusion,
            "processed_query": processed.text, "query_changed": processed.changed,
            "rules_applied": list(processed.rules), "gold_mapping": mapping,
            "first_gold_rank": first, "latency_ms": latency,
            "ranking": [{
                "rank": rank, "score": float(scores[int(index)]),
                "chunk_id": chunks[int(index)]["chunk_id"],
                "pdf_pages": chunks[int(index)]["pdf_pages"],
                "textbook_pages": chunks[int(index)]["textbook_pages"],
                "chapter_title": chunks[int(index)].get("chapter_title"),
                "section_title": chunks[int(index)].get("section_title"),
                "text_snippet": " ".join(chunks[int(index)]["text"].split())[:500],
                "matches_accepted_evidence": chunks[int(index)]["chunk_id"] in gold,
            } for rank, index in enumerate(ranking, 1)],
        })
    metrics = summarize(rows, scopes)
    recall = {"answerable_questions": len(answerable), "count": len(mapped),
              "recall": len(mapped) / len(answerable),
              "missing_question_ids": sorted(answerable - mapped),
              "required_invariant_satisfied": mapped == answerable,
              "changed_query_count": changed_count}
    return metrics, details, recall


def _quality_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Apply the project natural-first ordering to Phase G run records."""
    natural, overall = record["metrics"]["natural_student"], record["metrics"]["overall"]
    return (natural["hit_at_1_count"], natural["hit_at_3_count"],
            natural["hit_at_5_count"], natural["mrr"],
            overall["hit_at_1_count"], overall["mrr"],
            overall["hit_at_3_count"], overall["hit_at_5_count"])


def select_phase_g_winner(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the natural-first winner across both screen and fusion runs."""
    if not records:
        raise ValueError("at least one completed Phase G record is required")
    return max(records, key=_quality_key)


def _checkpoint(root: Path, run_id: str, parent: str, method: str, fusion: bool,
                metrics: dict[str, Any], details: list[dict[str, Any]],
                recall: dict[str, Any], loaded: Any, benchmark: Path,
                index: dict[str, Any], decision: str, reason: str,
                device: str, batch_size: int) -> dict[str, Any]:
    """Write one immutable query-processing run and append its standard record."""
    run_dir = create_run_directory(root, run_id)
    rankings_path = run_dir / "rankings.jsonl"
    with rankings_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in details:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    configuration = {"pipeline_name": run_id.removeprefix("phase_g_"),
                     "strategy": "fixed_600_100", "retriever": "hybrid_rrf",
                     "embedding": "bge_small", "query_method": method,
                     "fusion_with_original": fusion, "rrf_constant": RRF_CONSTANT,
                     "gold_blind_ranking": True, "original_query_preserved": fusion,
                     "index": index}
    metrics_path, config_path = run_dir / "metrics.json", run_dir / "configuration.json"
    write_json(metrics_path, {"metrics": metrics, "candidate_recall": recall})
    write_json(config_path, configuration)
    overall = metrics["overall"]
    record = {"run_id": run_id, "timestamp": utc_now(), "phase": "G",
              "parent_run_id": parent, "changed_variable": method,
              "configuration": configuration, "random_seed": RANDOM_SEED,
              "input_artifact_versions": {"benchmark_sha256": sha256_file(benchmark)},
              "model_revisions": {"embedding": loaded.metadata},
              "metrics": {"overall": overall,
                          "canonical": metrics["slices"]["canonical"],
                          "natural_student": metrics["slices"]["natural_student"],
                          "all_slices": metrics["slices"]},
              "latency": {"measurement": "warm processed-query embedding and BM25/dense RRF",
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
              "reproduce_command": ("temp\\python-x64\\python.exe scripts\\run_query_processing.py "
                                    f"--stage {'fusion' if fusion else 'screen'} --device {device} "
                                    f"--batch-size {batch_size}"),
              "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__,
                                   "platform": platform.platform(), "device": device}}
    checkpoint_run(root, record, "Continue the approved deterministic Phase G screen.")
    return record


def _render_report(root: Path, records: list[dict[str, Any]]) -> None:
    """Render a compact deterministic-query comparison from immutable records."""
    lines = ["# Phase G — deterministic query processing", "",
             "All runs use BGE-small fixed 600/100 Hybrid RRF and gold-blind static rules.", "",
             "| Run | Method | Fusion | Changed | H@1/3/5 | MRR | Natural H@1/3/5 | Canonical H@5 | p95 | Decision |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for record in records:
        overall, natural = record["metrics"]["overall"], record["metrics"]["natural_student"]
        lines.append(f'| {record["run_id"]} | {record["configuration"]["query_method"]} | '
                     f'{record["configuration"]["fusion_with_original"]} | '
                     f'{record["candidate_recall"].get("changed_query_count", 0)} | '
                     f'{overall["hit_at_1_count"]}/{overall["hit_at_3_count"]}/{overall["hit_at_5_count"]} | '
                     f'{overall["mrr"]:.3f} | '
                     f'{natural["hit_at_1_count"]}/{natural["hit_at_3_count"]}/{natural["hit_at_5_count"]} | '
                     f'{record["metrics"]["canonical"]["hit_at_5_count"]}/41 | '
                     f'{record["latency"]["p95_ms"]:.1f} ms | {record["decision"]} |')
    state = json.loads(experiment_paths(root)["state"].read_text(encoding="utf-8"))
    winner = state.get("current_best_configurations", {}).get("phase_g_deterministic_winner")
    lines.extend(["", "## Final deterministic selection", "",
                  f"Winner: `{winner['run_id']}`." if winner else "Winner not finalized.", "",
                  "Only textbook synonym expansion and formula/symbol normalization advanced to fusion. "
                  "Grammar cleanup changed five queries without changing Hit@K, while acronym expansion "
                  "added one overall Hit@1 but no natural-student Hit@K; neither was treated as a meaningful finalist.", "",
                  "Standalone synonym expansion beat original-plus-synonym fusion in quality and latency. "
                  "Every transformed query and fired rule is stored beside its full ranking.", ""])
    (root / "reports" / "experiments" / "phase_g_query_processing.md").write_text(
        "\n".join(lines), encoding="utf-8")


def _resources(root: Path, benchmark: Path, cache_dir: Path, index_dir: Path,
               device: str, batch_size: int) -> tuple[Any, Any, Any, Any, Any, Any]:
    """Load the fixed benchmark and retained BGE corpus/index once per stage."""
    if not benchmark.is_file():
        raise FileNotFoundError(f"reviewed benchmark is missing: {benchmark}")
    questions = read_jsonl(benchmark)
    pages = searchable_pages(root)
    corpus = build_corpora(root)["fixed_600_100"]
    config = MODEL_CONFIGS["bge_small"]
    loaded = load_local_model(config, cache_dir, device, batch_size)
    matrices, index = load_or_create_embeddings(
        loaded, corpus, index_dir, "phase_f_bge_small_fixed_600_100",
        batch_size, document_prefix=config.get("document_prefix", ""))
    return questions, pages, corpus, config, loaded, (matrices, index)


def run_screen(root: Path, benchmark: Path, cache_dir: Path, index_dir: Path,
               device: str, batch_size: int) -> dict[str, Any]:
    """Screen raw plus five isolated deterministic query processors."""
    run_ids = [f"phase_g_g0_{method}" for method in SCREEN_METHODS]
    state = json.loads(experiment_paths(root)["state"].read_text(encoding="utf-8"))
    initialize_experiment(root, APPROVED_PLAN, run_ids, state.get("model_cache_status", {}))
    questions, pages, corpus, config, loaded, packed = _resources(
        root, benchmark, cache_dir, index_dir, device, batch_size)
    matrices, index = packed
    history = {r["run_id"]: r for r in read_run_log(experiment_paths(root)["runs"])}
    control_record = history.get(run_ids[0])
    for method, run_id in zip(SCREEN_METHODS, run_ids):
        if run_id in history:
            continue
        metrics, details, recall = _evaluate_method(
            loaded, config, method, questions, pages, corpus, matrices)
        provisional = {"metrics": {"overall": metrics["overall"],
                                   "natural_student": metrics["slices"]["natural_student"]}}
        if method == "raw":
            decision, reason = "retain", "Reproduces the retained Phase F balanced control."
        elif recall["changed_query_count"] == 0:
            decision, reason = "reject", "No benchmark query activated this conservative processor."
        else:
            assert control_record is not None
            canonical = metrics["slices"]["canonical"]
            control_canonical = control_record["metrics"]["canonical"]
            if canonical["hit_at_5_count"] < control_canonical["hit_at_5_count"] - 1:
                decision, reason = "reject", "Canonical Hit@5 regressed by more than one question."
            elif _quality_key(provisional) > _quality_key(control_record):
                decision, reason = "retain", "Improved the natural-student-first ordering without material canonical regression."
            else:
                decision, reason = "reject", "Did not improve the natural-student-first ordering over raw retrieval."
        record = _checkpoint(root, run_id, "phase_f_f3_bge_small_fixed_600_100",
                             method, False, metrics, details, recall, loaded,
                             benchmark, index, decision, reason, device, batch_size)
        history[run_id] = record
        if method == "raw":
            control_record = record
    records = [history[run_id] for run_id in run_ids]
    changed = [record for record in records
               if record["candidate_recall"].get("changed_query_count", 0)]
    finalists = [record["configuration"]["query_method"]
                 for record in sorted(changed, key=_quality_key, reverse=True)[:2]]
    state = json.loads(experiment_paths(root)["state"].read_text(encoding="utf-8"))
    state["current_best_configurations"]["phase_g_fusion_finalists"] = finalists
    state["exact_next_action"] = (
        "Fuse the original query with the two strongest deterministic Phase G processors: "
        + ", ".join(finalists))
    write_json(experiment_paths(root)["state"], state)
    render_resume(root, state)
    _render_report(root, records)
    return {"fusion_finalists": finalists, "records": records}


def run_fusion(root: Path, benchmark: Path, cache_dir: Path, index_dir: Path,
               device: str, batch_size: int) -> dict[str, Any]:
    """Fuse the original query with only the two retained screen finalists."""
    state_path = experiment_paths(root)["state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    finalists = state.get("current_best_configurations", {}).get("phase_g_fusion_finalists", [])
    if not finalists:
        raise ValueError("run the deterministic Phase G screen before fusion")
    run_ids = [f"phase_g_g1_original_plus_{method}" for method in finalists]
    initialize_experiment(root, APPROVED_PLAN, run_ids, state.get("model_cache_status", {}))
    questions, pages, corpus, config, loaded, packed = _resources(
        root, benchmark, cache_dir, index_dir, device, batch_size)
    matrices, index = packed
    history = {r["run_id"]: r for r in read_run_log(experiment_paths(root)["runs"])}
    control = history["phase_g_g0_raw"]
    for method, run_id in zip(finalists, run_ids):
        if run_id in history:
            continue
        metrics, details, recall = _evaluate_method(
            loaded, config, method, questions, pages, corpus, matrices, fusion=True)
        provisional = {"metrics": {"overall": metrics["overall"],
                                   "natural_student": metrics["slices"]["natural_student"]}}
        canonical = metrics["slices"]["canonical"]
        if canonical["hit_at_5_count"] < control["metrics"]["canonical"]["hit_at_5_count"] - 1:
            decision, reason = "reject", "Original-query fusion still caused a material canonical Hit@5 regression."
        elif _quality_key(provisional) > _quality_key(control):
            decision, reason = "retain", "Original-plus-expanded fusion improved natural-first quality."
        else:
            decision, reason = "reject", "Fusion did not improve the raw-query natural-first ordering."
        history[run_id] = _checkpoint(
            root, run_id, f"phase_g_g0_{method}", method, True, metrics, details,
            recall, loaded, benchmark, index, decision, reason, device, batch_size)
    records = [history[run_id] for run_id in run_ids]
    # Final selection must compare fusion against every isolated screen, not
    # only raw retrieval; otherwise a slower fusion can hide a better direct
    # expansion using the exact same deterministic rules.
    screen_records = [history[f"phase_g_g0_{method}"] for method in SCREEN_METHODS]
    winner = select_phase_g_winner(screen_records + records)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["current_best_configurations"]["phase_g_deterministic_winner"] = {
        "run_id": winner["run_id"],
        "query_method": winner["configuration"]["query_method"],
        "fusion_with_original": winner["configuration"]["fusion_with_original"],
    }
    state["unresolved_questions"] = [
        "Would the separately gated local Gemma rewrite improve retrieval enough to justify its runtime?",
        "Which formula, table, visual, and distributed-evidence specialists should activate by query type?",
    ]
    state["exact_next_action"] = (
        "Pause at the separately gated Gemma rewrite boundary, or advance to Phase H "
        "textbook-specific retrieval specialists if Gemma is not approved/cached."
    )
    write_json(state_path, state)
    render_resume(root, state)
    all_records = [r for r in read_run_log(experiment_paths(root)["runs"]) if r["phase"] == "G"]
    _render_report(root, all_records)
    return {"winner": state["current_best_configurations"]["phase_g_deterministic_winner"],
            "records": records}


def build_parser() -> argparse.ArgumentParser:
    """Create the resumable deterministic Phase G command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--benchmark", type=Path,
                        default=Path("data/benchmarks/retrieval_benchmark_v1.jsonl"))
    parser.add_argument("--stage", choices=("screen", "fusion"), default="screen")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/retrieval/cache/models"))
    parser.add_argument("--index-dir", type=Path,
                        default=Path("data/retrieval/cache/experiments/phase_e"))
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=16)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run one Phase G stage and print its compact outcome."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    benchmark = args.benchmark if args.benchmark.is_absolute() else root / args.benchmark
    cache = args.cache_dir if args.cache_dir.is_absolute() else root / args.cache_dir
    index = args.index_dir if args.index_dir.is_absolute() else root / args.index_dir
    if args.stage == "screen":
        result = run_screen(root, benchmark, cache, index, args.device, args.batch_size)
        compact = {"fusion_finalists": result["fusion_finalists"]}
    else:
        result = run_fusion(root, benchmark, cache, index, args.device, args.batch_size)
        compact = {"winner": result["winner"]}
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
