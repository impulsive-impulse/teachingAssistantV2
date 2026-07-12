"""Generate Retrieval Benchmark v1 candidates from anchored corpus evidence."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .pipeline import ROOT


FIELDS = [
    "question_id", "book_id", "subject_area", "chapter_number", "chapter_title",
    "question", "question_type", "gold_textbook_pages", "gold_pdf_pages",
    "gold_section_title", "gold_answer_span", "requires_multiple_pages",
    "requires_multiple_chunks", "visual_dependency", "formula_dependency",
    "table_dependency", "difficulty", "candidate_confidence",
    "expected_retrieval_notes", "source_record_ids_or_pages_checked",
]


def candidate(qid: str, book: str, area: str, chapter: int, title: str, question: str,
              qtype: str, pages: list[int], anchor: str | None, *, difficulty: str = "medium",
              confidence: str = "high", multi_pages: bool = False, multi_chunks: bool = False,
              visual: bool = False, formula: bool = False, table: bool = False,
              notes: str = "Retrieve the explicit textbook explanation.") -> dict[str, Any]:
    return {
        "question_id": qid, "book_id": book, "subject_area": area,
        "chapter_number": chapter, "chapter_title": title, "question": question,
        "question_type": qtype, "gold_textbook_pages": pages, "anchor": anchor,
        "requires_multiple_pages": multi_pages, "requires_multiple_chunks": multi_chunks,
        "visual_dependency": visual, "formula_dependency": formula,
        "table_dependency": table, "difficulty": difficulty,
        "candidate_confidence": confidence, "expected_retrieval_notes": notes,
    }


CANDIDATES = [
    # Biology: 4 definitions.
    candidate("BIO-001", "biology", "biology_nutrition", 1, "Nutrition", "What is photosynthesis?", "definition", [2], "This process is called as photosynthesis", difficulty="easy"),
    candidate("BIO-002", "biology", "biology_respiration", 2, "Respiration", "What does cellular respiration mean?", "definition", [36], "The term cellular respiration refers", difficulty="easy"),
    candidate("BIO-003", "biology", "biology_excretion", 4, "Excretion", "What are nephrons?", "definition", [83], "functional units are called 'nephrons'", difficulty="easy"),
    candidate("BIO-004", "biology", "biology_environment", 9, "Our Environment", "What is a food chain?", "definition", [205], "food chain", difficulty="easy"),
    # Biology: 5 process explanations.
    candidate("BIO-005", "biology", "biology_nutrition", 1, "Nutrition", "How does food move from the mouth through the oesophagus, and what begins carbohydrate digestion?", "process_explanation", [15], "passes through oesophagus", multi_chunks=True),
    candidate("BIO-006", "biology", "biology_nutrition", 1, "Nutrition", "How do photosynthetic plants build organic molecules?", "process_explanation", [2], "build up complex organic molecules", difficulty="easy"),
    candidate("BIO-007", "biology", "biology_circulation", 3, "Circulation", "How does blood complete double circulation through the heart and lungs?", "process_explanation", [58], "blood had a double circulation", difficulty="hard", multi_chunks=True),
    candidate("BIO-008", "biology", "biology_excretion", 4, "Excretion", "What are the stages involved in urine formation?", "process_explanation", [84, 85], "Formation of urine involves 4 stages", multi_pages=True, multi_chunks=True),
    candidate("BIO-009", "biology", "biology_reproduction", 6, "Reproduction", "How does pollination lead toward fertilization and seed formation in flowering plants?", "process_explanation", [136, 137], "pollination", difficulty="hard", multi_pages=True, multi_chunks=True),
    # Biology: 4 function/role explanations.
    candidate("BIO-010", "biology", "biology_nutrition", 1, "Nutrition", "What role do chloroplasts and chlorophyll play in photosynthesis?", "function_role", [10], "chlorophyll is found in organelles"),
    candidate("BIO-011", "biology", "biology_respiration", 2, "Respiration", "How does haemoglobin deliver oxygen to body tissues?", "function_role", [36], "oxyhaemoglobin releases the oxygen", difficulty="medium"),
    candidate("BIO-012", "biology", "biology_circulation", 3, "Circulation", "What role does lymph play between blood and tissues?", "function_role", [64], "Lymph is the vital link", difficulty="easy"),
    candidate("BIO-013", "biology", "biology_coordination", 5, "Coordination", "What functions are attributed to auxins and cytokinins?", "function_role", [117], "Auxins cell elongation", table=True),
    # Biology: 3 comparisons.
    candidate("BIO-014", "biology", "biology_respiration", 2, "Respiration", "How do aerobic and anaerobic respiration differ in oxygen use and products?", "compare_contrast", [36, 40, 41], "aerobic respiration", difficulty="hard", multi_pages=True, multi_chunks=True),
    candidate("BIO-015", "biology", "biology_circulation", 3, "Circulation", "How do arteries and veins differ in the direction of blood flow?", "compare_contrast", [58], "blood returned by way of the veins", difficulty="medium"),
    candidate("BIO-016", "biology", "biology_reproduction", 6, "Reproduction", "How does meiosis differ from mitosis in chromosome number and daughter cells?", "compare_contrast", [144, 145], "meiosis", difficulty="hard", multi_pages=True, multi_chunks=True, table=True),
    # Biology: 2 multi-page/section synthesis queries.
    candidate("BIO-017", "biology", "biology_coordination", 5, "Coordination", "How do nervous control and hormonal control coordinate responses in the human body?", "multi_page_synthesis", [100, 114], "Coordination", difficulty="hard", multi_pages=True, multi_chunks=True),
    candidate("BIO-018", "biology", "biology_natural_resources", 10, "Natural Resources", "How can water harvesting and groundwater recharge support sustainable water use?", "multi_page_synthesis", [231, 243], "water harvesting", difficulty="hard", multi_pages=True, multi_chunks=True),
    # Biology: 2 intentionally unanswerable/weak-evidence queries.
    candidate("BIO-019", "biology", "biology_health", 4, "Excretion", "What was Telangana's kidney-disease incidence rate in 2025?", "not_answerable", [], None, confidence="high", notes="Not answerable: the textbook explains excretion but does not provide this current regional statistic."),
    candidate("BIO-020", "biology", "biology_excretion", 4, "Excretion", "Which kidney disease does a particular patient have based only on frequent urination?", "weak_evidence", [], None, difficulty="hard", confidence="low", notes="Weak and unsafe evidence: the book mentions urination-related conditions, but the symptom alone cannot support a patient diagnosis."),

    # Physical Sciences: 4 definition/law questions.
    candidate("PSC-001", "physical_sciences", "physics_optics", 1, "Reflection of Light at Curved Surfaces", "State the laws of reflection of light.", "definition_law", [8], "laws of reflection", difficulty="easy", formula=True),
    candidate("PSC-002", "physical_sciences", "physics_optics", 4, "Refraction of Light at Curved Surfaces", "What relationship is expressed by Snell's law?", "definition_law", [64], "Snell", formula=True),
    candidate("PSC-003", "physical_sciences", "physics_electricity", 9, "Electric Current", "State Ohm's law and its condition.", "definition_law", [199], "potential difference between the ends", formula=True),
    candidate("PSC-004", "physical_sciences", "physics_electromagnetism", 10, "Electromagnetism", "What is electromagnetic induction?", "definition_law", [240], "Electromagnetic induction"),
    # Physical Sciences: 4 formula-based concepts.
    candidate("PSC-005", "physical_sciences", "physics_optics", 1, "Reflection of Light at Curved Surfaces", "What is the mirror formula relating focal length, object distance, and image distance?", "formula_concept", [14, 15], "mirror formula", multi_pages=True, multi_chunks=True, formula=True),
    candidate("PSC-006", "physical_sciences", "physics_optics", 4, "Refraction of Light at Curved Surfaces", "How are focal length, object distance, and image distance related for a lens?", "formula_concept", [77], "lens formula", formula=True),
    candidate("PSC-007", "physical_sciences", "physics_optics", 5, "Human Eye and Colourful World", "How is the power of a lens related to its focal length?", "formula_concept", [95], "power of lens", formula=True),
    candidate("PSC-008", "physical_sciences", "physics_electricity", 9, "Electric Current", "How can electric power be expressed using voltage and current?", "formula_concept", [214, 215], "Electric power P", multi_pages=True, multi_chunks=True, formula=True),
    # Physical Sciences: 4 diagram/ray/circuit concepts.
    candidate("PSC-009", "physical_sciences", "physics_optics", 1, "Reflection of Light at Curved Surfaces", "How is an image constructed using principal rays for a concave mirror?", "diagram_concept", [8], "diagram shows two rays", difficulty="hard", visual=True),
    candidate("PSC-010", "physical_sciences", "physics_optics", 4, "Refraction of Light at Curved Surfaces", "What happens to principal rays passing through a convex lens?", "diagram_concept", [72], "convex lens", visual=True),
    candidate("PSC-011", "physical_sciences", "physics_optics", 5, "Human Eye and Colourful World", "How does a concave lens correct myopia?", "diagram_concept", [92, 93], "myopia", multi_pages=True, multi_chunks=True, visual=True),
    candidate("PSC-012", "physical_sciences", "physics_electricity", 9, "Electric Current", "How do current paths differ in series and parallel circuits?", "diagram_concept", [205, 208], "connected in the circuit either in series or in parallel", difficulty="hard", multi_pages=True, multi_chunks=True, visual=True),
    # Physical Sciences: 3 numerical-style setup questions.
    candidate("PSC-013", "physical_sciences", "physics_optics", 1, "Reflection of Light at Curved Surfaces", "Which equation and sign convention should be used to calculate image distance for a spherical mirror?", "numerical_setup", [18], "mirror formula", difficulty="hard", formula=True),
    candidate("PSC-014", "physical_sciences", "physics_electricity", 9, "Electric Current", "How should the equivalent resistance of three parallel resistors be set up?", "numerical_setup", [208], "Equivalent resistance of a parallel connection", difficulty="medium", formula=True),
    candidate("PSC-015", "physical_sciences", "physics_electricity", 9, "Electric Current", "How would you set up the calculation of the energy used by a 60 W appliance over a given time?", "numerical_setup", [214, 215], "power is nothing but the rate", multi_pages=True, multi_chunks=True, formula=True),
    # Physical Sciences: 3 chemistry concepts.
    candidate("PSC-016", "physical_sciences", "chemistry_equations", 2, "Chemical Equations", "What makes a chemical equation balanced, and what information can be added to make it more informative?", "chemistry_concept", [27, 29], "balanced equation", multi_pages=True, multi_chunks=True, formula=True),
    candidate("PSC-017", "physical_sciences", "chemistry_acids_bases_salts", 3, "Acids, Bases and Salts", "How does the pH scale distinguish acidic, neutral, and basic solutions?", "chemistry_concept", [47], "pH of neutral solutions is 7"),
    candidate("PSC-018", "physical_sciences", "chemistry_bonding", 8, "Chemical Bonding", "How does covalent bonding achieve stable outer shells through electron sharing?", "chemistry_concept", [174], "mutual sharing of a pair", difficulty="hard", multi_chunks=True),
    # Physical Sciences: 2 intentionally unanswerable/weak-evidence queries.
    candidate("PSC-019", "physical_sciences", "physics_electricity", 9, "Electric Current", "What is the current residential electricity tariff per kWh in Hyderabad?", "not_answerable", [], None, confidence="high", notes="Not answerable: the textbook defines kWh but does not provide a current utility tariff."),
    candidate("PSC-020", "physical_sciences", "chemistry_acids_bases_salts", 3, "Acids, Bases and Salts", "What is the exact pH of an unknown household liquid without indicator readings or measurements?", "weak_evidence", [], None, difficulty="hard", confidence="low", notes="Weak evidence: the textbook explains pH and indicators, but no observation is supplied for this unknown sample."),
]


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def evidence_window(text: str, anchor: str, radius: int = 190) -> str:
    flat = normalized(text)
    index = flat.lower().find(anchor.lower())
    if index < 0:
        raise ValueError(f"Evidence anchor not found: {anchor!r}")
    start = max(0, index - radius // 2)
    end = min(len(flat), index + len(anchor) + radius)
    if start:
        boundary = flat.find(" ", start)
        start = boundary + 1 if boundary >= 0 else start
    if end < len(flat):
        boundary = flat.rfind(" ", start, end)
        end = boundary if boundary >= 0 else end
    return flat[start:end]


def load_records(root: Path) -> dict[str, dict[int, dict[str, Any]]]:
    books = {}
    for book_id in ("biology", "physical_sciences"):
        path = root / "data" / "processed" / f"{book_id}_pages.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        books[book_id] = {r["textbook_page_number"]: r for r in rows if isinstance(r["textbook_page_number"], int)}
    return books


def build_rows(root: Path = ROOT) -> list[dict[str, Any]]:
    records = load_records(root)
    rows = []
    for definition in CANDIDATES:
        row = {key: value for key, value in definition.items() if key != "anchor"}
        pages = row["gold_textbook_pages"]
        offset = 9 if row["book_id"] == "biology" else 10
        row["gold_pdf_pages"] = [page + offset for page in pages]
        checked = [f"{row['book_id']}:textbook_page_{page}:pdf_page_{page + offset}" for page in pages]
        row["source_record_ids_or_pages_checked"] = checked
        if pages:
            first = records[row["book_id"]][pages[0]]
            row["gold_section_title"] = first["section_title"]
            row["gold_answer_span"] = evidence_window(first["cleaned_text"], definition["anchor"])
        else:
            row["gold_section_title"] = None
            row["gold_answer_span"] = None
        rows.append({field: row[field] for field in FIELDS})
    return rows


def validate(rows: list[dict[str, Any]], root: Path = ROOT) -> list[str]:
    errors = []
    if len(rows) != 40:
        errors.append(f"Expected 40 rows, found {len(rows)}")
    counts = Counter(r["book_id"] for r in rows)
    if counts != Counter({"biology": 20, "physical_sciences": 20}):
        errors.append(f"Incorrect book distribution: {dict(counts)}")
    ids = [r["question_id"] for r in rows]
    if len(ids) != len(set(ids)):
        errors.append("Question IDs are not unique")
    records = load_records(root)
    for row in rows:
        if set(row) != set(FIELDS):
            errors.append(f"{row['question_id']}: schema mismatch")
        offset = 9 if row["book_id"] == "biology" else 10
        expected = [p + offset for p in row["gold_textbook_pages"]]
        if row["gold_pdf_pages"] != expected:
            errors.append(f"{row['question_id']}: PDF offset mismatch")
        span = row["gold_answer_span"]
        if span:
            nearby = " ".join(normalized(records[row["book_id"]][p]["cleaned_text"]) for p in row["gold_textbook_pages"])
            if normalized(span).lower() not in nearby.lower():
                errors.append(f"{row['question_id']}: answer span not found on gold pages")
    return errors


def notes_report(rows: list[dict[str, Any]], errors: list[str]) -> str:
    qtypes = Counter(r["question_type"] for r in rows)
    deps = {name: [r["question_id"] for r in rows if r[name]] for name in
            ("visual_dependency", "formula_dependency", "table_dependency")}
    low = [r["question_id"] for r in rows if r["candidate_confidence"] == "low"]
    lines = [
        "# Retrieval Benchmark v1 candidate notes", "",
        "> **Candidate benchmark only:** these rows are not final ground truth. A subject-matter reviewer must check questions, spans, page ranges, dependencies, and unanswerable labels before retrieval scoring.", "",
        "## Generation and evidence policy", "",
        "The benchmark is generated from anchored windows in the committed page-level JSONL. Answerable rows use only checked textbook records. PDF pages are derived using the project mappings: Biology `textbook + 9`; Physical Sciences `textbook + 10`. Empty-gold rows are intentional negative/weak-evidence candidates.", "",
        "## Distribution", "", "| Question type | Count |", "|---|---:|",
    ]
    lines += [f"| `{key}` | {qtypes[key]} |" for key in sorted(qtypes)]
    lines += ["", "Book distribution: 20 Biology and 20 Physical Sciences questions.", "", "## Dependency slices", ""]
    for name, ids in deps.items():
        lines.append(f"- `{name}` ({len(ids)}): {', '.join(ids) if ids else 'none'}")
    lines += [
        "", "## Manual-review priorities", "",
        f"- Low-confidence candidates: {', '.join(low) if low else 'none'}.",
        "- Review all visual rows against the PDF page image; text extraction cannot preserve ray, circuit, anatomy, or layout relationships.",
        "- Review formula rows against the PDF because fractions, superscripts/subscripts, Ω, arrows, and signs can be flattened or degraded.",
        "- Review table-dependent Biology rows for row/column alignment.",
        "- Multi-page spans intentionally quote an anchored excerpt from the first listed evidence page; the remaining pages are corroborating context and are named in the checked-page field.",
        "", "## Page-mapping issue", "",
        "The required constant offsets validate for every benchmark row. However, later Physical Sciences page headers visible inside extracted text sometimes drift from the project-assigned textbook page number. Candidate v1 follows the established JSONL mapping and task-required `+10` rule. Manual review should decide whether future corpus versions need discontinuous printed-page labels.",
        "", "## Automated validation", "",
    ]
    if errors:
        lines += [f"**FAILED with {len(errors)} issue(s):**", ""] + [f"- {error}" for error in errors]
    else:
        lines += [
            "**Passed.** Both CSV and JSONL were parsed after writing. All required columns exist; there are exactly 40 unique questions split 20/20 by book; all non-empty gold page lists obey the configured offsets; and every non-empty answer span occurs on its listed gold page set.",
        ]
    lines += [
        "", "## Recommended next step", "",
        "Conduct manual review in two passes: first verify evidence/page labels and negative examples against the PDFs; then review pedagogical wording, dependency flags, and difficulty. Freeze a corrected `retrieval_benchmark_v1.csv/jsonl` only after reviewer sign-off, and begin retrieval scoring against that frozen version.", "",
    ]
    return "\n".join(lines)


def generate(root: Path = ROOT) -> list[dict[str, Any]]:
    rows = build_rows(root)
    errors = validate(rows, root)
    out = root / "data" / "benchmarks"
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "retrieval_benchmark_v1_candidates.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            csv_row = row.copy()
            for field in ("gold_textbook_pages", "gold_pdf_pages", "source_record_ids_or_pages_checked"):
                csv_row[field] = json.dumps(csv_row[field], ensure_ascii=False)
            for field in ("requires_multiple_pages", "requires_multiple_chunks", "visual_dependency", "formula_dependency", "table_dependency"):
                csv_row[field] = str(csv_row[field]).lower()
            writer.writerow(csv_row)
    jsonl_path = out / "retrieval_benchmark_v1_candidates.jsonl"
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Parse both serialized forms as a final I/O validation.
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        parsed_csv = list(csv.DictReader(handle))
    parsed_jsonl = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    if len(parsed_csv) != len(rows) or len(parsed_jsonl) != len(rows):
        errors.append("Serialized CSV/JSONL row count mismatch")
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "retrieval_benchmark_v1_notes.md").write_text(notes_report(rows, errors), encoding="utf-8", newline="\n")
    if errors:
        raise ValueError("Benchmark validation failed:\n" + "\n".join(errors))
    return rows
