"""Query an existing multi-document collection without changing legacy book chats."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from textbook_chat.config import AppSettings
from textbook_chat.database import Database
from textbook_chat.domain import Backend
from textbook_chat.generation.offline import OfflineRuntimeManager
from textbook_chat.models.embedding import EmbeddingArtifactRegistry
from textbook_chat.models.offline import OfflineArtifactRegistry
from textbook_chat.repositories import CollectionRepository
from textbook_chat.retrieval.registry import RetrievalRuntimeRegistry
from textbook_chat.services.collections import CollectionService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection")
    parser.add_argument("--question")
    parser.add_argument("--backend", choices=("offline", "online"), default="offline")
    parser.add_argument("--authorize-online-transmission", action="store_true")
    args = parser.parse_args()
    settings = AppSettings.load()
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()
    store = CollectionRepository(database)
    if args.collection is None:
        print(json.dumps(store.list(), indent=2))
        return
    if args.question is None:
        parser.error("--question is required with --collection")
    runtime = OfflineRuntimeManager(settings, OfflineArtifactRegistry(settings))
    registry = RetrievalRuntimeRegistry(settings, EmbeddingArtifactRegistry(settings))
    try:
        result = CollectionService(settings, store, registry.embedding, runtime).ask(
            args.collection, args.question, Backend(args.backend),
            acknowledged=args.authorize_online_transmission,
        )
        print(json.dumps(result, indent=2))
        if result["state"] != "completed":
            raise SystemExit(1)
    finally:
        runtime.shutdown()


if __name__ == "__main__":
    main()
