import json
import math
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests
from langchain_core.documents import Document

from config import (
    CACHE_DIR,
    CACHE_TTL_CENC,
    CACHE_TTL_EARTHQUAKE,
    CACHE_TTL_GDACS,
    CENC_API_URL,
    USGS_API_URL,
    GDACS_API_URL,
)


SOURCE_NOTES = {
    "CENC": "CENC records via Wolfx mirror",
    "USGS": "USGS Earthquake Hazards Program",
    "GDACS": "Global Disaster Alert and Coordination System",
}


def _is_cache_fresh(path: Path, ttl: int) -> bool:
    """Check if cache file exists and is within TTL."""
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < ttl


def _read_cache(path: Path) -> Optional[dict]:
    """Read cached JSON, return None if not found."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _write_cache(path: Path, data: dict) -> None:
    """Write data to cache as JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _format_ts(ts: float | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _cache_info(path: Path, ttl: int) -> dict:
    exists = path.exists()
    mtime = path.stat().st_mtime if exists else None
    age = time.time() - mtime if mtime else None
    return {
        "cache_exists": exists,
        "cache_time": _format_ts(mtime),
        "cache_age_seconds": round(age, 1) if age is not None else None,
        "cache_ttl_seconds": ttl,
        "cache_fresh": bool(exists and age is not None and age < ttl),
        "last_success_time": _format_ts(mtime),
    }


def _status_template(source: str, cache_file: Path, ttl: int) -> dict:
    status = {
        "source": source,
        "note": SOURCE_NOTES.get(source, ""),
        "success": False,
        "request_success": None,
        "used_cache": False,
        "error": "",
        "record_count": 0,
        "updated_at": "",
    }
    status.update(_cache_info(cache_file, ttl))
    return status


def _load_json_source(
    source: str,
    url: str,
    cache_name: str,
    ttl: int,
    timeout: int,
    force_refresh: bool = False,
) -> tuple[Optional[dict], dict]:
    """Load JSON with TTL cache and a UI-friendly status record."""
    cache_file = CACHE_DIR / cache_name
    status = _status_template(source, cache_file, ttl)

    if not force_refresh and status["cache_fresh"]:
        cached = _read_cache(cache_file)
        if cached is not None:
            status.update({
                "success": True,
                "used_cache": True,
                "updated_at": status["cache_time"],
            })
            return cached, status

    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        _write_cache(cache_file, data)
        status.update(_cache_info(cache_file, ttl))
        status.update({
            "success": True,
            "request_success": True,
            "used_cache": False,
            "updated_at": status["cache_time"],
        })
        return data, status
    except Exception as e:
        cached = _read_cache(cache_file)
        status.update({
            "request_success": False,
            "error": str(e),
        })
        if cached is not None:
            status.update({
                "success": True,
                "used_cache": True,
                "updated_at": status["cache_time"],
            })
            return cached, status
        return None, status


def _as_float(value, default: float | None = None) -> float | None:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _point_from_feature(feature: dict) -> tuple[float | None, float | None]:
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if geom.get("type") == "Point" and len(coords) >= 2:
        return _as_float(coords[1]), _as_float(coords[0])

    bbox = feature.get("bbox") or []
    if len(bbox) >= 4:
        west, south, east, north = [_as_float(v) for v in bbox[:4]]
        if None not in (west, south, east, north):
            return (south + north) / 2, (west + east) / 2

    return None, None


def _risk_for_earthquake(magnitude: float | None) -> tuple[str, int, list[int]]:
    mag = magnitude or 0
    if mag >= 6:
        return "Critical", 4, [214, 39, 40, 190]
    if mag >= 4.5:
        return "High", 3, [245, 124, 0, 180]
    if mag >= 3:
        return "Moderate", 2, [250, 204, 21, 170]
    return "Low", 1, [46, 160, 67, 150]


def _risk_for_alert(alert: str) -> tuple[str, int, list[int]]:
    alert_norm = (alert or "").strip().lower()
    if alert_norm == "red":
        return "Critical", 4, [214, 39, 40, 190]
    if alert_norm == "orange":
        return "High", 3, [245, 124, 0, 180]
    if alert_norm == "green":
        return "Moderate", 2, [250, 204, 21, 170]
    return "Low", 1, [46, 160, 67, 150]


def _event_type_name(code: str) -> str:
    names = {
        "EQ": "Earthquake",
        "FL": "Flood",
        "TC": "Tropical Cyclone",
        "DR": "Drought",
        "VO": "Volcano",
        "WF": "Wildfire",
    }
    return names.get((code or "").upper(), code or "Disaster")


def _event_type_group(event_type: str) -> str:
    allowed = {"Earthquake", "Flood", "Tropical Cyclone", "Volcano", "Drought", "Wildfire"}
    return event_type if event_type in allowed else "Other"


def _parse_time_to_ts(value) -> float | None:
    """Parse common API date formats to a Unix timestamp."""
    if value in ("", None):
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1000 if value > 10_000_000_000 else float(value)

    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _stable_event_uid(source: str, event_id: str | None, title: str = "", event_time: str = "") -> str:
    """Build a stable Chroma ID for deduplicating realtime events."""
    raw_id = str(event_id or "").strip()
    if not raw_id:
        raw_id = hashlib.sha1(f"{source}|{title}|{event_time}".encode("utf-8")).hexdigest()[:16]
    safe_id = "".join(ch if ch.isalnum() or ch in "._:-" else "_" for ch in raw_id)
    return f"realtime::{source.lower()}::{safe_id}"


def _extract_usgs_events(data: dict) -> List[dict]:
    events = []
    for f in data.get("features", []):
        props = f.get("properties", {})
        geom = f.get("geometry", {}).get("coordinates", [])
        events.append({
            "id": f.get("id", ""),
            "title": props.get("title", ""),
            "magnitude": _as_float(props.get("mag"), 0),
            "place": props.get("place", ""),
            "time_ms": props.get("time", 0),
            "url": props.get("url", ""),
            "alert": props.get("alert", ""),
            "tsunami": props.get("tsunami", 0),
            "coords": {"lng": geom[0], "lat": geom[1], "depth_km": geom[2]} if len(geom) >= 3 else None,
        })
    return events


def _load_usgs_earthquakes(force_refresh: bool = False) -> tuple[List[dict], dict]:
    data, status = _load_json_source(
        "USGS",
        USGS_API_URL,
        "earthquakes.json",
        CACHE_TTL_EARTHQUAKE,
        timeout=15,
        force_refresh=force_refresh,
    )
    events = _extract_usgs_events(data) if data and "features" in data else []
    status["record_count"] = len(events)
    return events, status


def fetch_usgs_earthquakes(force_refresh: bool = False) -> List[dict]:
    """
    Fetch recent earthquakes from USGS hourly feed.
    Returns list of event dicts with keys: id, title, magnitude, place, time, url, coords.
    Cached for 10 minutes.
    """
    events, status = _load_usgs_earthquakes(force_refresh=force_refresh)
    if status["success"]:
        return events
    raise RuntimeError(status["error"] or "USGS 数据不可用")


def _extract_cenc_events(data: dict) -> List[dict]:
    """Extract CENC earthquake records from Wolfx CENC list format."""
    def sort_key(item):
        key, _ = item
        if key.startswith("No"):
            return int(key[2:] or 999)
        return 999

    events = []
    for key, item in sorted(data.items(), key=sort_key):
        if not key.startswith("No") or not isinstance(item, dict):
            continue
        mag = _as_float(item.get("magnitude"), 0)
        lat = _as_float(item.get("latitude"))
        lon = _as_float(item.get("longitude"))
        depth = _as_float(item.get("depth"))
        events.append({
            "id": item.get("EventID", key),
            "title": f"M {mag} - {item.get('placeName') or item.get('location') or '未知震源'}",
            "magnitude": mag,
            "place": item.get("placeName") or item.get("location") or "",
            "time": item.get("time", ""),
            "report_time": item.get("ReportTime", ""),
            "review_type": item.get("type", ""),
            "intensity": item.get("intensity", ""),
            "coords": {"lng": lon, "lat": lat, "depth_km": depth} if lat is not None and lon is not None else None,
        })
    return events


def _load_cenc_earthquakes(force_refresh: bool = False) -> tuple[List[dict], dict]:
    data, status = _load_json_source(
        "CENC",
        CENC_API_URL,
        "cenc_earthquakes.json",
        CACHE_TTL_CENC,
        timeout=15,
        force_refresh=force_refresh,
    )
    events = _extract_cenc_events(data) if data else []
    status["record_count"] = len(events)
    return events, status


def fetch_cenc_earthquakes(force_refresh: bool = False) -> List[dict]:
    """
    Fetch latest CENC earthquake records via the Wolfx CENC JSON mirror.
    The upstream list contains the latest 50 CENC earthquake information records.
    """
    events, status = _load_cenc_earthquakes(force_refresh=force_refresh)
    if status["success"]:
        return events
    raise RuntimeError(status["error"] or "CENC 数据不可用")


def _load_gdacs_events(force_refresh: bool = False) -> tuple[List[dict], dict]:
    data, status = _load_json_source(
        "GDACS",
        GDACS_API_URL,
        "gdacs.json",
        CACHE_TTL_GDACS,
        timeout=20,
        force_refresh=force_refresh,
    )

    features = []
    if isinstance(data, list):
        features = data
    elif isinstance(data, dict):
        features = data.get("features", [])
    events = [_extract_gdacs_props(f) for f in features]
    status["record_count"] = len(events)
    return events, status


def fetch_gdacs_events(force_refresh: bool = False) -> List[dict]:
    """
    Fetch active disaster events from GDACS.
    Returns list of event dicts with properties flattened. Cached for 30 minutes.
    """
    events, status = _load_gdacs_events(force_refresh=force_refresh)
    if status["success"]:
        return events
    raise RuntimeError(status["error"] or "GDACS 数据不可用")


def _extract_gdacs_props(feature: dict) -> dict:
    """Extract and flatten properties from a GDACS GeoJSON feature."""
    props = feature.get("properties", feature) if isinstance(feature, dict) else {}
    sev = props.get("severitydata", {})
    if not isinstance(sev, dict):
        sev = {}
    lat, lon = _point_from_feature(feature if isinstance(feature, dict) else {})
    return {
        "eventtype": props.get("eventtype", ""),
        "eventid": props.get("eventid", ""),
        "episodeid": props.get("episodeid", ""),
        "name": props.get("name", props.get("eventname", "")),
        "description": props.get("description", ""),
        "country": props.get("country", ""),
        "alertlevel": props.get("alertlevel", ""),
        "fromdate": props.get("fromdate", ""),
        "todate": props.get("todate", ""),
        "severitytext": sev.get("severitytext", ""),
        "iso3": props.get("iso3", ""),
        "lat": lat,
        "lng": lon,
        "report_url": (props.get("url") or {}).get("report", "") if isinstance(props.get("url"), dict) else "",
    }


def _format_earthquake_event(ev: dict) -> str:
    """Format an earthquake event as a readable Chinese string chunk."""
    mag = ev.get("magnitude", "?")
    place = ev.get("place", "未知地点")
    alert = ev.get("alert", "")
    tsunami = "，可能引发海啸" if ev.get("tsunami") else ""
    alert_str = f"，警报级别: {alert}" if alert else ""
    return f"【地震事件】震级 {mag} 级，地点: {place}{alert_str}{tsunami}。来源: USGS，事件ID: {ev.get('id', '')}。"


def _format_gdacs_event(ev: dict) -> str:
    """Format a GDACS event as a readable Chinese string chunk."""
    event_type = ev.get("eventtype", "未知类型")
    name = ev.get("name", "未知事件")
    severity = ev.get("severitytext", "")
    alert = ev.get("alertlevel", "")
    country = ev.get("country", "")
    description = ev.get("description", "")
    alert_str = f"，预警: {alert}" if alert else ""
    severity_str = f"，{severity}" if severity else ""
    country_str = f"，国家: {country}" if country else ""
    desc_str = f"，描述: {description}" if description else ""
    return f"【{event_type}事件】{name}{alert_str}{severity_str}{country_str}{desc_str}。来源: GDACS，事件ID: {ev.get('eventid', '')}。"


def get_earthquake_documents() -> List[Document]:
    """Fetch earthquake data and convert to LangChain Documents."""
    events = fetch_usgs_earthquakes()
    docs = []
    for ev in events:
        content = _format_earthquake_event(ev)
        docs.append(Document(
            page_content=content,
            metadata={
                "source": "usgs",
                "event_type": "earthquake",
                "event_id": ev.get("id", ""),
                "magnitude": ev.get("magnitude", 0),
                "place": ev.get("place", ""),
            },
        ))
    return docs


def get_cenc_documents() -> List[Document]:
    """Fetch CENC earthquake data and convert to LangChain Documents."""
    events = fetch_cenc_earthquakes()
    docs = []
    for ev in events:
        mag = ev.get("magnitude", "?")
        place = ev.get("place", "未知地点")
        depth = ev.get("coords", {}).get("depth_km") if ev.get("coords") else None
        depth_text = f"，震源深度 {depth} 千米" if depth is not None else ""
        content = (
            f"【地震事件】震级 {mag} 级，地点: {place}{depth_text}。"
            f"发震时间: {ev.get('time', '')}。来源: CENC 中国地震台网，事件ID: {ev.get('id', '')}。"
        )
        docs.append(Document(
            page_content=content,
            metadata={
                "source": "cenc",
                "event_type": "earthquake",
                "event_id": ev.get("id", ""),
                "magnitude": ev.get("magnitude", 0),
                "place": ev.get("place", ""),
            },
        ))
    return docs


def get_gdacs_documents() -> List[Document]:
    """Fetch GDACS events and convert to LangChain Documents."""
    events = fetch_gdacs_events()
    docs = []
    for ev in events:
        content = _format_gdacs_event(ev)
        docs.append(Document(
            page_content=content,
            metadata={
                "source": "gdacs",
                "event_type": ev.get("eventtype", ""),
                "event_id": str(ev.get("eventid", "")),
                "severity": ev.get("severitytext", ev.get("alertlevel", "")),
                "place": ev.get("country", ""),
            },
        ))
    return docs


def get_all_disaster_documents() -> List[Document]:
    """Get all disaster events as Documents (earthquakes + GDACS events)."""
    docs = []
    try:
        docs.extend(get_cenc_documents())
    except Exception as e:
        print(f"获取 CENC 地震数据失败: {e}")
    try:
        docs.extend(get_earthquake_documents())
    except Exception as e:
        print(f"获取 USGS 地震数据失败: {e}")
    try:
        docs.extend(get_gdacs_documents())
    except Exception as e:
        print(f"获取 GDACS 数据失败: {e}")
    return docs


def get_current_hazard_events(
    include_cenc: bool = True,
    include_usgs: bool = True,
    include_gdacs: bool = True,
    force_refresh: bool = False,
) -> List[dict]:
    """Return normalized live hazard events for the interactive map."""
    events: List[dict] = []

    if include_cenc:
        try:
            for ev in fetch_cenc_earthquakes(force_refresh=force_refresh):
                coords = ev.get("coords") or {}
                if coords.get("lat") is None or coords.get("lng") is None:
                    continue
                risk, risk_score, color = _risk_for_earthquake(ev.get("magnitude"))
                event_time = ev.get("time", "")
                event_uid = _stable_event_uid("CENC", ev.get("id"), ev.get("title", ""), event_time)
                events.append({
                    "event_uid": event_uid,
                    "event_id": ev.get("id", ""),
                    "source": "CENC",
                    "source_note": SOURCE_NOTES["CENC"],
                    "event_type": "Earthquake",
                    "event_type_group": "Earthquake",
                    "title": ev.get("title", ""),
                    "place": ev.get("place", ""),
                    "time": event_time,
                    "time_ts": _parse_time_to_ts(event_time),
                    "magnitude": ev.get("magnitude"),
                    "depth_km": coords.get("depth_km"),
                    "latitude": coords.get("lat"),
                    "longitude": coords.get("lng"),
                    "risk": risk,
                    "risk_score": risk_score,
                    "color": color,
                    "radius_m": 15000 + (ev.get("magnitude") or 0) * 9000,
                    "url": "https://news.ceic.ac.cn/",
                })
        except Exception as e:
            print(f"地图获取 CENC 数据失败: {e}")

    if include_usgs:
        try:
            for ev in fetch_usgs_earthquakes(force_refresh=force_refresh):
                coords = ev.get("coords") or {}
                if coords.get("lat") is None or coords.get("lng") is None:
                    continue
                risk, risk_score, color = _risk_for_earthquake(ev.get("magnitude"))
                event_time_ts = (ev.get("time_ms") or 0) / 1000
                event_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event_time_ts))
                event_uid = _stable_event_uid("USGS", ev.get("id"), ev.get("title", ""), event_time)
                events.append({
                    "event_uid": event_uid,
                    "event_id": ev.get("id", ""),
                    "source": "USGS",
                    "source_note": SOURCE_NOTES["USGS"],
                    "event_type": "Earthquake",
                    "event_type_group": "Earthquake",
                    "title": ev.get("title", ""),
                    "place": ev.get("place", ""),
                    "time": event_time,
                    "time_ts": event_time_ts,
                    "magnitude": ev.get("magnitude"),
                    "depth_km": coords.get("depth_km"),
                    "latitude": coords.get("lat"),
                    "longitude": coords.get("lng"),
                    "risk": risk,
                    "risk_score": risk_score,
                    "color": color,
                    "radius_m": 12000 + (ev.get("magnitude") or 0) * 8000,
                    "url": ev.get("url", ""),
                })
        except Exception as e:
            print(f"地图获取 USGS 数据失败: {e}")

    if include_gdacs:
        try:
            for ev in fetch_gdacs_events(force_refresh=force_refresh):
                if ev.get("lat") is None or ev.get("lng") is None:
                    continue
                risk, risk_score, color = _risk_for_alert(ev.get("alertlevel"))
                event_type = _event_type_name(ev.get("eventtype"))
                event_time = ev.get("fromdate", "")
                raw_event_id = f"{ev.get('eventid', '')}:{ev.get('episodeid', '')}".strip(":")
                event_uid = _stable_event_uid("GDACS", raw_event_id, ev.get("name", ""), event_time)
                events.append({
                    "event_uid": event_uid,
                    "event_id": raw_event_id,
                    "source": "GDACS",
                    "source_note": SOURCE_NOTES["GDACS"],
                    "event_type": event_type,
                    "event_type_group": _event_type_group(event_type),
                    "title": ev.get("name") or ev.get("description") or event_type,
                    "place": ev.get("country", ""),
                    "time": event_time,
                    "time_ts": _parse_time_to_ts(event_time),
                    "magnitude": None,
                    "depth_km": None,
                    "latitude": ev.get("lat"),
                    "longitude": ev.get("lng"),
                    "risk": risk,
                    "risk_score": risk_score,
                    "color": color,
                    "radius_m": 45000 + risk_score * 25000,
                    "url": ev.get("report_url", ""),
                })
        except Exception as e:
            print(f"地图获取 GDACS 数据失败: {e}")

    return events


