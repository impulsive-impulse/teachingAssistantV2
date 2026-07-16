"""Render selected original-PDF pages used for formula, table, and visual checks."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).with_name("_deps")))

import fitz
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("rendered_pdf_checks")
OUT.mkdir(exist_ok=True)

GROUPS = {
    "biology_visual_formula": (ROOT / "books" / "X Biology EM 2025-26.pdf", [13, 49, 67, 68, 93, 94, 97, 127, 153, 154, 175, 189, 193, 197, 220, 226, 241, 245]),
    "physical_visual_formula_1": (ROOT / "books" / "X Physics EM 2025-26.pdf", [23, 28, 29, 35, 44, 48, 60, 90, 93, 102, 103, 116]),
    "physical_visual_formula_2": (ROOT / "books" / "X Physics EM 2025-26.pdf", [128, 129, 136, 146, 152, 153, 166, 176, 180, 181, 183, 195, 196, 198]),
    "physical_visual_formula_3": (ROOT / "books" / "X Physics EM 2025-26.pdf", [207, 208, 209, 217, 226, 229, 238, 248, 250, 267, 271, 274, 307, 317, 318]),
}


def render_group(name: str, pdf_path: Path, pages: list[int]) -> None:
    document = fitz.open(pdf_path)
    cards = []
    for page_number in pages:
        page = document[page_number - 1]
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        target_width = 520
        target_height = round(image.height * target_width / image.width)
        image = image.resize((target_width, target_height))
        card = Image.new("RGB", (target_width, target_height + 34), "white")
        card.paste(image, (0, 34))
        ImageDraw.Draw(card).text((8, 8), f"PDF page {page_number}", fill="black")
        cards.append(card)
    columns = 3
    rows = (len(cards) + columns - 1) // columns
    cell_width = max(card.width for card in cards)
    cell_height = max(card.height for card in cards)
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "#dddddd")
    for index, card in enumerate(cards):
        sheet.paste(card, ((index % columns) * cell_width, (index // columns) * cell_height))
    sheet.save(OUT / f"{name}.jpg", quality=88)


def main() -> None:
    for name, (pdf_path, pages) in GROUPS.items():
        render_group(name, pdf_path, pages)
    print(OUT)


if __name__ == "__main__":
    main()
