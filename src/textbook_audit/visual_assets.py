"""Extract embedded textbook PDF images for Phase H visual-evidence audit.

This is an asset-build step, not a visual retriever. It processes every
front-matter-free page flagged as image-bearing and records raster availability
without using benchmark labels. Semantic image ranking remains separately gated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .embedding_bakeoff import searchable_pages
from .experiment_tracking import sha256_file, write_json
from .retrieval import read_jsonl


def safe_image_name(name: str) -> str:
    """Convert a PDF image object name into a filesystem-safe stable name."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned or "embedded_image.bin"


def _manifest_valid(manifest: dict[str, Any], root: Path,
                    source_hashes: dict[str, str]) -> bool:
    """Validate source hashes and every cached extracted-image digest."""
    if manifest.get("source_pdf_sha256") != source_hashes:
        return False
    for item in manifest.get("images", []):
        path = root / item["path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            return False
    return True


def extract_visual_assets(root: Path, output_dir: Path,
                          manifest_path: Path) -> dict[str, Any]:
    """Extract raster XObjects from every searchable page marked with images."""
    try:
        import PIL
        import pypdf
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError(
            "visual asset extraction requires the optional visual-assets dependencies "
            "pypdf and Pillow; retrieval can continue without this audit artifact"
        ) from error

    pages = searchable_pages(root)
    source_paths = {
        book: root / "books" / book_pages[0]["source_file"]
        for book, book_pages in pages.items()
    }
    for path in source_paths.values():
        if not path.is_file():
            raise FileNotFoundError(f"source textbook PDF is missing: {path}")
    source_hashes = {book: sha256_file(path) for book, path in source_paths.items()}
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if _manifest_valid(existing, root, source_hashes):
            return {**existing, "cache_hit": True}

    output_dir.mkdir(parents=True, exist_ok=True)
    images, pages_without_raster = [], []
    marked_pages = 0
    for book, book_pages in pages.items():
        reader = PdfReader(source_paths[book])
        for page in book_pages:
            if not page.get("has_image"):
                continue
            marked_pages += 1
            pdf_page = int(page["pdf_page_number"])
            embedded = list(reader.pages[pdf_page - 1].images)
            if not embedded:
                pages_without_raster.append({"book_id": book, "pdf_page": pdf_page})
                continue
            for number, image in enumerate(embedded, 1):
                original = safe_image_name(image.name)
                filename = f"{book}_pdf_{pdf_page:04d}_{number:03d}_{original}"
                path = output_dir / filename
                digest = hashlib.sha256(image.data).hexdigest()
                if not path.is_file() or sha256_file(path) != digest:
                    path.write_bytes(image.data)
                images.append({
                    "book_id": book, "pdf_page": pdf_page,
                    "textbook_page": page.get("textbook_page_number"),
                    "chapter_title": page.get("chapter_title"),
                    "section_title": page.get("section_title"),
                    "object_name": image.name, "path": str(path.relative_to(root)),
                    "size_bytes": len(image.data), "sha256": digest,
                })
    manifest = {
        "schema_version": 1,
        "extraction_mode": "embedded_raster_xobjects_only_not_full_page_rendering",
        "semantic_ranking_performed": False,
        "front_matter_excluded": True,
        "source_pdf_sha256": source_hashes,
        "runtime": {"pypdf": pypdf.__version__, "pillow": PIL.__version__},
        "marked_image_pages": marked_pages,
        "pages_with_extracted_rasters": len({(i["book_id"], i["pdf_page"]) for i in images}),
        "pages_without_embedded_raster": pages_without_raster,
        "image_count": len(images),
        "total_size_bytes": sum(item["size_bytes"] for item in images),
        "images": images,
        "cache_hit": False,
    }
    write_json(manifest_path, manifest)
    return manifest


def visual_benchmark_asset_coverage(root: Path, manifest: dict[str, Any],
                                    benchmark_path: Path) -> dict[str, Any]:
    """Evaluate asset availability for visual rows after gold-blind extraction."""
    questions = read_jsonl(benchmark_path)
    available = {(item["book_id"], int(item["pdf_page"]))
                 for item in manifest["images"]}
    rows = []
    for question in questions:
        if not question.get("visual_dependency") or not question.get("gold_pdf_pages"):
            continue
        pages = [int(page) for page in question["gold_pdf_pages"]]
        covered = [page for page in pages if (question["book_id"], page) in available]
        rows.append({"question_id": question["question_id"],
                     "gold_pdf_pages": pages, "pages_with_raster_assets": covered,
                     "any_gold_page_has_raster": bool(covered),
                     "all_gold_pages_have_raster": len(covered) == len(pages)})
    return {"visual_questions": len(rows),
            "any_page_coverage_count": sum(row["any_gold_page_has_raster"] for row in rows),
            "all_pages_coverage_count": sum(row["all_gold_pages_have_raster"] for row in rows),
            "questions": rows}


def build_parser() -> argparse.ArgumentParser:
    """Create the visual asset extraction command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path,
                        default=Path("data/retrieval/cache/experiments/phase_h/visual_assets"))
    parser.add_argument("--manifest", type=Path,
                        default=Path("reports/experiments/phase_h_visual_assets.json"))
    parser.add_argument("--benchmark", type=Path,
                        default=Path("data/benchmarks/retrieval_benchmark_v1.jsonl"))
    return parser


def main(argv: list[str] | None = None) -> None:
    """Extract/cache visual assets, report capability coverage, and print a summary."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    output = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    benchmark = args.benchmark if args.benchmark.is_absolute() else root / args.benchmark
    manifest = extract_visual_assets(root, output, manifest_path)
    coverage = visual_benchmark_asset_coverage(root, manifest, benchmark)
    write_json(root / "reports" / "experiments" / "phase_h_visual_asset_coverage.json",
               coverage)
    print(json.dumps({"cache_hit": manifest["cache_hit"],
                      "marked_image_pages": manifest["marked_image_pages"],
                      "pages_with_rasters": manifest["pages_with_extracted_rasters"],
                      "image_count": manifest["image_count"],
                      "visual_question_any_page_coverage":
                          f'{coverage["any_page_coverage_count"]}/{coverage["visual_questions"]}'},
                     indent=2))


if __name__ == "__main__":
    main()