def load_events_with_cache(
    include_cenc: bool = True,
    include_usgs: bool = True,
    include_gdacs: bool = True,
    force_refresh: bool = False,
) -> tuple[List[dict], dict]:
    """Load normalized map events and per-source cache/request status."""
    events: List[dict] = []
    statuses: dict = {}

    if include_cenc:
        cenc_events, statuses["CENC"] = _load_cenc_earthquakes(force_refresh=force_refresh)
        for ev in cenc_events:
            coords = ev.get("coords") or {}
            if coords.get("lat") is None or coords.get("lng") is None:
                continue
            risk, risk_score, color = _risk_for_earthquake(ev.get("magnitude"))
            event_time = ev.get("time", "")
            event_uid = _stable_event_uid("CENC", ev.get("id"), ev.get("title", ""), event_time)
            events.append({
                "event_uid": event_uid,
                "event_id": ev.get("id", ""),
                "source": "CENC",
                "source_note": SOURCE_NOTES["CENC"],
                "event_type": "Earthquake",
                "event_type_group": "Earthquake",
                "title": ev.get("title", ""),
                "place": ev.get("place", ""),
                "time": event_time,
                "time_ts": _parse_time_to_ts(event_time),
                "magnitude": ev.get("magnitude"),
                "depth_km": coords.get("depth_km"),
                "latitude": coords.get("lat"),
                "longitude": coords.get("lng"),
                "risk": risk,
                "risk_score": risk_score,
                "color": color,
                "radius_m": 15000 + (ev.get("magnitude") or 0) * 9000,
                "url": "https://news.ceic.ac.cn/",
            })

    if include_usgs:
        usgs_events, statuses["USGS"] = _load_usgs_earthquakes(force_refresh=force_refresh)
        for ev in usgs_events:
            coords = ev.get("coords") or {}
            if coords.get("lat") is None or coords.get("lng") is None:
                continue
            risk, risk_score, color = _risk_for_earthquake(ev.get("magnitude"))
            event_time_ts = (ev.get("time_ms") or 0) / 1000
            event_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(event_time_ts))
            event_uid = _stable_event_uid("USGS", ev.get("id"), ev.get("title", ""), event_time)
            events.append({
                "event_uid": event_uid,
                "event_id": ev.get("id", ""),
                "source": "USGS",
                "source_note": SOURCE_NOTES["USGS"],
                "event_type": "Earthquake",
                "event_type_group": "Earthquake",
                "title": ev.get("title", ""),
                "place": ev.get("place", ""),
                "time": event_time,
                "time_ts": event_time_ts,
                "magnitude": ev.get("magnitude"),
                "depth_km": coords.get("depth_km"),
                "latitude": coords.get("lat"),
                "longitude": coords.get("lng"),
                "risk": risk,
                "risk_score": risk_score,
                "color": color,
                "radius_m": 12000 + (ev.get("magnitude") or 0) * 8000,
                "url": ev.get("url", ""),
            })

    if include_gdacs:
        gdacs_events, statuses["GDACS"] = _load_gdacs_events(force_refresh=force_refresh)
        for ev in gdacs_events:
            if ev.get("lat") is None or ev.get("lng") is None:
                continue
            risk, risk_score, color = _risk_for_alert(ev.get("alertlevel"))
            event_type = _event_type_name(ev.get("eventtype"))
            event_time = ev.get("fromdate", "")
            raw_event_id = f"{ev.get('eventid', '')}:{ev.get('episodeid', '')}".strip(":")
            event_uid = _stable_event_uid("GDACS", raw_event_id, ev.get("name", ""), event_time)
            events.append({
                "event_uid": event_uid,
                "event_id": raw_event_id,
                "source": "GDACS",
                "source_note": SOURCE_NOTES["GDACS"],
                "event_type": event_type,
                "event_type_group": _event_type_group(event_type),
                "title": ev.get("name") or ev.get("description") or event_type,
                "place": ev.get("country", ""),
                "time": event_time,
                "time_ts": _parse_time_to_ts(event_time),
                "magnitude": None,
                "depth_km": None,
                "latitude": ev.get("lat"),
                "longitude": ev.get("lng"),
                "risk": risk,
                "risk_score": risk_score,
                "color": color,
                "radius_m": 45000 + risk_score * 25000,
                "url": ev.get("report_url", ""),
            })

    return events, statuses


