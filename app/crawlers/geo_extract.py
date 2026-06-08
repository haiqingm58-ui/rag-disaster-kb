from __future__ import annotations

import re
from typing import Any


PLACE_CENTERS: dict[str, tuple[float, float, str, dict[str, str]]] = {
    "长沙市": (28.2282, 112.9388, "city", {"province": "湖南省", "city": "长沙市"}),
    "长沙": (28.2282, 112.9388, "city", {"province": "湖南省", "city": "长沙市"}),
    "长沙县": (28.2460, 113.0810, "county", {"province": "湖南省", "city": "长沙市", "county": "长沙县"}),
    "浏阳市": (28.1638, 113.6433, "county", {"province": "湖南省", "city": "长沙市", "county": "浏阳市"}),
    "浏阳": (28.1638, 113.6433, "county", {"province": "湖南省", "city": "长沙市", "county": "浏阳市"}),
    "宁乡市": (28.2774, 112.5518, "county", {"province": "湖南省", "city": "长沙市", "county": "宁乡市"}),
    "宁乡": (28.2774, 112.5518, "county", {"province": "湖南省", "city": "长沙市", "county": "宁乡市"}),
    "望城区": (28.3475, 112.8179, "county", {"province": "湖南省", "city": "长沙市", "county": "望城区"}),
    "望城": (28.3475, 112.8179, "county", {"province": "湖南省", "city": "长沙市", "county": "望城区"}),
    "岳麓区": (28.2353, 112.9313, "county", {"province": "湖南省", "city": "长沙市", "county": "岳麓区"}),
    "岳麓": (28.2353, 112.9313, "county", {"province": "湖南省", "city": "长沙市", "county": "岳麓区"}),
    "湘江新区": (28.2353, 112.9313, "county", {"province": "湖南省", "city": "长沙市", "county": "湘江新区"}),
    "雨花区": (28.1354, 113.0385, "county", {"province": "湖南省", "city": "长沙市", "county": "雨花区"}),
    "天心区": (28.1127, 112.9899, "county", {"province": "湖南省", "city": "长沙市", "county": "天心区"}),
    "芙蓉区": (28.1854, 113.0325, "county", {"province": "湖南省", "city": "长沙市", "county": "芙蓉区"}),
    "开福区": (28.2559, 112.9852, "county", {"province": "湖南省", "city": "长沙市", "county": "开福区"}),
    "湖南省": (28.1124, 112.9834, "province", {"province": "湖南省"}),
    "湖南": (28.1124, 112.9834, "province", {"province": "湖南省"}),
    "大围山": (28.4310, 114.0960, "town", {"province": "湖南省", "city": "长沙市", "county": "浏阳市", "town": "大围山"}),
    "沩山": (28.3155, 112.0700, "town", {"province": "湖南省", "city": "长沙市", "county": "宁乡市", "town": "沩山"}),
}

RIVER_NAMES = ("湘江", "浏阳河", "捞刀河", "沩水")


def extract_coordinates(text: str) -> tuple[float | None, float | None]:
    patterns = [
        r"经度[:：]?\s*(?P<lng>1[01]\d(?:\.\d+)?)\D{0,12}纬度[:：]?\s*(?P<lat>2\d(?:\.\d+)?)",
        r"纬度[:：]?\s*(?P<lat>2\d(?:\.\d+)?)\D{0,12}经度[:：]?\s*(?P<lng>1[01]\d(?:\.\d+)?)",
        r"(?P<lng>1[01]\d\.\d+)\s*[,，]\s*(?P<lat>2\d\.\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group("lat")), float(match.group("lng"))
    return None, None


def extract_geo(text: str) -> dict[str, Any]:
    lat, lng = extract_coordinates(text)
    river_name = next((name for name in RIVER_NAMES if name in text), "")
    if lat is not None and lng is not None:
        return {
            "province": "湖南省" if "湖南" in text or "长沙" in text else "",
            "city": "长沙市" if "长沙" in text else "",
            "county": "",
            "town": "",
            "address_text": "",
            "river_name": river_name,
            "lat": lat,
            "lng": lng,
            "geo_precision": "exact_point",
        }

    for name, (place_lat, place_lng, precision, fields) in sorted(PLACE_CENTERS.items(), key=lambda item: len(item[0]), reverse=True):
        if name in text:
            return {
                "province": fields.get("province", ""),
                "city": fields.get("city", ""),
                "county": fields.get("county", ""),
                "town": fields.get("town", ""),
                "address_text": name,
                "river_name": river_name,
                "lat": place_lat,
                "lng": place_lng,
                "geo_precision": precision,
            }

    # No location matched — leave coordinates null rather than defaulting to Changsha.
    # Events without real coordinates should not show on the map.
    return {
        "province": "",
        "city": "",
        "county": "",
        "town": "",
        "address_text": "",
        "river_name": river_name,
        "lat": None,
        "lng": None,
        "geo_precision": "unknown",
    }
