#!/usr/bin/env python3
"""Check if an industry standard file can be parsed — no Neo4j write.

Usage:
  python scripts/check_standard_file.py --file data/standards/example.md
  python scripts/check_standard_file.py --file data/standards/pdf/example.pdf --save-intermediate
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.standard.parser import parse_standard_document
from src.graph.standard.extractor import extract_from_standard

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def check_file(file_path: Path, title: str = "", code: str = "",
               industry: str = "", save_intermediate: bool = False) -> dict:
    """Check if a standard file can be parsed.

    Returns a dict with check results suitable for display.
    """
    result = {
        "file": str(file_path),
        "file_type": file_path.suffix.lower(),
        "exists": file_path.exists(),
        "read_ok": False,
        "text_length": 0,
        "is_scanned": False,
        "chapters": 0,
        "clauses": 0,
        "requirements": 0,
        "indicators": 0,
        "terms": 0,
        "methods": 0,
        "objects": 0,
        "error": "",
        "suggestion": "",
    }

    if not result["exists"]:
        result["error"] = f"文件不存在: {file_path}"
        result["suggestion"] = "检查文件路径是否正确"
        return result

    # Read text
    if file_path.suffix.lower() == ".pdf":
        try:
            from src.graph.standard.pdf_parser import parse_pdf
            pdf_result = parse_pdf(str(file_path))
            if pdf_result["error"]:
                result["error"] = pdf_result["error"]
                result["suggestion"] = "请安装 PyMuPDF: pip install pymupdf"
                return result
            text = pdf_result["text"]
            result["is_scanned"] = pdf_result["is_scanned"]
            if pdf_result["is_scanned"]:
                result["suggestion"] = (
                    "该 PDF 可能是扫描版，仅含少量可提取文字。"
                    "建议先使用 OCR 工具（如 Tesseract）将扫描页转为文字再导入。"
                )
            if save_intermediate and text:
                out_dir = Path("data/standards/converted")
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{file_path.stem}.txt"
                out_path.write_text(text, encoding="utf-8")
                print(f"Intermediate text saved to {out_path}")
        except ImportError:
            result["error"] = "PyMuPDF (fitz) 未安装。pip install pymupdf"
            result["suggestion"] = "安装 PyMuPDF 或使用文本格式 (.md/.txt)"
            return result
    else:
        text = file_path.read_text(encoding="utf-8")

    result["read_ok"] = True
    result["text_length"] = len(text)

    if not text.strip():
        result["error"] = "文件为空或无法提取文字"
        result["suggestion"] = "检查文件内容"
        return result

    # Parse
    try:
        doc, chapters, clauses = parse_standard_document(
            text, code=code or file_path.stem,
            title=title or file_path.stem, industry=industry or "unknown",
            source_file=str(file_path),
        )
        result["chapters"] = len(chapters)
        result["clauses"] = len(clauses)
    except Exception as exc:
        result["error"] = f"解析失败: {exc}"
        result["suggestion"] = "检查文件格式是否符合要求（见文档第4节）"
        return result

    # Extract
    try:
        extraction = extract_from_standard(clauses)
        result["requirements"] = len(extraction.get("requirements", []))
        result["indicators"] = len(extraction.get("indicators", []))
        result["terms"] = len(extraction.get("terms", []))
        result["methods"] = len(extraction.get("methods", []))
        result["objects"] = len(extraction.get("objects", []))
    except Exception as exc:
        result["error"] = f"知识抽取失败: {exc}"
        result["suggestion"] = "文件可解析，但知识抽取异常。检查条款内容格式。"
        return result

    # Success
    if not result["suggestion"]:
        total_extracted = (result["requirements"] + result["indicators"] +
                          result["terms"] + result["methods"] + result["objects"])
        if total_extracted == 0:
            result["suggestion"] = (
                "文件解析成功，但未抽取出结构化的知识（要求/指标/术语等）。"
                '可能的原因：条款中不包含「应/宜/可」等规范性用语。'
                "可以继续导入，但图谱中可能缺少细节节点。"
            )
        else:
            result["suggestion"] = (
                "文件检查通过！可以执行正式导入：\n"
                f"  python scripts/import_standard_graph.py "
                f"--file {file_path} "
                f"--code \"{code or 'YOUR_CODE'}\" "
                f"--title \"{title or 'YOUR_TITLE'}\" "
                f"--industry \"{industry or 'YOUR_INDUSTRY'}\""
            )

    return result


def main():
    ap = argparse.ArgumentParser(
        description="Check if a standard file can be parsed (no Neo4j write)")
    ap.add_argument("--file", required=True,
                    help="Path to .pdf, .md, or .txt file")
    ap.add_argument("--code", default="",
                    help="Standard code (optional for checking)")
    ap.add_argument("--title", default="",
                    help="Standard title (optional for checking)")
    ap.add_argument("--industry", default="",
                    help="Industry domain (optional for checking)")
    ap.add_argument("--save-intermediate", action="store_true",
                    help="For PDF: save extracted text to data/standards/converted/")

    args = ap.parse_args()

    result = check_file(
        file_path=Path(args.file).expanduser().resolve(),
        title=args.title,
        code=args.code,
        industry=args.industry,
        save_intermediate=args.save_intermediate,
    )

    print()
    print("=" * 60)
    print("标准文件检查报告")
    print("=" * 60)
    print(f"  文件路径:     {result['file']}")
    print(f"  文件类型:     {result['file_type']}")
    print(f"  文件存在:     {'是' if result['exists'] else '否'}")
    print(f"  读取成功:     {'是' if result['read_ok'] else '否'}")
    print(f"  文本长度:     {result['text_length']} 字符")

    if result["file_type"] == ".pdf":
        print(f"  疑似扫描版:   {'是 ⚠️' if result['is_scanned'] else '否'}")

    if result["error"]:
        print(f"  错误:         {result['error']}")
        print(f"  建议:         {result['suggestion']}")
        return

    print(f"  章节数量:     {result['chapters']}")
    print(f"  条款数量:     {result['clauses']}")
    print(f"  抽取要求:     {result['requirements']}")
    print(f"  抽取指标:     {result['indicators']}")
    print(f"  抽取术语:     {result['terms']}")
    print(f"  抽取方法:     {result['methods']}")
    print(f"  抽取对象:     {result['objects']}")

    print()
    print(f"  建议操作:     {result['suggestion']}")
    print()


if __name__ == "__main__":
    main()