def get_source_status(force_refresh: bool = False) -> dict:
    """Return status for all realtime sources."""
    _, statuses = load_events_with_cache(force_refresh=force_refresh)
    return statuses


def _event_document_content(ev: dict) -> str:
    magnitude = f"，震级 {ev.get('magnitude')}" if ev.get("magnitude") not in ("", None) else ""
    depth = f"，深度 {ev.get('depth_km')} 千米" if ev.get("depth_km") not in ("", None) else ""
    return (
        f"【{ev.get('event_type', 'Disaster')}事件】{ev.get('title', '')}"
        f"，地点: {ev.get('place', '')}{magnitude}{depth}。"
        f"时间: {ev.get('time', '')}。风险等级: {ev.get('risk', '')}。"
        f"经纬度: {ev.get('latitude', '')}, {ev.get('longitude', '')}。"
        f"来源: {ev.get('source', '')}，事件ID: {ev.get('event_id', '')}。"
    )


def event_to_document(ev: dict) -> Document:
    """Convert a normalized realtime event to a Chroma document."""
    metadata = {
        "source": ev.get("source", "").lower(),
        "event_type": ev.get("event_type", ""),
        "risk_level": ev.get("risk", ""),
        "location": ev.get("place", ""),
        "place": ev.get("place", ""),
        "latitude": ev.get("latitude") or 0,
        "longitude": ev.get("longitude") or 0,
        "event_time": ev.get("time", ""),
        "time_ts": ev.get("time_ts") or 0,
        "url": ev.get("url", ""),
        "source_url": ev.get("url", ""),
        "event_id": ev.get("event_id", ""),
        "event_uid": ev.get("event_uid", ""),
    }
    return Document(page_content=_event_document_content(ev), metadata=metadata)


