#!/usr/bin/env python3
"""Find a standard PDF by code or title in common locations.

Usage:
  python scripts/find_standard_pdf.py --code "GB/T 38509-2020"
  python scripts/find_standard_pdf.py --title "滑坡防治设计规范"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SEARCH_DIRS = [
    Path.home() / "Documents",
    Path.home() / "Documents" / "Codex",
]


def _normalize(s: str) -> str:
    """Normalize a string for fuzzy matching: lowercase, strip punctuation."""
    return re.sub(r'[\s\-/\.:：；\+—–]+', '', s.lower())


def find_pdf(code: str = "", title: str = "") -> list[Path]:
    """Search for PDF files matching code or title.

    Fuzzy matching: strips spaces/punctuation before comparison.
    """
    results: list[Path] = []
    code_norm = _normalize(code) if code else ""
    title_norm = _normalize(title) if title else ""

    # Build search terms
    terms: list[str] = []
    if code:
        terms.append(code_norm)
        # Extract numeric part for extra matching
        nums = re.findall(r'\d{4,}', code)
        terms.extend(nums)

    for search_dir in SEARCH_DIRS:
        if not search_dir.exists():
            continue
        for pdf_path in search_dir.rglob("*.pdf"):
            name_norm = _normalize(pdf_path.stem)
            # Match by code
            if code_norm and code_norm in name_norm:
                results.append(pdf_path)
                continue
            # Match by numeric part
            for num in terms:
                if num in name_norm and num not in code_norm:
                    results.append(pdf_path)
                    break
            else:
                # Match by title (fuzzy)
                if title_norm and len(title_norm) > 2 and title_norm in name_norm:
                    results.append(pdf_path)

    # Prefer shorter paths (closer to Documents root over deep paths)
    results.sort(key=lambda p: (len(p.parts), str(p)))
    return results


def main():
    ap = argparse.ArgumentParser(description="Find standard PDF files")
    ap.add_argument("--code", default="", help="Standard code (e.g. GB/T 38509-2020)")
    ap.add_argument("--title", default="", help="Standard title (fuzzy match)")

    args = ap.parse_args()
    if not args.code and not args.title:
        ap.error("Must specify --code or --title")

    results = find_pdf(code=args.code, title=args.title)

    if not results:
        print("未找到匹配的 PDF 文件。")
        print(f"  搜索目录: {[str(d) for d in SEARCH_DIRS]}")
        print(f"  搜索条件: code={args.code!r} title={args.title!r}")
    else:
        print(f"找到 {len(results)} 个 PDF:")
        for p in results:
            size_kb = p.stat().st_size / 1024 if p.exists() else 0
            print(f"  {p}  ({size_kb:.0f} KB)")

    # Return best match as the first one
    if results:
        best = results[0]
        print()
        print(f"推荐使用:")
        print(f"  python scripts/import_standard_graph.py \\")
        print(f"    --file \"{best}\" \\")
        print(f"    --code \"{args.code}\" \\")
        print(f"    --title \"{args.title}\" \\")
        print(f"    --industry \"geological_disaster\" \\")
        print(f"    --dry-run")


if __name__ == "__main__":
    main()
