#!/usr/bin/env python3
"""Compare PDF vs MinerU Markdown parsing results for the same standard.

Usage:
  python scripts/compare_standard_inputs.py \\
    --pdf "path/to/standard.pdf" \\
    --md "path/to/mineru_output.md" \\
    --code "GB/T 32864-2016" \\
    --title "滑坡防治工程勘查规范"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.standard.parser import parse_standard_document
from src.graph.standard.extractor import extract_from_standard


def _parse_file(file_path: Path) -> dict:
    """Parse a file and return stats."""
    if file_path.suffix.lower() == ".pdf":
        from src.graph.standard.pdf_parser import parse_pdf
        result = parse_pdf(str(file_path))
        if result["error"]:
            return {"error": result["error"]}
        text = result["text"]
    else:
        text = file_path.read_text(encoding="utf-8")

    doc, chapters, clauses = parse_standard_document(
        text, code="COMPARE", title="Compare", industry="compare",
        source_file=str(file_path),
    )
    extraction = extract_from_standard(clauses)

    return {
        "chapters": len(chapters),
        "clauses": len(clauses),
        "terms": len(extraction.get("terms", [])),
        "requirements": len(extraction.get("requirements", [])),
        "indicators": len(extraction.get("indicators", [])),
        "methods": len(extraction.get("methods", [])),
        "objects": len(extraction.get("objects", [])),
        "chapter_list": [(ch.chapter_number, ch.title[:60]) for ch in chapters[:20]],
        "term_list": [t.name for t in extraction.get("terms", [])[:20]],
        "clause_list": [(cl.clause_number, (cl.title or cl.content)[:60])
                       for cl in clauses[:20]],
        "error": extraction.get("error", ""),
    }


def main():
    ap = argparse.ArgumentParser(
        description="Compare PDF vs MinerU Markdown parsing results")
    ap.add_argument("--pdf", required=True, help="Path to PDF file")
    ap.add_argument("--md", required=True, help="Path to MinerU Markdown file")
    ap.add_argument("--code", default="COMPARE", help="Standard code")
    ap.add_argument("--title", default="", help="Standard title")

    args = ap.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    md_path = Path(args.md).expanduser().resolve()

    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}")
        sys.exit(1)
    if not md_path.exists():
        print(f"MD not found: {md_path}")
        sys.exit(1)

    print("解析中...")
    pdf_stats = _parse_file(pdf_path)
    md_stats = _parse_file(md_path)

    def _val(key):
        p = pdf_stats.get(key, 0)
        m = md_stats.get(key, 0)
        return p, m

    print()
    print("=" * 70)
    print(f"PDF vs MinerU Markdown 对比: {args.code}")
    print("=" * 70)
    print(f"{'指标':<20} {'PDF':>10} {'Markdown':>10} {'差异':>10}")
    print("-" * 50)

    for label, key in [
        ("Chapters", "chapters"), ("Clauses", "clauses"),
        ("Terms", "terms"), ("Requirements", "requirements"),
        ("Indicators", "indicators"), ("Methods", "methods"),
        ("Objects", "objects"),
    ]:
        p, m = _val(key)
        diff = m - p
        flag = " ⚠️" if abs(diff) > max(p * 0.5, 5) else ""
        print(f"{label:<20} {p:>10} {m:>10} {diff:>+10}{flag}")

    print()
    print("PDF 前 20 个 Chapter:")
    for num, title in pdf_stats.get("chapter_list", []):
        print(f"  [{num}] {title}")

    print()
    print("Markdown 前 20 个 Chapter:")
    for num, title in md_stats.get("chapter_list", []):
        print(f"  [{num}] {title}")

    print()
    print("PDF 前 20 个 Term:")
    for name in pdf_stats.get("term_list", []):
        print(f"  - {name}")

    print()
    print("Markdown 前 20 个 Term:")
    for name in md_stats.get("term_list", []):
        print(f"  - {name}")

    # Recommendation
    print()
    print("=" * 70)
    pdf_ch = pdf_stats.get("chapters", 0)
    md_ch = md_stats.get("chapters", 0)
    if md_ch > 50 and pdf_ch < 30:
        print("推荐: 使用 PDF 导入（Markdown Chapter 数量异常偏高）")
    elif pdf_ch > md_ch * 1.5:
        print("推荐: 使用 Markdown 导入")
    else:
        print("推荐: 两者均可，优先使用 PDF")
    print("=" * 70)


if __name__ == "__main__":
    main()
