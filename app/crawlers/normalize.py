from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.crawlers.dedupe import content_hash
from app.crawlers.geo_extract import extract_geo
from app.crawlers.source_config import DisasterSource
from app.models.disaster_event import DisasterEvent


DISASTER_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("mountain_flood", ("山洪",)),
    ("debris_flow", ("泥石流",)),
    ("landslide", ("滑坡", "山体滑坡")),
    ("collapse", ("崩塌", "地面塌陷")),
    ("geological_disaster", ("地质灾害", "地灾", "风险预警")),
    ("flood", ("洪水", "内涝", "渍涝", "超警", "河道")),
    ("rainfall", ("暴雨", "雨量", "降雨")),
    ("water_level", ("水位",)),
    ("reservoir", ("水库",)),
]

WARNING_LEVELS: list[tuple[str, tuple[str, ...]]] = [
    ("red", ("红色预警", "一级", "极高风险")),
    ("orange", ("橙色预警", "二级", "高风险")),
    ("yellow", ("黄色预警", "三级", "较高风险")),
    ("blue", ("蓝色预警",)),
]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u3000", " ")).strip()


def detect_disaster_type(text: str) -> str:
    for disaster_type, keywords in DISASTER_KEYWORDS:
        if any(word in text for word in keywords):
            return disaster_type
    return "unknown"


def detect_warning_level(text: str) -> str:
    for level, keywords in WARNING_LEVELS:
        if any(word in text for word in keywords):
            return level
    return "unknown"


def parse_published_at(text: str) -> str:
    patterns = [
        r"(20\d{2})[-年./](\d{1,2})[-月./](\d{1,2})日?\s*(\d{1,2})?:?(\d{1,2})?:?(\d{1,2})?",
        r"(20\d{2})(\d{2})(\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        parts = [int(item) if item else 0 for item in match.groups()]
        year, month, day = parts[:3]
        hour = parts[3] if len(parts) > 3 else 0
        minute = parts[4] if len(parts) > 4 else 0
        second = parts[5] if len(parts) > 5 else 0
        try:
            return datetime(year, month, day, hour, minute, second).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_event(source: DisasterSource, raw: dict[str, Any]) -> DisasterEvent:
    title = clean_text(raw.get("title") or "未命名灾害信息")
    raw_text = clean_text(raw.get("raw_text") or raw.get("text") or raw.get("summary") or title)
    summary = clean_text(raw.get("summary") or raw_text[:240])
    full_text = f"{title} {summary} {raw_text}"
    published_at = clean_text(raw.get("published_at") or "") or parse_published_at(full_text)
    disaster_type = raw.get("disaster_type") or detect_disaster_type(full_text)
    warning_level = raw.get("warning_level") or detect_warning_level(full_text)
    geo = extract_geo(full_text)
    event = DisasterEvent(
        source_id=source.source_id,
        source_name=source.source_name,
        source_level=source.level,
        source_url=source.url,
        original_url=raw.get("original_url") or raw.get("url") or source.url,
        title=title,
        summary=summary,
        raw_text=raw_text,
        disaster_type=disaster_type,
        warning_type=raw.get("warning_type") or ("预警" if warning_level != "unknown" else ""),
        warning_level=warning_level,
        province=geo["province"],
        city=geo["city"],
        county=geo["county"],
        town=geo["town"],
        address_text=geo["address_text"],
        river_name=geo["river_name"],
        station_name=clean_text(raw.get("station_name") or ""),
        lat=geo["lat"],
        lng=geo["lng"],
        geo_precision=geo["geo_precision"],
        start_time=clean_text(raw.get("start_time") or ""),
        end_time=clean_text(raw.get("end_time") or ""),
        published_at=published_at,
        status=clean_text(raw.get("status") or "active"),
        confidence=clean_text(raw.get("confidence") or "official_news"),
        is_active=bool(raw.get("is_active", True)),
    )
    event.content_hash = content_hash(event.source_id, event.title, event.published_at, event.raw_text or event.summary)
    return event
