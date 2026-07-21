"""Application and provider readiness/setup endpoints."""

import asyncio
import json
import os
import platform
import sys

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ...repositories import ModelSetupRepository
from ...schemas import ModelSetupJobResponse, SystemStatusResponse
from ...services.model_setup import ModelSetupCoordinator
from ...services.system import SystemStatusService
from ..dependencies import model_setup_coordinator, model_setups, offline_runtime, system_service


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def get_status(service: SystemStatusService = Depends(system_service)) -> SystemStatusResponse:
    """Return local checks only; this endpoint never contacts OpenAI."""

    return service.status()


@router.get("/diagnostics")
def get_diagnostics(service: SystemStatusService = Depends(system_service)) -> dict:
    """Return local runtime identities without environment values or content."""

    status_payload = service.status().model_dump(mode="json")
    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "process_id": os.getpid(),
        },
        "readiness": status_payload,
        "security": {
            "binding": "127.0.0.1",
            "api_key_present": service.settings.openai_api_key_present,
            "api_key_value_exposed": False,
            "automatic_provider_fallback": False,
            "automatic_online_retries": 0,
        },
    }


@router.post(
    "/embedding/setup", response_model=ModelSetupJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def setup_embedding_model(
    coordinator: ModelSetupCoordinator = Depends(model_setup_coordinator),
) -> dict:
    """Begin an explicit exact-revision download, or reuse verified local files."""

    return coordinator.begin_embedding_setup()


@router.post(
    "/offline/setup", response_model=ModelSetupJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def setup_offline_provider(
    coordinator: ModelSetupCoordinator = Depends(model_setup_coordinator),
) -> dict:
    """Begin explicit Qwen and llama.cpp setup after compatibility checks."""

    try:
        return coordinator.begin_offline_setup()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/offline/load")
def load_offline_provider(runtime=Depends(offline_runtime)) -> dict:
    try:
        return runtime.load()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/offline/runtime")
def offline_provider_runtime(runtime=Depends(offline_runtime)) -> dict:
    return runtime.status()


@router.post("/offline/unload")
def unload_offline_provider(runtime=Depends(offline_runtime)) -> dict:
    try:
        return runtime.unload()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/embedding/setup/{job_uuid}", response_model=ModelSetupJobResponse)
def get_embedding_setup(
    job_uuid: str, repository: ModelSetupRepository = Depends(model_setups)
) -> dict:
    job = repository.get(job_uuid)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model setup job not found.")
    return job


@router.get("/embedding/setup/{job_uuid}/events")
async def embedding_setup_events(
    job_uuid: str, repository: ModelSetupRepository = Depends(model_setups)
) -> StreamingResponse:
    if not repository.get(job_uuid):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model setup job not found.")

    async def stream():
        previous = None
        while True:
            job = repository.get(job_uuid)
            if not job:
                return
            public = ModelSetupJobResponse.model_validate(job).model_dump(mode="json")
            encoded = json.dumps(public, separators=(",", ":"))
            if encoded != previous:
                yield f"event: progress\ndata: {encoded}\n\n"
                previous = encoded
            if job["state"] in {"completed", "failed", "cancelled"}:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/offline/setup/{job_uuid}/events")
async def offline_setup_events(
    job_uuid: str, repository: ModelSetupRepository = Depends(model_setups)
) -> StreamingResponse:
    job = repository.get(job_uuid)
    if not job or job["component"] != ModelSetupCoordinator.OFFLINE_COMPONENT:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model setup job not found.")

    async def stream():
        previous = None
        while True:
            current = repository.get(job_uuid)
            if not current:
                return
            public = ModelSetupJobResponse.model_validate(current).model_dump(mode="json")
            encoded = json.dumps(public, separators=(",", ":"))
            if encoded != previous:
                yield f"event: progress\ndata: {encoded}\n\n"
                previous = encoded
            if current["state"] in {"completed", "failed", "cancelled"}:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
