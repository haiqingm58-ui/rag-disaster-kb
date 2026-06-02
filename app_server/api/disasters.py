from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app_server.schemas.disaster import DisasterEventsResponse
from app_server.security import CurrentUser, require_user
from app_server.services.disaster_service import list_events


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
    items, statuses = list_events(days=365, focus_only=True, force_refresh=True)
    return {"status": "ok", "count": len(items), "statuses": statuses}
