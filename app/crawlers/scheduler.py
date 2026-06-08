from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from typing import Any

from app.crawlers.base import BaseDisasterCrawler
from app.crawlers.dedupe import CrawlerStatusStore, DisasterEventStore
from app.crawlers.source_config import get_source, load_sources


logger = logging.getLogger(__name__)


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


def main() -> None:
    parser = argparse.ArgumentParser(description="长沙中心权威灾害信息采集任务")
    parser.add_argument("--once", action="store_true", help="运行所有 enabled=true 的数据源一次")
    parser.add_argument("--all", action="store_true", help="运行所有 enabled=true 的数据源一次")
    parser.add_argument("--source", help="只运行指定 source_id")
    parser.add_argument("--limit", type=int, default=None, help="每个源最多处理的列表项数量")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.source:
        result = run_source(args.source, limit=args.limit)
    elif args.once or args.all:
        result = run_enabled_sources(limit=args.limit)
    else:
        parser.error("请指定 --once、--all 或 --source")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
