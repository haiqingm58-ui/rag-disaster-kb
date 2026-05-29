#!/usr/bin/env python3
"""Inspect MinerU output directory — list files and JSON structure preview.

Usage:
  python scripts/inspect_mineru_output.py <mineru_output_dir>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def inspect_directory(dir_path: Path):
    print(f"MinerU 输出目录: {dir_path}")
    print("=" * 60)

    # List all files
    all_files = sorted(dir_path.rglob("*"))
    json_files = [f for f in all_files if f.suffix == ".json"]
    md_files = [f for f in all_files if f.suffix == ".md"]
    pdf_files = [f for f in all_files if f.suffix == ".pdf"]
    img_files = [f for f in all_files if f.suffix in (".jpg", ".png")]

    print(f"  文件统计:")
    print(f"    JSON:     {len(json_files)}")
    print(f"    Markdown: {len(md_files)}")
    print(f"    PDF:      {len(pdf_files)}")
    print(f"    Images:   {len(img_files)}")

    print(f"\n  JSON 文件:")
    for f in json_files:
        size = f.stat().st_size
        print(f"    {f.name}  ({size//1024} KB)")

    print(f"\n  Markdown 文件:")
    for f in md_files:
        size = f.stat().st_size
        print(f"    {f.name}  ({size//1024} KB)")

    # Preview each JSON
    for f in json_files:
        _preview_json(f)


def _preview_json(path: Path):
    print(f"\n{'─'*60}")
    print(f"预览: {path.name}")
    print(f"{'─'*60}")

    try:
        with open(path) as fh:
            data = json.load(fh)
    except Exception as e:
        print(f"  读取失败: {e}")
        return

    print(f"  顶层类型: {type(data).__name__}")

    if isinstance(data, list):
        print(f"  元素数量: {len(data)}")
        if not data:
            return
        item = data[0]
        if isinstance(item, dict):
            print(f"  字段: {list(item.keys())}")
            # Type distribution
            if "type" in item:
                types = Counter(d.get("type", "?") for d in data)
                print(f"  type 分布: {dict(types)}")
            # Show first 3 text items
            shown = 0
            for d in data:
                if isinstance(d, dict) and d.get("text", "").strip():
                    lv = d.get("text_level", d.get("level", "?"))
                    print(f"  [{d.get('type','?')} lv{lv} p{d.get('page_idx','?')}] "
                          f"{d['text'][:80]!r}")
                    shown += 1
                    if shown >= 5:
                        break

    elif isinstance(data, dict):
        print(f"  顶层键: {list(data.keys())[:10]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/inspect_mineru_output.py <mineru_output_dir>")
        sys.exit(1)
    inspect_directory(Path(sys.argv[1]).expanduser().resolve())
