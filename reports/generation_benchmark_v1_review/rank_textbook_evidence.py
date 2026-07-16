"""Rank authoritative textbook pages for the approval-stage 40-question shortlist."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
REVIEW = Path(__file__).parent

QUESTIONS = [
    ("GEN-BIO-001", "biology", 1, "What process do you follow in the laboratory to study the presence of starch in leaves?"),
    ("GEN-BIO-002", "biology", 1, "How are fats digested? Where do they get digested?"),
    ("GEN-BIO-003", "biology", 2, "How are alveoli designed to maximise the exchange of gases?"),
    ("GEN-BIO-004", "biology", 2, "What procedure do you follow to understand anaerobic respiration in your school laboratory?"),
    ("GEN-BIO-005", "biology", 3, "What is double circulation? Why is it important in humans?"),
    ("GEN-BIO-006", "biology", 3, "Differentiate between arteries and veins."),
    ("GEN-BIO-007", "biology", 4, "What is meant by excretion? Explain the process of formation of urine?"),
    ("GEN-BIO-008", "biology", 4, "Why do some people need to use a dialysis machine? Explain the principle involved in it"),
    ("GEN-BIO-009", "biology", 5, "How does phototropism occur in plants?"),
    ("GEN-BIO-010", "biology", 5, "How does a neuron differ from an ordinary cell in structure? Write notes?"),
    ("GEN-BIO-011", "biology", 6, "Why do fish and frog produce a huge number of eggs each year?"),
    ("GEN-BIO-012", "biology", 6, "Write the differences between mitosis and meiosis?"),
    ("GEN-BIO-013", "biology", 7, "How does mucus help in passage of food?"),
    ("GEN-BIO-014", "biology", 7, "Write the procedure involved in the acid and leaf experiment to understand the concept how the stomach gets protected from its own acid secretions. Compare the observations with the changes that takes place in human digestive system."),
    ("GEN-BIO-015", "biology", 8, "Explain monohybrid experiment with an example. Which law of inheritance can we understand? Explain?"),
    ("GEN-BIO-016", "biology", 8, "How does sex determination take place in human?"),
    ("GEN-BIO-017", "biology", 9, "What happens to the amount of energy transferred from one step to the next in a food chain?"),
    ("GEN-BIO-018", "biology", 9, "How is using of toxic material affecting the ecosystem? Write a short note on bioaccumulation and biomagnifications?"),
    ("GEN-BIO-019", "biology", 10, "What is sustainable development? How is it useful in natural resource management?"),
    ("GEN-BIO-020", "biology", 10, "Why is it important to recharge the ground water sources?"),
    ("GEN-PSC-001", "physical_sciences", 1, "Why do we prefer a convex mirror as a rear-view mirror in the vehicles?"),
    ("GEN-PSC-002", "physical_sciences", 1, "Find the distance of the image, when an object is placed on the principal axis, at a distance of 10 cm in front of a concave mirror whose radius of curvature is 8 cm."),
    ("GEN-PSC-003", "physical_sciences", 2, "What information do you get from a balanced chemical equation?"),
    ("GEN-PSC-004", "physical_sciences", 2, "Why should we balance a chemical equation?"),
    ("GEN-PSC-005", "physical_sciences", 3, "Which gas is usually liberated when an acid reacts with a metal? How will you test for the presence of this gas?"),
    ("GEN-PSC-006", "physical_sciences", 3, "Why does tooth decay start when the pH of mouth is lower than 5.5?"),
    ("GEN-PSC-007", "physical_sciences", 4, "How do you verify experimentally that the focal length of a convex lens is increased when it is kept in water?"),
    ("GEN-PSC-008", "physical_sciences", 4, "Write the lens maker’s formula and explain the terms in it."),
    ("GEN-PSC-009", "physical_sciences", 5, "How do you correct the eye defect Myopia? Explain the Myopia using the diagram."),
    ("GEN-PSC-010", "physical_sciences", 5, "Explain briefly the reason for the blue colour of the sky."),
    ("GEN-PSC-011", "physical_sciences", 6, "What is an orbital? How is it different from Bohr’s orbit?"),
    ("GEN-PSC-012", "physical_sciences", 7, "What are the limitations of Mendeleeff’s periodic table? How could the modern periodic table overcome the limitations of Mendeleeff’s table?"),
    ("GEN-PSC-013", "physical_sciences", 8, "Explain the formation of sodium chloride and calcium oxide on the basis of the concept of electron transfer from one atom to another atom."),
    ("GEN-PSC-014", "physical_sciences", 8, "Predict the reasons for low melting points for covalent compounds when compared with ionic compounds."),
    ("GEN-PSC-015", "physical_sciences", 9, "State Ohm’s law. Suggest an experiment to verify it and explain the procedure."),
    ("GEN-PSC-016", "physical_sciences", 9, "Why should we connect electric appliances in parallel in a household circuit? What happens if they are connected in series?"),
    ("GEN-PSC-017", "physical_sciences", 10, "Explain Faraday’s law of induction with the help of activity."),
    ("GEN-PSC-018", "physical_sciences", 10, "Explain the working of an electric motor with a neat diagram."),
    ("GEN-PSC-019", "physical_sciences", 11, "Suggest an experiment to prove that the presence of air and water are essential for corrosion. Explain the procedure."),
    ("GEN-PSC-020", "physical_sciences", 12, "Explain the cleansing action of soap."),
]

STOP = set("a an and are as at be between by do does for from how in into is it its of on or own should that the their them this to what when which why with you your".split())


def tokens(value: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", value.lower()) if len(t) > 2 and t not in STOP]


def load_pages(book: str) -> list[dict]:
    path = ROOT / "data" / "processed" / f"{book}_pages.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def rank(question: str, chapter: int, pages: list[dict]) -> list[tuple[float, dict]]:
    query = Counter(tokens(question))
    ranked = []
    for page in pages:
        if page.get("chapter_number") != chapter:
            continue
        page_tokens = Counter(tokens(page.get("cleaned_text", "")))
        covered = sum(1 for term in query if page_tokens[term])
        tf = sum(min(query[term], page_tokens[term]) for term in query)
        phrase = 5 if question.lower().strip("?.") in page.get("cleaned_text", "").lower() else 0
        ranked.append((covered * 10 + tf + phrase, page))
    return sorted(ranked, key=lambda item: (-item[0], item[1]["pdf_page_number"]))[:5]


def snippet(text: str, question: str, width: int = 700) -> str:
    lowered = text.lower()
    terms = sorted(set(tokens(question)), key=len, reverse=True)
    positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    start = max(0, (min(positions) if positions else 0) - 120)
    return re.sub(r"\s+", " ", text[start:start + width]).strip()


def main() -> None:
    corpora = {book: load_pages(book) for book in ("biology", "physical_sciences")}
    pdfs = {
        "biology": PdfReader(ROOT / "books" / "X Biology EM 2025-26.pdf"),
        "physical_sciences": PdfReader(ROOT / "books" / "X Physics EM 2025-26.pdf"),
    }
    lines = ["# Ranked textbook evidence candidates", "",
             "Each entry compares the processed page with text extracted independently from the original PDF.", ""]
    for qid, book, chapter, question in QUESTIONS:
        lines += [f"## {qid}", "", question, ""]
        for score, page in rank(question, chapter, corpora[book]):
            pdf_page = page["pdf_page_number"]
            original_text = pdfs[book].pages[pdf_page - 1].extract_text() or ""
            lines += [
                f"- score={score:.0f}; textbook={page.get('textbook_page_number')}; pdf={pdf_page}; section={page.get('section_title')!r}",
                f"  - processed: {snippet(page.get('cleaned_text', ''), question)}",
                f"  - original PDF text layer: {snippet(original_text, question)}",
            ]
        lines.append("")
    (REVIEW / "ranked_textbook_evidence.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(REVIEW / "ranked_textbook_evidence.md")


if __name__ == "__main__":
    main()
