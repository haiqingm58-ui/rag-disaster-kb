from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app_server.schemas.disaster import DisasterEventsResponse
from app_server.security import CurrentUser, require_user
from app_server.services.disaster_service import list_events
from app_server.services.disaster_scheduler import disaster_scheduler


router = APIRouter(prefix="/disasters", tags=["disasters"])


@router.get("/events", response_model=DisasterEventsResponse)
def events(
    type: str | None = None,
    source: str | None = None,
    level: str | None = None,
    days: int | None = Query(7, ge=1, le=365),
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float | None = Query(None, gt=0),
    focus: bool = True,
) -> dict:
    items, statuses = list_events(
        event_type=type,
        source=source,
        level=level,
        days=days,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
        focus_only=focus,
    )
    return {"events": items, "count": len(items), "statuses": statuses}


@router.post("/sync")
def sync(user: CurrentUser = Depends(require_user)) -> dict:
    status = disaster_scheduler.trigger(force_refresh=True, reason="manual_api")
    result = status.get("last_result") or {}
    return {
        "status": "ok" if status.get("last_run_success", True) else "error",
        "count": result.get("total_events", 0),
        "new_events": result.get("new_events", 0),
        "skipped_duplicates": result.get("skipped_duplicates", 0),
        "statuses": result.get("statuses", {}),
        "scheduler": status,
        "vectorstore_error": result.get("vectorstore_error", ""),
    }


@router.get("/scheduler")
def scheduler_status(user: CurrentUser = Depends(require_user)) -> dict:
    return disaster_scheduler.status()


@router.post("/scheduler/run")
def scheduler_run(user: CurrentUser = Depends(require_user)) -> dict:
    return disaster_scheduler.trigger(force_refresh=True, reason="manual_scheduler_api")
