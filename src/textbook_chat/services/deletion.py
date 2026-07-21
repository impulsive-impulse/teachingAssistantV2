"""Scope-checked local deletion for books and their derived content."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

from ..config import AppSettings
from ..repositories import BookRepository


class BookDeletionService:
    def __init__(
        self,
        settings: AppSettings,
        books: BookRepository,
        evict_runtime: Callable[[str], None],
    ):
        self.settings = settings
        self.books = books
        self.evict_runtime = evict_runtime

    def delete(self, book_uuid: str) -> dict[str, Any]:
        book = self.books.begin_delete(book_uuid)
        try:
            self.evict_runtime(book_uuid)
            targets = [self.settings.data_dir / "books" / book_uuid]
            targets.extend(self.settings.data_dir / "jobs" / job for job in book["job_ids"])
            for target in targets:
                self._remove_owned_directory(target)
            self.books.finish_delete(book_uuid)
            return {"id": book_uuid, "deleted": True}
        except Exception:
            self.books.restore_after_delete_failure(book_uuid, book["status"])
            raise

    def _remove_owned_directory(self, target: Path) -> None:
        root = self.settings.data_dir.resolve()
        resolved = target.resolve()
        if root == resolved or root not in resolved.parents:
            raise RuntimeError("refusing to delete a path outside application storage")
        if resolved.exists():
            shutil.rmtree(resolved)
