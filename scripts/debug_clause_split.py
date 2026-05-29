#!/usr/bin/env python3
"""Debug clause splitting for MinerU JSON parsing.

Usage:
  python scripts/debug_clause_split.py \\
    --input "<mineru_dir>" \\
    --code "GB/T 38509-2020"
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.standard.mineru_parser import (
    find_content_list, parse_from_mineru_json,
    load_mineru_blocks, _split_merged_clauses,
)


def main():
    ap = argparse.ArgumentParser(description="Debug clause splitting")
    ap.add_argument("--input", required=True, help="MinerU output directory")
    ap.add_argument("--code", default="", help="Standard code")
    args = ap.parse_args()

    input_dir = Path(args.input).expanduser().resolve()
    if not input_dir.exists():
        print(f"Directory not found: {input_dir}")
        sys.exit(1)

    json_path = find_content_list(str(input_dir))
    if not json_path:
        print("No content_list.json found")
        sys.exit(1)

    print(f"JSON: {json_path}")

    # Load blocks
    blocks = load_mineru_blocks(str(json_path))
    content_blocks = [b for b in blocks if b.get("type") == "text" and b["text"].strip()]
    print(f"Total content blocks: {len(content_blocks)}")

    # Find longest paragraphs (content assigned to clauses)
    doc, chapters, clauses = parse_from_mineru_json(
        str(json_path), code=args.code, title="Debug", industry="debug",
    )

    # Before split stats
    long_clauses = sorted(clauses, key=lambda c: len(c.content or ""), reverse=True)
    print(f"\n=== 最长 10 个 Clause (拆分后) ===")
    for i, cl in enumerate(long_clauses[:10]):
        content_len = len(cl.content or "")
        preview = (cl.content or "")[:120].replace("\n", "\\n")
        print(f"  {i+1}. [{cl.clause_number}] ({content_len} chars): {preview}...")

    # Chapter list
    print(f"\n=== Chapters ({len(chapters)}) ===")
    for ch in chapters:
        print(f"  [{ch.chapter_number}] {ch.title[:60]}")

    # Detect suspicious chapters (beyond 15)
    if len(chapters) > 15:
        extra = chapters[15:]
        print(f"\n=== 超出 15 的额外 Chapter ({len(extra)}) ===")
        for ch in extra:
            print(f"  [{ch.chapter_number}] {ch.title[:60]}")

    # Clause stats
    print(f"\n=== Clause 统计 ===")
    print(f"  总数: {len(clauses)}")

    # Check for duplicates
    nums = [cl.clause_number for cl in clauses]
    dupes = {n: c for n, c in Counter(nums).items() if c > 1}
    if dupes:
        print(f"  重复编号: {dupes}")

    # Check for content extremes
    short = [cl for cl in clauses if len(cl.content or "") < 10]
    if short:
        print(f"  偏短 Clause (<10 chars): {len(short)}")
        for cl in short[:5]:
            print(f"    [{cl.clause_number}] {cl.content!r}")

    print(f"\n  前 50 个 Clause:")
    for cl in clauses[:50]:
        title_preview = (cl.title or "")[:60]
        print(f"    [{cl.clause_number}] {title_preview}")


if __name__ == "__main__":
    main()
