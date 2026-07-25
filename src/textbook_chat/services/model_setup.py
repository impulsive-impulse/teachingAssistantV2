"""Explicit, durable download/setup workflow for pinned model artifacts."""

from __future__ import annotations

import threading
import traceback
import hashlib
import shutil
import urllib.request
import zipfile
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from ..models.embedding import EmbeddingArtifactRegistry
from ..models.offline import (
    OfflineArtifactRegistry,
)
from ..repositories import ModelSetupRepository
from .ingestion import IngestionCoordinator


class ModelSetupCoordinator:
    """Manage model downloads without blocking requests or hiding failures."""

    EMBEDDING_COMPONENT = "embedding_model"
    OFFLINE_COMPONENT = "offline_provider"

    def __init__(
        self,
        repository: ModelSetupRepository,
        registry: EmbeddingArtifactRegistry,
        ingestion: IngestionCoordinator,
        offline_registry: OfflineArtifactRegistry | None = None,
    ):
        self.repository = repository
        self.registry = registry
        self.offline_registry = offline_registry
        self.ingestion = ingestion
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="model-setup")
        self._lock = threading.Lock()
        self._active: dict[str, Future[None]] = {}
        self._closed = False

    def start(self) -> None:
        """Resume queued downloads and fail stale running records explicitly."""

        for component in (self.EMBEDDING_COMPONENT, self.OFFLINE_COMPONENT):
            active = self.repository.active(component)
            if active:
                self.submit(active["id"])

    def begin_embedding_setup(self) -> dict:
        existing = self.repository.active(self.EMBEDDING_COMPONENT)
        if existing:
            return existing
        job = self.repository.create(self.EMBEDDING_COMPONENT)
        self.submit(job["id"])
        return job

    def begin_offline_setup(self) -> dict:
        if self.offline_registry is None:
            raise RuntimeError("Offline artifact setup is not configured.")
        error = self.offline_registry.compatibility_error()
        if error:
            raise RuntimeError(error)
        existing = self.repository.active(self.OFFLINE_COMPONENT)
        if existing:
            return existing
        job = self.repository.create(self.OFFLINE_COMPONENT)
        self.submit(job["id"])
        return job

    def submit(self, job_uuid: str) -> None:
        with self._lock:
            if self._closed or job_uuid in self._active:
                return
            future = self._executor.submit(self._run, job_uuid)
            self._active[job_uuid] = future
            future.add_done_callback(lambda _future, job=job_uuid: self._finished(job))

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _finished(self, job_uuid: str) -> None:
        with self._lock:
            self._active.pop(job_uuid, None)

    def _run(self, job_uuid: str) -> None:
        job = self.repository.get(job_uuid)
        if not job:
            return
        if job["component"] == self.EMBEDDING_COMPONENT:
            self._run_embedding_setup(job_uuid)
        elif job["component"] == self.OFFLINE_COMPONENT:
            self._run_offline_setup(job_uuid)
        else:
            self.repository.update(
                job_uuid, state="failed", stage="failed", progress=0,
                error_code="unknown_setup_component", user_message="Unknown setup component.",
                terminal=True,
            )

    def _run_embedding_setup(self, job_uuid: str) -> None:
        try:
            self.repository.update(
                job_uuid, state="running", stage="checking_existing", progress=0.05,
                user_message="Checking approved local model caches.",
            )
            existing = self.registry.discover()
            if existing:
                self.repository.update(
                    job_uuid, state="completed", stage="verified", progress=1,
                    downloaded_bytes=0, total_bytes=existing.size_bytes,
                    user_message="Pinned BGE model verified and reused from the local cache.", terminal=True,
                )
                self.ingestion.resume_waiting()
                return
            self._download(job_uuid)
            verified = self.registry.discover()
            if not verified:
                raise RuntimeError("download completed but no verified frozen snapshot was found")
            self.repository.update(
                job_uuid, state="completed", stage="verified", progress=1,
                downloaded_bytes=verified.size_bytes, total_bytes=verified.size_bytes,
                user_message="Pinned BGE model downloaded and verified.", terminal=True,
            )
            self.ingestion.resume_waiting()
        except Exception as exc:
            self.repository.update(
                job_uuid, state="failed", stage="failed", progress=0,
                error_code="embedding_setup_failed",
                user_message="The pinned embedding model could not be downloaded and verified.",
                internal_detail="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                terminal=True,
            )

    def _download(self, job_uuid: str) -> None:
        """Download each file at the exact commit; Hub cache resumes partial files."""

        try:
            from huggingface_hub import HfApi, hf_hub_download, hf_hub_url
            from huggingface_hub.file_download import get_hf_file_metadata
        except ImportError as exc:
            raise RuntimeError("huggingface-hub is not installed") from exc

        api = HfApi()
        files = sorted(api.list_repo_files(self.registry.model_name, revision=self.registry.revision))
        sizes: dict[str, int] = {}
        for filename in files:
            metadata = get_hf_file_metadata(
                hf_hub_url(self.registry.model_name, filename, revision=self.registry.revision)
            )
            sizes[filename] = int(metadata.size or 0)
        total = sum(sizes.values())
        downloaded = 0
        for index, filename in enumerate(files, 1):
            self.repository.update(
                job_uuid, state="running", stage="downloading", progress=0.10 + 0.80 * (index - 1) / max(len(files), 1),
                downloaded_bytes=downloaded, total_bytes=total,
                user_message=f"Downloading pinned embedding model file {index} of {len(files)}.",
            )
            path = Path(hf_hub_download(
                repo_id=self.registry.model_name,
                filename=filename,
                revision=self.registry.revision,
                cache_dir=self.registry.application_cache,
            ))
            downloaded += path.stat().st_size
        snapshot = self.registry.application_cache / self.registry.repository_cache_name / "snapshots" / self.registry.revision
        self.repository.update(
            job_uuid, state="running", stage="verifying_checksum", progress=0.94,
            downloaded_bytes=downloaded, total_bytes=total,
            user_message="Verifying the frozen model snapshot checksum.",
        )
        self.registry.verify_path(snapshot)

    def _run_offline_setup(self, job_uuid: str) -> None:
        try:
            if self.offline_registry is None:
                raise RuntimeError("offline artifact setup is not configured")
            self.repository.update(
                job_uuid, state="running", stage="checking_existing", progress=0.02,
                user_message="Checking exact Qwen and llama.cpp artifacts.",
            )
            existing = self.offline_registry.discover()
            if existing:
                self.repository.update(
                    job_uuid, state="completed", stage="verified", progress=1,
                    total_bytes=existing.model_size_bytes,
                    user_message="Frozen offline provider artifacts verified and reused.", terminal=True,
                )
                return
            model_path = next(
                (
                    path for path in self.offline_registry.model_candidates()
                    if self.offline_registry.verify_model(path)
                ),
                None,
            )
            reused_model = model_path is not None
            if model_path is None:
                model_path = self._download_offline_model(job_uuid)
            if not self.offline_registry.verify_model(model_path):
                raise RuntimeError("downloaded Qwen GGUF failed its frozen SHA-256 check")
            self._download_llama_runtime(job_uuid)
            verified = self.offline_registry.discover()
            if not verified:
                raise RuntimeError("offline artifacts failed final identity and version checks")
            self.repository.update(
                job_uuid, state="completed", stage="verified", progress=1,
                downloaded_bytes=0 if reused_model else verified.model_size_bytes,
                total_bytes=verified.model_size_bytes,
                user_message=(
                    "Shared frozen Qwen model reused; selected llama.cpp runtime "
                    "downloaded and verified."
                    if reused_model else
                    "Frozen Qwen model and llama.cpp runtime downloaded and verified."
                ),
                terminal=True,
            )
        except Exception as exc:
            self.repository.update(
                job_uuid, state="failed", stage="failed", progress=0,
                error_code="offline_setup_failed",
                user_message="The frozen offline provider could not be downloaded and verified.",
                internal_detail="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                terminal=True,
            )

    def _download_offline_model(self, job_uuid: str) -> Path:
        try:
            from huggingface_hub import hf_hub_download
            from huggingface_hub.file_download import get_hf_file_metadata
            from huggingface_hub import hf_hub_url
        except ImportError as exc:
            raise RuntimeError("huggingface-hub is not installed") from exc
        registry = self.offline_registry
        if registry is None:
            raise RuntimeError("offline artifact setup is not configured")
        metadata = get_hf_file_metadata(hf_hub_url(
            registry.model_repository, registry.model_filename, revision=registry.model_revision
        ))
        total = int(metadata.size or 0)
        self.repository.update(
            job_uuid, state="running", stage="downloading_qwen", progress=0.05,
            total_bytes=total, user_message="Downloading the exact Qwen3-8B Q4_K_M model.",
        )
        return Path(hf_hub_download(
            repo_id=registry.model_repository,
            filename=registry.model_filename,
            revision=registry.model_revision,
            cache_dir=registry.model_root,
        ))

    def _download_llama_runtime(self, job_uuid: str) -> None:
        registry = self.offline_registry
        if registry is None:
            raise RuntimeError("offline artifact setup is not configured")
        backend = registry.backend
        spec = registry.runtime_spec(backend)
        runtime_dir = registry.runtime_directory(backend)
        archive = runtime_dir / "llama-runtime.zip.partial"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        self.repository.update(
            job_uuid, state="running", stage="downloading_llama", progress=0.86,
            user_message=(
                f"Downloading llama.cpp build {spec.build_number} for Windows ARM64 "
                f"{backend}."
            ),
        )
        with urllib.request.urlopen(spec.archive_url, timeout=120) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        digest = hashlib.sha256()
        with archive.open("rb") as source:
            for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != spec.archive_sha256:
            archive.unlink(missing_ok=True)
            raise RuntimeError("llama.cpp release archive failed its official SHA-256 check")
        staging = runtime_dir / "bin.staging"
        _assert_runtime_child(runtime_dir, staging)
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                target = (staging / member.filename).resolve()
                if staging.resolve() != target and staging.resolve() not in target.parents:
                    raise RuntimeError("llama.cpp archive contains an unsafe path")
            bundle.extractall(staging)
        server_candidates = list(staging.rglob("llama-server.exe"))
        if len(server_candidates) != 1:
            raise RuntimeError("llama.cpp archive does not contain exactly one server binary")
        extracted_root = server_candidates[0].parent
        final = runtime_dir / "bin"
        _assert_runtime_child(runtime_dir, final)
        if final.exists():
            shutil.rmtree(final)
        if extracted_root == staging:
            staging.replace(final)
        else:
            shutil.move(str(extracted_root), str(final))
            shutil.rmtree(staging, ignore_errors=True)
        archive.unlink(missing_ok=True)
        self.repository.update(
            job_uuid, state="running", stage="verifying_llama", progress=0.96,
            user_message="Verifying llama.cpp build, commit, and extracted file checksums.",
        )
        registry.write_runtime_manifest(final, backend)


def _assert_runtime_child(root: Path, target: Path) -> None:
    resolved_root, resolved_target = root.resolve(), target.resolve()
    if resolved_root == resolved_target or resolved_root not in resolved_target.parents:
        raise RuntimeError("refusing to modify a path outside the offline runtime directory")
