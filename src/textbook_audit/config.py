"""Immutable corpus configuration derived from the printed textbook indexes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BookSpec:
    book_id: str
    filename: str
    title: str
    content_pdf_offset: int
    roman_start_pdf: int
    chapters: tuple[tuple[int, str, int], ...]


SPECS = (
    BookSpec(
        "biology", "X Biology EM 2025-26.pdf", "Biology – Class 10", 9, 3,
        (
            (1, "Nutrition", 1), (2, "Respiration", 26),
            (3, "Circulation", 51), (4, "Excretion", 78),
            (5, "Coordination", 100), (6, "Reproduction", 123),
            (7, "Coordination in Life Processes", 153),
            (8, "Heredity - Evolution", 176), (9, "Our Environment", 205),
            (10, "Natural Resources", 225),
        ),
    ),
    BookSpec(
        "physical_sciences", "X Physics EM 2025-26.pdf",
        "Physical Sciences – Class 10", 10, 3,
        (
            (1, "Reflection of Light at Curved Surfaces", 1),
            (2, "Chemical Equations", 22), (3, "Acids, Bases and Salts", 35),
            (4, "Refraction of Light at Curved Surfaces", 62),
            (5, "Human Eye and Colourful World", 86),
            (6, "Structure of Atom", 112),
            (7, "Classification of Elements - The Periodic Table", 129),
            (8, "Chemical Bonding", 157), (9, "Electric Current", 185),
            (10, "Electromagnetism", 219),
            (11, "Principles of Metallurgy", 249),
            (12, "Carbon and its Compounds", 266),
        ),
    ),
)
