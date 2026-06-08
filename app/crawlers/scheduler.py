from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from app.crawlers.base import BaseDisasterCrawler
from app.crawlers.dedupe import CrawlerStatusStore, DisasterEventStore, EVENT_DB_PATH
from app.crawlers.source_config import get_source, load_sources


logger = logging.getLogger(__name__)

# Valid enum values for validation.
VALID_WARNING_LEVELS = {"red", "orange", "yellow", "blue", "unknown"}
VALID_DISASTER_TYPES = {
    "mountain_flood", "debris_flow", "landslide", "collapse",
    "geological_disaster", "flood", "rainfall", "water_level", "reservoir", "unknown",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_source(source_id: str, limit: int | None = None) -> dict[str, Any]:
    source = get_source(source_id)
    result = BaseDisasterCrawler(source).run(limit=limit)
    CrawlerStatusStore().update(
        source.source_id,
        {
            "last_run_at": now_text(),
            "last_success_at": now_text() if not result["errors"] else "",
            "last_error": "; ".join(item["error"] for item in result["errors"][:3]),
            "last_result": result,
        },
    )
    return result


def run_enabled_sources(limit: int | None = None) -> dict[str, Any]:
    results = []
    for source in load_sources(enabled_only=True):
        try:
            results.append(run_source(source.source_id, limit=limit))
        except Exception as exc:
            logger.exception("crawler source failed source=%s", source.source_id)
            CrawlerStatusStore().update(
                source.source_id,
                {"last_run_at": now_text(), "last_success_at": "", "last_error": str(exc), "last_result": {}},
            )
            results.append({"source_id": source.source_id, "source_name": source.source_name, "total_items": 0, "saved": 0, "new_events": 0, "errors": [{"error": str(exc)}]})
    return {
        "finished_at": now_text(),
        "sources": results,
        "total_events": sum(item.get("saved", 0) for item in results),
        "new_events": sum(item.get("new_events", 0) for item in results),
    }


def source_status() -> list[dict[str, Any]]:
    statuses = CrawlerStatusStore().read()
    counts = DisasterEventStore().count_by_source()
    rows = []
    for source in load_sources():
        status = statuses.get(source.source_id, {})
        rows.append({
            "source_id": source.source_id,
            "source_name": source.source_name,
            "level": source.level,
            "enabled": source.enabled,
            "fetch_interval_minutes": source.fetch_interval_minutes,
            "priority": source.priority,
            "last_run_at": status.get("last_run_at", ""),
            "last_success_at": status.get("last_success_at", ""),
            "last_error": status.get("last_error", ""),
            "total_events": counts.get(source.source_id, 0),
            "notes": source.notes,
        })
    return rows


def compute_stats() -> dict[str, Any]:
    """Compute aggregate statistics and anomaly detection from disaster_events."""
    store = DisasterEventStore()
    conn = store.connect()

    now = datetime.now()
    last_24h = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    last_7d = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    # Total events.
    total = conn.execute("SELECT COUNT(*) FROM disaster_events").fetchone()[0]

    # By source_id.
    by_source = {str(r["source_id"]): int(r["count"]) for r in conn.execute(
        "SELECT source_id, COUNT(*) AS count FROM disaster_events GROUP BY source_id"
    ).fetchall()}

    # By disaster_type.
    by_type = {str(r["disaster_type"]): int(r["count"]) for r in conn.execute(
        "SELECT disaster_type, COUNT(*) AS count FROM disaster_events GROUP BY disaster_type"
    ).fetchall()}

    # By warning_level.
    by_level = {str(r["warning_level"]): int(r["count"]) for r in conn.execute(
        "SELECT warning_level, COUNT(*) AS count FROM disaster_events GROUP BY warning_level"
    ).fetchall()}

    # Events with lat/lng.
    with_geo = conn.execute(
        "SELECT COUNT(*) FROM disaster_events WHERE lat IS NOT NULL AND lng IS NOT NULL"
    ).fetchone()[0]

    # geo_precision distribution.
    geo_precision_dist = {str(r["geo_precision"]): int(r["count"]) for r in conn.execute(
        "SELECT geo_precision, COUNT(*) AS count FROM disaster_events GROUP BY geo_precision"
    ).fetchall()}

    # Recent events.
    recent_24h = conn.execute(
        "SELECT COUNT(*) FROM disaster_events WHERE published_at >= ?", (last_24h,)
    ).fetchone()[0]
    recent_7d = conn.execute(
        "SELECT COUNT(*) FROM disaster_events WHERE published_at >= ?", (last_7d,)
    ).fetchone()[0]

    # --- Anomaly detection ---
    anomalies: list[dict[str, Any]] = []

    # 1. Empty title.
    empty_title = conn.execute(
        "SELECT COUNT(*) FROM disaster_events WHERE title IS NULL OR title = '' OR title = '未命名灾害信息'"
    ).fetchone()[0]
    if empty_title:
        anomalies.append({"type": "empty_title", "count": empty_title, "detail": "title 为空或为占位值"})

    # 2. Empty original_url.
    empty_url = conn.execute(
        "SELECT COUNT(*) FROM disaster_events WHERE original_url IS NULL OR original_url = ''"
    ).fetchone()[0]
    if empty_url:
        anomalies.append({"type": "empty_original_url", "count": empty_url, "detail": "original_url 为空"})

    # 3. lat/lng null but geo_precision = exact_point (contradiction).
    null_geo_exact = conn.execute(
        "SELECT COUNT(*) FROM disaster_events WHERE (lat IS NULL OR lng IS NULL) AND geo_precision = 'exact_point'"
    ).fetchone()[0]
    if null_geo_exact:
        anomalies.append({"type": "null_geo_exact_point", "count": null_geo_exact, "detail": "lat/lng 为空但 geo_precision=exact_point"})

    # 4. Invalid warning_level.
    invalid_level_rows = conn.execute(
        "SELECT COUNT(*) FROM disaster_events WHERE warning_level NOT IN ({})".format(
            ",".join(f"'{v}'" for v in VALID_WARNING_LEVELS)
        )
    ).fetchone()[0]
    if invalid_level_rows:
        anomalies.append({"type": "invalid_warning_level", "count": invalid_level_rows, "detail": f"warning_level 不在 {VALID_WARNING_LEVELS}"})

    # 5. Invalid disaster_type.
    invalid_type_rows = conn.execute(
        "SELECT COUNT(*) FROM disaster_events WHERE disaster_type NOT IN ({})".format(
            ",".join(f"'{v}'" for v in VALID_DISASTER_TYPES)
        )
    ).fetchone()[0]
    if invalid_type_rows:
        anomalies.append({"type": "invalid_disaster_type", "count": invalid_type_rows, "detail": f"disaster_type 不在 {VALID_DISASTER_TYPES}"})

    # 6. Default Changsha center coordinates (lat≈28.2282, lng≈112.9388) with geo_precision=city
    # These are system-inferred, not from real coordinates.
    default_coords = conn.execute(
        "SELECT COUNT(*) FROM disaster_events WHERE lat = 28.2282 AND lng = 112.9388 AND geo_precision = 'city'"
    ).fetchone()[0]
    if default_coords:
        anomalies.append({"type": "default_changsha_center", "count": default_coords, "detail": "使用系统默认长沙中心坐标（非真实定位）"})

    # 7. Events with lat/lng equal to default and geo_precision != exact_point → system inference.
    sys_inferred = conn.execute(
        "SELECT COUNT(*) FROM disaster_events WHERE lat = 28.2282 AND lng = 112.9388 AND geo_precision != 'exact_point'"
    ).fetchone()[0]
    if sys_inferred:
        anomalies.append({"type": "system_inferred_coords", "count": sys_inferred, "detail": "坐标是系统根据地名推断，非官方精确点位"})

    return {
        "total_events": total,
        "by_source_id": by_source,
        "by_disaster_type": by_type,
        "by_warning_level": by_level,
        "with_lat_lng": with_geo,
        "geo_precision_distribution": geo_precision_dist,
        "recent_24h": recent_24h,
        "recent_7d": recent_7d,
        "anomalies": anomalies,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="长沙中心权威灾害信息采集任务")
    parser.add_argument("--once", action="store_true", help="运行所有 enabled=true 的数据源一次")
    parser.add_argument("--all", action="store_true", help="运行所有 enabled=true 的数据源一次")
    parser.add_argument("--source", help="只运行指定 source_id")
    parser.add_argument("--limit", type=int, default=None, help="每个源最多处理的列表项数量")
    parser.add_argument("--stats", action="store_true", help="输出数据库统计和异常检测")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.stats:
        result = compute_stats()
    elif args.source:
        result = run_source(args.source, limit=args.limit)
    elif args.once or args.all:
        result = run_enabled_sources(limit=args.limit)
    else:
        parser.error("请指定 --once、--all、--source 或 --stats")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
