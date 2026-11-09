from fastapi import APIRouter, Request, HTTPException, Query
from typing import Literal
from services.vespa_service import VespaError

router = APIRouter(tags=["system"])


@router.get("/livez")
def livez():
    """Process liveness only. Feature readiness is /capabilities; /health keeps its CLIP readiness meaning."""
    return {"status": "alive", "service": "drivescene-ai"}


@router.get("/capabilities")
def capabilities(request: Request, refresh: bool = False,
                 dataset_key: str | None = Query(default=None, pattern=r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$"),
                 dataset_version: Literal["v1.0-mini", "v1.0-trainval"] | None = None):
    # Sync route: a refresh may run a bounded read-only VESPA check in the thread pool. Never starts inference.
    if (dataset_key is None) != (dataset_version is None):
        raise HTTPException(422, "dataset_key and dataset_version must be supplied together")
    try:
        return request.app.state.capability_service.snapshot(refresh, dataset_key, dataset_version)
    except VespaError as error:
        raise HTTPException(error.status_code, detail={"code": error.code, "message": str(error)}) from error
