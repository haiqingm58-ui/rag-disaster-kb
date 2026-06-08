from __future__ import annotations

from typing import Any

from app.crawlers.dedupe import DisasterEventStore
from app.crawlers.scheduler import run_source, source_status


def latest_official_events(
    type: str | None = None,
    level: str | None = None,
    city: str | None = None,
    county: str | None = None,
    source_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    active_only: bool = True,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return DisasterEventStore().latest(
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


def official_events_geojson(**filters: Any) -> dict[str, Any]:
    return DisasterEventStore().geojson(**filters)


def official_source_status() -> list[dict[str, Any]]:
    return source_status()


def run_official_source(source_id: str, limit: int | None = None) -> dict[str, Any]:
    return run_source(source_id, limit=limit)
