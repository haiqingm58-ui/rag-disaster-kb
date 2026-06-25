from __future__ import annotations

from fastapi import APIRouter, Query

from app_server.services.official_disaster_service import latest_official_events, official_events_geojson


router = APIRouter(prefix="/disaster-events", tags=["official-disaster-events"])


@router.get("/latest")
def latest(
    type: str | None = None,
    level: str | None = None,
    city: str | None = None,
    county: str | None = None,
    source_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    active_only: bool = True,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    events = latest_official_events(
        type=type,
        level=level,
        city=city,
        county=county,
        source_id=source_id,
        start_time=start_time,
        end_time=end_time,
        active_only=active_only,
        limit=limit,
    )
    return {"events": events, "count": len(events)}


@router.get("/geojson")
def geojson(
    type: str | None = None,
    level: str | None = None,
    city: str | None = None,
    county: str | None = None,
    source_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    active_only: bool = True,
    limit: int = Query(200, ge=1, le=500),
) -> dict:
    return official_events_geojson(
        type=type,
        level=level,
        city=city,
        county=county,
        source_id=source_id,
        start_time=start_time,
        end_time=end_time,
        active_only=active_only,
        limit=limit,
    )
