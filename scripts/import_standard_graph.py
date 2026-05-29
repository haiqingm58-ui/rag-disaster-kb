#!/usr/bin/env python3
"""Import an industry standard document into the Neo4j knowledge graph.

Supports .pdf, .md, .txt files.

Usage:
  # Markdown/txt
  python scripts/import_standard_graph.py \\
      --file data/standards/example.md \\
      --code "DZ/T 0286-2015" \\
      --title "地质灾害危险性评估规范" \\
      --industry "geological_disaster"

  # PDF
  python scripts/import_standard_graph.py \\
      --file data/standards/pdf/example.pdf \\
      --code "DZ/T 0286-2015" \\
      --title "地质灾害危险性评估规范" \\
      --industry "geological_disaster" \\
      --save-intermediate

  # Dry run (no Neo4j write)
  python scripts/import_standard_graph.py \\
      --file data/standards/example.md \\
      --code "DZ/T XXXX-XXXX" \\
      --title "测试" \\
      --industry "test" \\
      --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.common.neo4j_client import check_connection
from src.graph.standard.parser import parse_standard_document
from src.graph.standard.extractor import StandardGraphExtractor
from src.graph.standard.writer import init_schema, write_standard_graph

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _resolve_auto_input(file_path: Path, args) -> tuple[Path, str, str, any, list, list]:
    """Auto-detect best input source: PDF > MinerU JSON > MinerU MD > raw MD."""
    suffix = file_path.suffix.lower()

    # If it's a directory, look for MinerU JSON
    if file_path.is_dir():
        text, source, doc, chs, cls = _resolve_mineru_json(file_path, args)
        if text and source != "none":
            return file_path, text, source, doc, chs, cls
        logger.error("Directory %s does not contain usable MinerU JSON", file_path)
        sys.exit(1)

    # If it's a PDF
    if suffix == ".pdf":
        from src.graph.standard.pdf_parser import assess_pdf_quality
        quality = assess_pdf_quality(str(file_path))
        if quality["quality"] == "ok":
            text = _read_file(file_path, save_intermediate=args.save_intermediate)
            return file_path, text, "pdf", None, [], []
        else:
            logger.warning("PDF quality issue: %s — trying MinerU JSON", quality["reason"])
            text, source, doc, chs, cls = _resolve_mineru_json(file_path, args)
            if text and source != "none":
                return file_path, text, source, doc, chs, cls
            logger.warning("No MinerU JSON found; using raw PDF text (may be garbled)")
            text = _read_file(file_path, save_intermediate=args.save_intermediate)
            return file_path, text, "pdf_bad_cmap", None, [], []

    # MD or txt
    text = _read_file(file_path, save_intermediate=args.save_intermediate)
    return file_path, text, "md", None, [], []


def _resolve_mineru_json(file_path: Path, args) -> tuple[str, str, list, list, list]:
    """Try to parse MinerU content_list.json. Returns (text, source, doc, chapters, clauses)."""
    try:
        from src.graph.standard.mineru_parser import (
            find_content_list, parse_from_mineru_json,
        )

        search_dir = file_path
        if file_path.is_file():
            stem = file_path.stem
            mineru_base = file_path.resolve().parent.parent.parent.parent
            for pattern in ["converted_markdown", "auto"]:
                candidate = mineru_base / pattern / stem
                if candidate.exists():
                    search_dir = candidate
                    break
            if not search_dir.exists() or search_dir == file_path:
                parent = file_path.parent
                for d in parent.iterdir():
                    if d.is_dir() and stem.replace("+", "") in d.name.replace("+", ""):
                        search_dir = d
                        break

        if not search_dir.is_dir() if isinstance(search_dir, Path) else not Path(str(search_dir)).is_dir():
            return "", "none", None, [], []

        json_path = find_content_list(str(search_dir))
        if not json_path:
            return "", "none", None, [], []

        logger.info("Found MinerU content_list: %s", json_path)
        doc, chapters, clauses = parse_from_mineru_json(
            str(json_path),
            code=args.code, title=args.title, industry=args.industry,
            source_file=str(json_path), issuing_body=args.issuing_body,
        )

        if not chapters and not clauses:
            return "", "none", None, [], []

        # Reconstruct text for extraction
        text_parts = []
        for ch in chapters:
            text_parts.append(f"{ch.chapter_number} {ch.title}")
        for cl in clauses:
            text_parts.append(f"{cl.clause_number} {cl.content}")

        return "\n\n".join(text_parts), "mineru_json", doc, chapters, clauses
    except Exception as exc:
        logger.warning("MinerU JSON resolution failed: %s", exc)
        return "", "none", None, [], []


def _read_file(file_path: Path, save_intermediate: bool = False) -> str:
    """Read text from a file, routing through pdf_parser for .pdf files.

    Args:
        file_path: Path to the input file.
        save_intermediate: If True and file is PDF, save extracted text.

    Returns:
        Extracted text string.
    """
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        from src.graph.standard.pdf_parser import parse_pdf

        result = parse_pdf(str(file_path))
        if result["error"]:
            logger.error("PDF parse error: %s", result["error"])
            sys.exit(1)

        if result["is_scanned"]:
            logger.warning(
                "该 PDF 可能是扫描版（仅 %d/%d 页有可提取文字），"
                "需要 OCR 后再导入。继续尝试使用已提取的文字…",
                sum(1 for p in result["pages"] if p["text"].strip()),
                result["total_pages"],
            )

        logger.info("PDF: %d pages, %d chars extracted",
                    result["total_pages"], len(result["text"]))

        if save_intermediate and result["text"]:
            _save_intermediate_text(file_path, result["text"])

        return result["text"]

    else:
        # .md or .txt
        text = file_path.read_text(encoding="utf-8")
        logger.info("Read %d chars from %s", len(text), file_path)
        return text


def _save_intermediate_text(original_path: Path, text: str) -> None:
    """Save extracted text as .txt for inspection."""
    out_dir = Path("data/standards/converted")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{original_path.stem}.txt"
    out_path.write_text(text, encoding="utf-8")
    logger.info("Intermediate text saved to %s", out_path)


def _print_dry_run(doc, chapters, clauses, extraction):
    """Enhanced dry-run output with full extraction statistics and samples."""
    print()
    print("=" * 60)
    print("DRY RUN — not writing to Neo4j")
    print("=" * 60)
    print(f"  标准编号:     {doc.code}")
    print(f"  标准标题:     {doc.title}")
    print(f"  行业:         {doc.industry}")
    print(f"  发布机构:     {doc.issuing_body or '(未指定)'}")
    print(f"  状态:         {doc.status.value}")
    print(f"  来源文件:     {doc.source_file}")
    print(f"  Standard ID:  {doc.standard_id}")
    print()

    print(f"  章节数量:     {len(chapters)}")
    for ch in chapters[:5]:
        print(f"    [{ch.chapter_number}] {ch.title}")
    if len(chapters) > 5:
        print(f"    ... 及另外 {len(chapters) - 5} 个章节")
    print()

    print(f"  条款数量:     {len(clauses)}")
    for cl in clauses[:5]:
        preview = (cl.title or cl.content)[:80]
        print(f"    [{cl.clause_number}] {preview}")
    if len(clauses) > 5:
        print(f"    ... 及另外 {len(clauses) - 5} 个条款")
    print()

    stats_items = [
        ("术语 (Terms)", "terms", "name"),
        ("规范要求 (Requirements)", "requirements", "text"),
        ("指标参数 (Indicators)", "indicators", "name"),
        ("方法 (Methods)", "methods", "name"),
        ("适用对象 (Objects)", "objects", "name"),
    ]

    for label, key, attr in stats_items:
        items = extraction.get(key, [])
        print(f"  {label}:    {len(items)}")
        for item in items[:5]:
            val = getattr(item, attr, str(item))
            print(f"    - {val[:100]}")
        if len(items) > 5:
            print(f"    ... 及另外 {len(items) - 5} 项")
        print()


def main():
    ap = argparse.ArgumentParser(description="Import industry standard into Neo4j")
    ap.add_argument("--file", required=True,
                    help="Path to .pdf, .md, or .txt file")
    ap.add_argument("--code", required=True,
                    help="Standard code (e.g. DZ/T 0286-2015)")
    ap.add_argument("--title", required=True, help="Standard title")
    ap.add_argument("--industry", required=True, help="Industry domain")
    ap.add_argument("--issuing-body", default="", help="Issuing organization")
    ap.add_argument("--max-chapter-depth", type=int, default=1,
                    help="Heading levels treated as chapters (default: 1)")
    ap.add_argument("--skip-extract", action="store_true",
                    help="Skip knowledge extraction (only parse structure)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse and extract but do not write to Neo4j")
    ap.add_argument("--save-intermediate", action="store_true",
                    help="For PDF: save extracted text to data/standards/converted/")
    ap.add_argument("--ner-model-type", default="rule",
                    choices=["rule", "bilstm_crf", "bert_bilstm_crf"],
                    help="NER model type (default: rule)")
    ap.add_argument("--ner-model-path", default=None,
                    help="Path to NER model weights (.pt file)")
    ap.add_argument("--re-model-type", default="rule",
                    choices=["rule", "casrel", "prgc"],
                    help="Relation extraction model type (default: rule)")
    ap.add_argument("--re-model-path", default=None,
                    help="Path to RE model weights (.pt file)")
    ap.add_argument("--force", action="store_true",
                    help="Skip quality checks and force import")
    ap.add_argument("--no-quality-check", action="store_true",
                    help="Disable the quality gate (same as --force)")
    ap.add_argument("--input-format", default="auto",
                    choices=["auto", "pdf", "mineru_md", "mineru_json"],
                    help="Input format (default: auto — try PDF first, then MinerU JSON/MD)")

    args = ap.parse_args()

    # Resolve input: PDF, MinerU directory, or Markdown
    file_path = Path(args.file).expanduser().resolve()
    used_source = "unknown"
    mineru_doc = None
    mineru_chapters = []
    mineru_clauses = []

    if args.input_format == "auto":
        file_path, text, used_source, mineru_doc, mineru_chapters, mineru_clauses = \
            _resolve_auto_input(file_path, args)
    elif args.input_format == "mineru_json":
        text, used_source, mineru_doc, mineru_chapters, mineru_clauses = \
            _resolve_mineru_json(file_path, args)
    elif file_path.suffix.lower() == ".pdf":
        text = _read_file(file_path, save_intermediate=args.save_intermediate)
        used_source = "pdf"
    else:
        text = _read_file(file_path, save_intermediate=args.save_intermediate)
        used_source = "md" if file_path.suffix == ".md" else "txt"

    if not text or not text.strip():
        logger.error("未能从文件中提取到文字内容。")
        sys.exit(1)

    logger.info("Using source: %s (%s)", used_source, file_path.name)

    if not text or not text.strip():
        logger.error(
            "未能从文件中提取到文字内容。"
            "如果文件是 PDF，可能是扫描版，需要 OCR 后再导入。"
        )
        sys.exit(1)

    # Check Neo4j (unless dry-run)
    if not args.dry_run:
        conn = check_connection()
        if not conn["ok"]:
            logger.error(conn["error"])
            sys.exit(1)
        logger.info("Neo4j: %s", conn["uri"])

    # Parse — use MinerU objects directly if available, otherwise run normal parser
    if used_source == "mineru_json" and mineru_doc is not None:
        doc = mineru_doc
        chapters = mineru_chapters
        clauses = mineru_clauses
        logger.info("MinerU JSON: %d chapters, %d clauses", len(chapters), len(clauses))
    else:
        doc, chapters, clauses = parse_standard_document(
            text,
            code=args.code,
            title=args.title,
            industry=args.industry,
            source_file=str(file_path),
            issuing_body=args.issuing_body,
            max_chapter_depth=args.max_chapter_depth,
        )
        logger.info("Parsed: %d chapters, %d clauses", len(chapters), len(clauses))

    # Extract
    if args.skip_extract:
        extraction = {
            "requirements": [], "indicators": [], "terms": [],
            "methods": [], "objects": [],
        }
    else:
        extractor = StandardGraphExtractor(
            ner_model_type=args.ner_model_type,
            ner_model_path=args.ner_model_path,
            re_model_type=args.re_model_type,
            re_model_path=args.re_model_path,
        )
        extraction = extractor.extract_from_standard(clauses)
        logger.info(
            "Extracted: %d requirements, %d indicators, %d terms, %d methods, %d objects",
            len(extraction["requirements"]), len(extraction["indicators"]),
            len(extraction["terms"]), len(extraction["methods"]),
            len(extraction["objects"]),
        )

    if args.dry_run:
        _print_dry_run(doc, chapters, clauses, extraction)
        return

    # Quality gate (skip with --force or --no-quality-check)
    if not args.force and not args.no_quality_check:
        issues = _check_quality(doc, chapters, clauses, extraction)
        errors = [i for i in issues if i.startswith("ERROR")]
        warnings = [i for i in issues if i.startswith("WARNING")]
        if errors:
            print()
            print("=" * 60)
            print("⚠️  质量检查未通过 — 阻止写入 Neo4j")
            print("=" * 60)
            for e in errors:
                print(f"  ❌ {e}")
            if warnings:
                print()
                if warnings:
                    for w in warnings:
                        print(f"  ⚠️  {w}")
            print()
            print("建议:")
            print("  1. 先运行 --dry-run 查看解析结果")
            print("  2. 检查输入文件格式")
            print("  3. 如果确认无误，使用 --force 跳过质量检查")
            return
        elif warnings:
            print()
            print("=" * 60)
            print("⚠️  质量警告（不阻止导入）")
            print("=" * 60)
            for w in warnings:
                print(f"  ⚠️  {w}")
            print()

    # Write to Neo4j
    init_schema()
    stats = write_standard_graph(
        doc=doc, chapters=chapters, clauses=clauses,
        terms=extraction["terms"],
        requirements=extraction["requirements"],
        indicators=extraction["indicators"],
        methods=extraction["methods"],
        objects=extraction["objects"],
    )

    print()
    print("=" * 50)
    print("Import complete")
    print("=" * 50)
    print(f"  Standard:     {doc.code} — {doc.title}")
    print(f"  Standard ID:  {doc.standard_id}")
    print(f"  Chapters:     {stats['chapters']}")
    print(f"  Clauses:      {stats['clauses']}")
    print(f"  Terms:        {stats['terms']}")
    print(f"  Requirements: {stats['requirements']}")
    print(f"  Indicators:   {stats['indicators']}")
    print(f"  Methods:      {stats['methods']}")
    print(f"  Objects:      {stats['objects']}")
    print(f"  Relationships:{stats['relationships']}")
    print()
    print("Query in Neo4j Browser:")
    print(f"  MATCH (s:StandardDocument {{standard_id: '{doc.standard_id}'}})-[*1..2]->(n)")
    print(f"  RETURN s, n")


def _check_quality(doc, chapters, clauses, extraction) -> list[str]:
    """Run quality checks before writing to Neo4j. Returns list of issues.

    Issues are classified as ERROR (blocks import) or WARNING (informational).
    """
    issues = []

    n_chapters = len(chapters)
    n_clauses = len(clauses)
    n_terms = len(extraction.get("terms", []))
    n_requirements = len(extraction.get("requirements", []))
    n_indicators = len(extraction.get("indicators", []))

    top_level_numbers: set[str] = set()
    for cl in clauses:
        num = cl.clause_number.split(".")[0]
        top_level_numbers.add(num)
    expected_chapters = len(top_level_numbers)

    # ═══ ERROR-level checks (block import) ═══

    if n_chapters > 50:
        issues.append(
            f"ERROR: Chapter 数量异常 ({n_chapters})，预期约 {expected_chapters} 个。"
            "可能是页眉页脚、目录或表格被误识别为 Chapter。"
        )

    if n_clauses == 0:
        issues.append("ERROR: 未解析出任何条款 (Clauses=0)。")

    # Ratio: Requirements vs Clauses
    if n_clauses > 0 and n_requirements > n_clauses * 5:
        ratio = n_requirements / n_clauses
        issues.append(
            f"ERROR: Requirements/Clauses 比例过高 ({n_requirements}/{n_clauses} = {ratio:.1f})。"
            "文本可能被错误切分，每句都被当成了独立条款和强制要求。"
        )

    # Ratio: Indicators vs Clauses
    if n_clauses > 0 and n_indicators > n_clauses * 2:
        ratio = n_indicators / n_clauses
        issues.append(
            f"ERROR: Indicators/Clauses 比例过高 ({n_indicators}/{n_clauses} = {ratio:.1f})。"
            "大量误识别为指标，请检查输入文件。"
        )

    # Ratio: Clauses vs Chapters (too few clauses for many chapters)
    if n_chapters > 10 and n_clauses < n_chapters * 3:
        issues.append(
            f"ERROR: Clauses 数量 ({n_clauses}) 远少于 Chapters ({n_chapters}) 的 3 倍。"
            "结构异常 — Chapter 可能包含大量误识别。"
        )

    # ═══ WARNING-level checks (inform but don't block) ═══

    has_term_chapter = any(
        "术语" in (ch.title or "") for ch in chapters
    )
    if has_term_chapter and n_terms == 0:
        issues.append(
            f"WARNING: 存在「术语和定义」章节但未抽取到术语。"
        )

    if n_requirements == 0 and n_indicators == 0:
        issues.append(
            "WARNING: 未抽取到任何规范要求或指标参数。"
        )

    if n_chapters > expected_chapters * 3 and expected_chapters > 0:
        issues.append(
            f"WARNING: Chapter 数量 ({n_chapters}) 远大于一级编号数 ({expected_chapters})。"
        )

    # ═══ Check for suspicious chapter titles ═══
    suspicious = _find_suspicious_chapter_titles(chapters)
    if suspicious:
        issues.append(
            f"ERROR: 发现 {len(suspicious)} 个可疑 Chapter 标题:"
        )
        for s in suspicious[:5]:
            issues.append(f"  - {s}")

    return issues


def _find_suspicious_chapter_titles(chapters) -> list[str]:
    """Return list of chapter titles that look suspicious."""
    import re
    suspicious = []
    patterns = [
        r"^\d*\s*(?:mm|cm|m|km|kPa|MPa|GPa|Pa|N|kN|%|°|℃)\s*[。；，]?$",
        r"[；;]$",                           # Ends with Chinese/English semicolon
        r"[。，,]$",                          # Ends with period/comma (not title-like)
        r"^[—\-–]{2,}",                      # Starts with dash
        r"（(?:mm|cm|m|km|kPa|MPa|kN|%)）",   # Unit in parentheses
        r"单位为", r"式中", r"见表", r"见图",
    ]
    for ch in chapters:
        title = ch.title.strip()
        for pat in patterns:
            if re.search(pat, title):
                suspicious.append(f"[{ch.chapter_number}] {title[:60]}")
                break
    return suspicious


if __name__ == "__main__":
    main()
