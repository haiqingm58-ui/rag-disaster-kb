from __future__ import annotations

import math
import logging
from datetime import datetime, timedelta
from typing import Any

from src.ingestion.disaster_api import load_events_with_cache


logger = logging.getLogger(__name__)
REALTIME_HINTS = (
    "最近",
    "附近",
    "当前",
    "现在",
    "预警",
    "发生",
    "今日",
    "今天",
    "洪水",
    "暴雨",
    "内涝",
    "山洪",
    "滑坡",
    "山体滑坡",
    "崩塌",
    "泥石流",
)
FOCUS_EVENT_TYPES = ("Flood", "Landslide")
LANDSLIDE_TERMS = ("landslide", "mudslide", "debris flow", "滑坡", "崩塌", "泥石流")
FLOOD_TERMS = ("flood", "flash flood", "洪水", "山洪", "内涝", "暴雨")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def question_needs_realtime(question: str) -> bool:
    return any(hint in question for hint in REALTIME_HINTS)


def _event_text(ev: dict[str, Any]) -> str:
    return " ".join(
        str(ev.get(key, ""))
        for key in ("event_type", "event_type_group", "title", "place", "source_note")
    ).lower()


def _is_focus_event(ev: dict[str, Any]) -> bool:
    event_type = (ev.get("event_type") or "").lower()
    event_group = (ev.get("event_type_group") or "").lower()
    text = _event_text(ev)
    return (
        "flood" in event_type
        or "flood" in event_group
        or any(term in text for term in FLOOD_TERMS)
        or "landslide" in event_type
        or "landslide" in event_group
        or any(term in text for term in LANDSLIDE_TERMS)
    )


def _focus_rank(ev: dict[str, Any]) -> tuple[int, int, float]:
    text = _event_text(ev)
    if "landslide" in text or any(term in text for term in LANDSLIDE_TERMS):
        priority = 0
    elif "flood" in text or any(term in text for term in FLOOD_TERMS):
        priority = 1
    else:
        priority = 2
    return (priority, -(ev.get("risk_score") or 0), -(ev.get("time_ts") or 0))


def list_events(
    event_type: str | None = None,
    source: str | None = None,
    level: str | None = None,
    days: int | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_km: float | None = None,
    focus_only: bool = True,
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
        if focus_only and not event_type and not _is_focus_event(ev):
            continue
        if cutoff and (not ev.get("time_ts") or ev["time_ts"] < cutoff):
            continue
        if lat is not None and lon is not None and radius_km:
            distance = _haversine_km(lat, lon, ev.get("latitude") or 0, ev.get("longitude") or 0)
            if distance > radius_km:
                continue
            ev = {**ev, "distance_km": round(distance, 1)}
        filtered.append(ev)
    filtered.sort(key=_focus_rank if focus_only and not event_type else lambda item: item.get("time_ts") or 0, reverse=not (focus_only and not event_type))
    return filtered, statuses


def events_for_question(question: str, limit: int = 5) -> list[dict[str, Any]]:
    if not question_needs_realtime(question):
        return []
    focus_only = not any(word in question for word in ("地震", "台风", "火山", "干旱", "野火"))
    events, _ = list_events(days=7, focus_only=focus_only)
    return events[:limit]
