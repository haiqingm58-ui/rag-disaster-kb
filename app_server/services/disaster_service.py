from __future__ import annotations

import math
import logging
from datetime import datetime, timedelta
from typing import Any

from src.ingestion.disaster_api import load_events_with_cache


logger = logging.getLogger(__name__)
REALTIME_HINTS = ("最近", "附近", "当前", "现在", "预警", "地震了吗", "发生", "今日", "今天")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def question_needs_realtime(question: str) -> bool:
    return any(hint in question for hint in REALTIME_HINTS)


def list_events(
    event_type: str | None = None,
    source: str | None = None,
    level: str | None = None,
    days: int | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float | None = None,
    force_refresh: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        events, statuses = load_events_with_cache(force_refresh=force_refresh)
    except Exception as exc:
        logger.exception("load realtime disaster events failed")
        return [], {"error": str(exc)}
    cutoff = None
    if days:
        cutoff = (datetime.now() - timedelta(days=days)).timestamp()

    filtered = []
    for ev in events:
        if event_type and event_type.lower() not in (ev.get("event_type", "") + ev.get("event_type_group", "")).lower():
            continue
        if source and ev.get("source", "").lower() != source.lower():
            continue
        if level and ev.get("risk", "").lower() != level.lower():
            continue
        if cutoff and (not ev.get("time_ts") or ev["time_ts"] < cutoff):
            continue
        if lat is not None and lon is not None and radius_km:
            distance = _haversine_km(lat, lon, ev.get("latitude") or 0, ev.get("longitude") or 0)
            if distance > radius_km:
                continue
            ev = {**ev, "distance_km": round(distance, 1)}
        filtered.append(ev)
    filtered.sort(key=lambda item: item.get("time_ts") or 0, reverse=True)
    return filtered, statuses


def events_for_question(question: str, limit: int = 5) -> list[dict[str, Any]]:
    if not question_needs_realtime(question):
        return []
    events, _ = list_events(days=7)
    return events[:limit]