def sync_events_to_vectorstore(events: List[dict]) -> dict:
    """Sync realtime events to ChromaDB using stable IDs to avoid duplicates."""
    from src.vectorstore.chroma_store import add_documents_with_ids, collection_ids
    from config import COLLECTION_EVENTS

    existing = collection_ids(COLLECTION_EVENTS)
    new_docs: List[Document] = []
    new_ids: List[str] = []
    skipped = 0

    for ev in events:
        event_uid = ev.get("event_uid") or _stable_event_uid(
            ev.get("source", "unknown"),
            ev.get("event_id"),
            ev.get("title", ""),
            ev.get("time", ""),
        )
        if event_uid in existing or event_uid in new_ids:
            skipped += 1
            continue
        ev["event_uid"] = event_uid
        new_docs.append(event_to_document(ev))
        new_ids.append(event_uid)

    if new_docs:
        add_documents_with_ids(new_docs, new_ids, COLLECTION_EVENTS)

    result = {
        "total_events": len(events),
        "new_events": len(new_docs),
        "skipped_duplicates": skipped,
        "last_sync_time": _format_ts(time.time()),
    }
    _write_cache(CACHE_DIR / "event_sync_status.json", result)
    return result


def sync_current_events(
    include_cenc: bool = True,
    include_usgs: bool = True,
    include_gdacs: bool = True,
    force_refresh: bool = False,
) -> dict:
    events, statuses = load_events_with_cache(
        include_cenc=include_cenc,
        include_usgs=include_usgs,
        include_gdacs=include_gdacs,
        force_refresh=force_refresh,
    )
    result = sync_events_to_vectorstore(events)
    result["statuses"] = statuses
    return result


def get_last_sync_status() -> dict:
    return _read_cache(CACHE_DIR / "event_sync_status.json") or {}


def refresh_all_events() -> int:
    """Force refresh all API data and sync new realtime events into ChromaDB."""
    return sync_current_events(force_refresh=True)["total_events"]
