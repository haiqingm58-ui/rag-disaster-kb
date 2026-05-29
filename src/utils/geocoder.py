"""City name to coordinates with a small local cache."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import requests

from config import CACHE_DIR, GEOCODER_CACHE_TTL_HOURS, GEOCODER_PROVIDER, GEOCODER_USER_AGENT

CACHE_FILE = CACHE_DIR / "geocoder_cache.json"


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _cache_key(query: str) -> str:
    return query.strip().lower()


def _cache_valid(item: dict) -> bool:
    ttl_seconds = GEOCODER_CACHE_TTL_HOURS * 3600
    return time.time() - float(item.get("cached_at", 0)) <= ttl_seconds


def geocode_city(query: str) -> Optional[dict]:
    """Return a geocoding result or None.

    Result fields: name, latitude, longitude, provider, raw_display_name.
    """
    query = query.strip()
    if not query:
        return None

    cache = _load_cache()
    key = _cache_key(query)
    cached = cache.get(key)
    if cached and _cache_valid(cached):
        result = dict(cached["result"])
        result["from_cache"] = True
        return result

    if GEOCODER_PROVIDER != "nominatim":
        raise ValueError(f"当前仅内置 nominatim 地理编码，暂不支持：{GEOCODER_PROVIDER}")

    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "accept-language": "zh-CN,zh,en",
        },
        headers={"User-Agent": GEOCODER_USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None

    first = results[0]
    result = {
        "name": query,
        "latitude": float(first["lat"]),
        "longitude": float(first["lon"]),
        "provider": "nominatim",
        "raw_display_name": first.get("display_name", query),
        "from_cache": False,
    }
    cache[key] = {"cached_at": time.time(), "result": result}
    _save_cache(cache)
    return result
