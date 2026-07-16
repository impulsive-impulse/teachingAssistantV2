"""Controlled extraction of question/answer blocks from the 22 reviewed Manabadi pages.

This is a temporary approval-stage review utility, not production benchmark code.
The URL allow-list was copied from the chapter navigation visible on the two seed pages.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).with_name("_deps")))

import requests
from lxml import html


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("manabadi_raw_candidates.jsonl")

BIOLOGY = [
    (1, "Nutrition", "https://www.manabadi.co.in/ts-scert-10th-class-Biology-Lesson-1-Nutrition/278"),
    (2, "Respiration", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-2-Respiration&chpid=279"),
    (3, "Circulation", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-3-Circulation&chpid=280"),
    (4, "Excretion", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-4-Excretion&chpid=281"),
    (5, "Coordination", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-5-Coordination&chpid=282"),
    (6, "Reproduction", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-6-Reproduction&chpid=283"),
    (7, "Coordination in Life Processes", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-7-Coordination-in-Life-Processes&chpid=284"),
    (8, "Heredity - Evolution", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-8-Heredity-and-Evolution&chpid=285"),
    (9, "Our Environment", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-9-Our-Environment&chpid=286"),
    (10, "Natural Resources", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Biology-Lesson-10-Natural-Resources&chpid=287"),
]

PHYSICAL_SCIENCES = [
    (1, "Reflection of Light at Curved Surfaces", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-1-Reflection-of-Light-at-Curved-Surfaces&chpid=309"),
    (2, "Chemical Equations", "https://www.manabadi.co.in/ts-scert-10th-class-Physical-Science-Lesson-2-Chemical-Equations/310"),
    (3, "Acids, Bases and Salts", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-3-Acids-Bases-and-Salts&chpid=311"),
    (4, "Refraction of Light at Curved Surfaces", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-4-Refraction-of-Light-at-Curved-Surfaces&chpid=312"),
    (5, "Human Eye and Colourful World", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-5-Human-Eye-and-Colourful-World&chpid=313"),
    (6, "Structure of Atom", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-6-Structure-of-Atom&chpid=314"),
    (7, "Classification of Elements - The Periodic Table", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-7-Classification-of-Elements-The-Periodic-Table&chpid=315"),
    (8, "Chemical Bonding", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-8-Chemical-Bonding&chpid=316"),
    (9, "Electric Current", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-9-Electric-Current&chpid=317"),
    (10, "Electromagnetism", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-10-Electromagnetism&chpid=318"),
    (11, "Principles of Metallurgy", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-11-Principles-of-Metallurgy&chpid=319"),
    (12, "Carbon and its Compounds", "https://www.manabadi.co.in/articles/scert/SCERT-Chapter-Wise-Solutions.aspx?Chp=ts-scert-10th-class-Physical-Science-Lesson-12-Carbon-and-its-Compounds&chpid=320"),
]


def clean_text(node) -> str:
    return re.sub(r"\s+", " ", " ".join(node.itertext())).strip()


def infer_type(question: str) -> str:
    value = question.lower()
    if any(word in value for word in ("draw", "diagram", "figure", "observe the following")):
        return "visual_or_diagram"
    if any(word in value for word in ("experiment", "laboratory", "demonstrate", "procedure")):
        return "experiment_based"
    if any(word in value for word in ("calculate", "find the", "balance the", "formula", "equation")):
        return "formula_or_numerical"
    if any(word in value for word in ("difference", "differentiate", "compare", "distinguish")):
        return "comparison"
    if any(word in value for word in ("why", "explain", "how", "give reasons", "what happens")):
        return "explanatory"
    return "short_answer"


def extract_page(session: requests.Session, book_id: str, chapter_number: int,
                 chapter_title: str, source_url: str) -> list[dict]:
    response = session.get(source_url, timeout=30)
    response.raise_for_status()
    document = html.fromstring(response.content)
    rows = []
    for heading in document.xpath("//h5[starts-with(normalize-space(.), 'Question')]"):
        original = clean_text(heading)
        match = re.match(r"Question\s+([0-9]+[A-Za-z]?)\s*[.:]?\s*(.*)", original, re.I)
        question_number = match.group(1) if match else None
        wording = match.group(2).strip() if match else original
        answer_parts = []
        sibling = heading.getnext()
        while sibling is not None and not (
            isinstance(sibling.tag, str) and sibling.tag.lower() == "h5"
        ):
            if isinstance(sibling.tag, str):
                text = clean_text(sibling)
                if text:
                    answer_parts.append(text)
            sibling = sibling.getnext()
        website_answer = re.sub(r"^Answer\s*:\s*", "", " ".join(answer_parts), flags=re.I)
        rows.append({
            "book_id": book_id,
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "source_url": source_url,
            "resolved_url": response.url,
            "source_question_number": question_number,
            "original_source_question": wording,
            "original_heading": original,
            "website_answer": website_answer,
            "preliminary_question_type": infer_type(wording),
        })
    return rows


def main() -> None:
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (compatible; textbook-benchmark-review/1.0)"
    rows = []
    for book_id, pages in (("biology", BIOLOGY), ("physical_sciences", PHYSICAL_SCIENCES)):
        for chapter_number, chapter_title, source_url in pages:
            rows.extend(extract_page(session, book_id, chapter_number, chapter_title, source_url))
    deduplicated = []
    seen = set()
    for row in rows:
        key = (row["book_id"], row["chapter_number"], row["source_question_number"],
               row["original_source_question"])
        if key not in seen:
            seen.add(key)
            deduplicated.append(row)
    rows = deduplicated
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    counts = {}
    for row in rows:
        key = f"{row['book_id']}:{row['chapter_number']}"
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps({"rows": len(rows), "counts": counts, "output": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
