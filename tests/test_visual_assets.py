"""Regression tests for visual asset naming and post-extraction coverage."""

from pathlib import Path

from textbook_audit.visual_assets import safe_image_name, visual_benchmark_asset_coverage


ROOT = Path(__file__).resolve().parents[1]


def test_embedded_image_names_are_safe_and_stable() -> None:
    """PDF object names cannot escape or create invalid artifact paths."""
    assert safe_image_name("I 7/../../figure.jpg") == "I_7_.._.._figure.jpg"
    assert safe_image_name("***") == "embedded_image.bin"


def test_visual_coverage_is_evaluation_only() -> None:
    """Coverage reads the completed manifest and never selects extraction pages."""
    manifest = {"images": [
        {"book_id": "physical_sciences", "pdf_page": 18},
        {"book_id": "physical_sciences", "pdf_page": 82},
    ]}
    coverage = visual_benchmark_asset_coverage(
        ROOT, manifest, ROOT / "data" / "benchmarks" / "retrieval_benchmark_v1.jsonl")
    assert coverage["visual_questions"] == 6
    assert coverage["any_page_coverage_count"] == 2
