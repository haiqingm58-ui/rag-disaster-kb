#!/usr/bin/env python3
"""CLI: 手动刷新实时灾害 API 数据"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.disaster_api import (
    fetch_cenc_earthquakes,
    fetch_usgs_earthquakes,
    fetch_gdacs_events,
    sync_current_events,
)


def main():
    print("🌍 获取实时灾害数据...")
    print()

    print("📡 CENC 地震数据 (CENC records via Wolfx mirror):")
    try:
        cenc = fetch_cenc_earthquakes(force_refresh=True)
        print(f"   获取到 {len(cenc)} 条地震记录")
        for e in cenc[:5]:
            print(f"   - M{e.get('magnitude', '?')} {e.get('place', '?')}")
        if len(cenc) > 5:
            print(f"   ... 还有 {len(cenc) - 5} 条")
    except Exception as e:
        print(f"   获取失败: {e}")

    print()
    print("📡 USGS 地震数据:")
    try:
        eq = fetch_usgs_earthquakes(force_refresh=True)
        print(f"   获取到 {len(eq)} 条地震记录")
        for e in eq[:5]:
            print(f"   - M{e.get('magnitude', '?')} {e.get('place', '?')}")
        if len(eq) > 5:
            print(f"   ... 还有 {len(eq) - 5} 条")
    except Exception as e:
        print(f"   获取失败: {e}")

    print()
    print("📡 GDACS 全球灾害数据:")
    try:
        gd = fetch_gdacs_events(force_refresh=True)
        print(f"   获取到 {len(gd)} 条灾害记录")
        for ev in gd[:5]:
            name = ev.get("name", ev.get("eventname", "?"))
            etype = ev.get("eventtype", ev.get("type", "?"))
            print(f"   - [{etype}] {name}")
        if len(gd) > 5:
            print(f"   ... 还有 {len(gd) - 5} 条")
    except Exception as e:
        print(f"   获取失败: {e}")

    print()
    print("📥 同步到向量数据库...")
    result = sync_current_events(force_refresh=False)
    print(
        "✅ 完成！"
        f"本次事件 {result['total_events']} 条，"
        f"新增 {result['new_events']} 条，"
        f"跳过重复 {result['skipped_duplicates']} 条，"
        f"最后同步 {result['last_sync_time']}"
    )


if __name__ == "__main__":
    main()
