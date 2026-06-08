from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app_server.security import CurrentUser, require_admin
from app_server.services.official_disaster_service import run_official_source


router = APIRouter(prefix="/crawler", tags=["crawler-admin"])


@router.post("/run")
def run(
    source_id: str = Query(..., min_length=1),
    limit: int | None = Query(None, ge=1, le=50),
    user: CurrentUser = Depends(require_admin),
) -> dict:
    result = run_official_source(source_id, limit=limit)
    return {"status": "ok" if not result.get("errors") else "partial", "result": result}
