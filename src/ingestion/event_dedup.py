"""Approximate event deduplication and confidence scoring."""

from __future__ import annotations

import math
from datetime import datetime

from config import (
    EVENT_DEDUP_DISTANCE_KM,
    EVENT_DEDUP_MAGNITUDE_DELTA,
    EVENT_DEDUP_TIME_WINDOW_MINUTES,
)

OFFICIAL_SOURCES = {"CENC", "USGS", "GDACS"}
SIMILAR_TYPES = {
    "Earthquake": {"Earthquake"},
    "Flood": {"Flood"},
    "Tropical Cyclone": {"Tropical Cyclone", "Typhoon", "Cyclone"},
    "Volcano": {"Volcano"},
    "Drought": {"Drought"},
    "Wildfire": {"Wildfire", "Fire"},
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_time_ts(event: dict) -> float | None:
    if event.get("time_ts"):
        return float(event["time_ts"])
    value = event.get("time") or event.get("event_time") or ""
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).timestamp()
        except Exception:
            continue
    return None


def _types_similar(a: str, b: str) -> bool:
    if a == b:
        return True
    return b in SIMILAR_TYPES.get(a, set()) or a in SIMILAR_TYPES.get(b, set())


def _is_duplicate(a: dict, b: dict) -> bool:
    if not _types_similar(a.get("event_type", ""), b.get("event_type", "")):
        return False
    try:
        distance = _haversine_km(float(a["latitude"]), float(a["longitude"]), float(b["latitude"]), float(b["longitude"]))
    except Exception:
        return False
    if distance > EVENT_DEDUP_DISTANCE_KM:
        return False

    t1 = _parse_time_ts(a)
    t2 = _parse_time_ts(b)
    if t1 is not None and t2 is not None:
        if abs(t1 - t2) > EVENT_DEDUP_TIME_WINDOW_MINUTES * 60:
            return False

    if a.get("event_type") == "Earthquake" and b.get("event_type") == "Earthquake":
        m1 = a.get("magnitude")
        m2 = b.get("magnitude")
        if m1 not in (None, "") and m2 not in (None, ""):
            if abs(float(m1) - float(m2)) > EVENT_DEDUP_MAGNITUDE_DELTA:
                return False
    return True


def _confidence_for_group(group: list[dict]) -> str:
    sources = {e.get("source") for e in group if e.get("source")}
    official_count = len(sources & OFFICIAL_SOURCES)
    if official_count >= 2:
        return "high"
    if official_count == 1:
        return "medium"
    if any(e.get("source_type") == "user_report" for e in group):
        return "unverified"
    return "low"


def merge_events(events: list[dict]) -> list[dict]:
    """Annotate events with merged group metadata while keeping raw records."""
    groups: list[list[dict]] = []
    for event in events:
        for group in groups:
            if any(_is_duplicate(event, existing) for existing in group):
                group.append(event)
                break
        else:
            groups.append([event])

    merged_events = []
    for idx, group in enumerate(groups, 1):
        raw_ids = [
            str(e.get("event_id") or e.get("id") or e.get("report_id") or f"raw_{idx}_{i}")
            for i, e in enumerate(group)
        ]
        raw_sources = sorted({str(e.get("source") or e.get("platform") or e.get("source_type") or "unknown") for e in group})
        confidence = _confidence_for_group(group)
        primary = group[0]
        for event in group:
            annotated = dict(event)
            annotated.update({
                "merged_event_id": f"merged_{idx}",
                "raw_event_ids": raw_ids,
                "raw_sources": raw_sources,
                "primary_source": primary.get("source") or primary.get("platform") or primary.get("source_type", ""),
                "source_count": len(raw_sources),
                "confidence_level": confidence,
            })
            merged_events.append(annotated)
    return merged_events
