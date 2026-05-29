"""Parse MinerU content_list.json into structured Chapter/Clause objects.

Uses MinerU's type/text_level/page_idx fields to identify headings, paragraphs,
and tables. Handles PDFs where direct PyMuPDF extraction fails (bad CMap).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from .models import StandardDocument, Chapter, Clause, StandardStatus
from ..common.utils import new_id

logger = logging.getLogger(__name__)

# Clause number patterns: "4.1 Title", "4.1.1 Title", "10.2.3 Title"
# Also matches "1范围" (no space between number and Chinese text)
CLAUSE_NUM_RE = re.compile(r'^(\d+(?:\.\d+)*)[\s　]+(.+)$')
CLAUSE_NUM_NO_SPACE_RE = re.compile(r'^(\d+)([一-鿿][\w一-鿿]{0,80})$')

# Non-clause patterns to exclude
NON_CLAUSE_RE = re.compile(
    r'^(?:表\s*\d|图\s*\d|式\s*[（(]\d|'
    r'附录\s*[A-Z]|附录[A-Z]|'
    r'目\s*次|目\s*录|前\s*言|引\s*言)',
)


def find_content_list(dir_path: str) -> Optional[Path]:
    """Find the best content_list JSON in a MinerU output directory."""
    base = Path(dir_path)
    # Search recursively
    candidates = list(base.rglob("*content_list*.json"))
    if not candidates:
        candidates = list(base.rglob("*_middle.json"))
    if not candidates:
        return None
    # Prefer v2, then shorter names
    candidates.sort(key=lambda p: ("v2" not in p.name, len(p.name)))
    return candidates[0]


def load_mineru_blocks(json_path: str) -> list[dict]:
    """Load MinerU content blocks from JSON (v1 or v2 format)."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        if isinstance(data, dict) and "pdf_info" in data:
            logger.warning("middle.json format not yet supported")
        return []

    if not data:
        return []

    # Detect format: v1 has flat list of dicts with 'type' and 'text'
    first = data[0]
    if isinstance(first, dict) and "text" in first:
        return data

    # v2 format: list of pages, each page is a list of blocks
    if isinstance(first, list):
        return _flatten_v2(data)

    return []


def _is_math_block(text: str) -> bool:
    """Detect LaTeX math formulas extracted as text."""
    return bool(re.search(r'[\\{}^~]|\\mathrm|\\pi|\\alpha|\\times|\\circ|\\sim', text))


def _flatten_v2(pages: list[list[dict]]) -> list[dict]:
    """Convert MinerU v2 nested format to flat v1-like block list."""
    blocks: list[dict] = []

    for page_idx, page_blocks in enumerate(pages):
        for block in page_blocks:
            btype = block.get("type", "text")
            content = block.get("content", {})

            if btype == "title":
                tc = content.get("title_content", [])
                level = content.get("level", 1)
                for item in tc:
                    if item.get("type") == "text":
                        blocks.append({
                            "type": "text",
                            "text": item.get("content", ""),
                            "text_level": level,
                            "page_idx": page_idx,
                        })
            elif btype == "paragraph":
                pc = content.get("paragraph_content", [])
                for item in pc:
                    blocks.append({
                        "type": "text",
                        "text": item.get("content", ""),
                        "text_level": item.get("level", 1),
                        "page_idx": page_idx,
                    })
            elif btype == "text_block":
                for item in content.get("sub_text", []):
                    blocks.append({
                        "type": "text",
                        "text": item.get("content", ""),
                        "text_level": item.get("level", 1),
                        "page_idx": page_idx,
                    })
            elif btype in ("image", "table", "page_header", "page_footer",
                           "index", "chart", "equation", "list"):
                pass  # Skip non-content blocks
            else:
                text = ""
                if isinstance(content, dict):
                    text = content.get("content", "") or content.get("text", "")
                elif isinstance(content, str):
                    text = content
                if text.strip() and not _is_math_block(text):
                    blocks.append({
                        "type": "text", "text": text,
                        "text_level": 1, "page_idx": page_idx,
                    })

    return blocks


def parse_from_mineru_json(
    json_path: str,
    code: str = "",
    title: str = "",
    industry: str = "",
    source_file: str = "",
    issuing_body: str = "",
) -> tuple[StandardDocument, list[Chapter], list[Clause]]:
    """Parse a standard from MinerU content_list.json.

    Returns (StandardDocument, chapters, clauses) like parser.parse_standard_document.
    """
    blocks = load_mineru_blocks(json_path)
    if not blocks:
        return _empty_result(code, title, industry, source_file, issuing_body)

    standard_id = new_id("std")

    # Build text from content blocks (skip headers/footers/page_numbers/images)
    content_blocks = [
        b for b in blocks
        if b.get("type", "") in ("text", "header")
        and b.get("text", "").strip()
    ]

    # Extract summary
    texts = [b["text"].strip() for b in content_blocks if b["text"].strip()]
    summary = " ".join(texts[:5])[:500] if texts else ""

    if not title and texts:
        title = texts[1] if len(texts) > 1 else texts[0]

    doc = StandardDocument(
        standard_id=standard_id, code=code, title=title or "Untitled",
        industry=industry, issuing_body=issuing_body,
        source_file=source_file, summary=summary,
    )

    # Build chapters and clauses from text_level hierarchy
    chapters: list[Chapter] = []
    clauses: list[Clause] = []
    chapter_idx = 0
    clause_idx = 0

    # Process blocks sequentially
    prev_chapter_id: Optional[str] = None
    prev_at_level: dict[int, str] = {}
    pending_number: Optional[str] = None
    in_body = False  # Skip cover/title pages until first real chapter

    for i, block in enumerate(content_blocks):
        text = block["text"].strip()
        if not text:
            continue
        if _is_math_block(text):
            continue

        level = block.get("text_level", 1)
        page = block.get("page_idx", 0)

        # Map MinerU v2 levels: level 1=cover, level 2=chapter, level 3+=clause
        # For v1 format, level 1=chapter
        mapped_level = level - 1 if level >= 2 else level

        # Skip TOC, preface
        if text in ("目 次", "前 言", "引 言", "目  次"):
            continue
        if NON_CLAUSE_RE.match(text):
            continue

        # Case A: This block is just a clause number (e.g. "3.1")
        standalone_num = re.match(r'^(\d+(?:\.\d+)+)$', text)
        if standalone_num:
            pending_number = standalone_num.group(1)
            continue

        # Case B: "N Title" or "N Title" format
        m = CLAUSE_NUM_RE.match(text)
        if not m:
            m = CLAUSE_NUM_NO_SPACE_RE.match(text)
        effective_number = m.group(1) if m else None
        effective_title = m.group(2).strip() if m else text
        effective_level = max(mapped_level, effective_number.count(".") + 1 if effective_number else mapped_level)

        if effective_number is None and pending_number:
            effective_number = pending_number
            effective_title = text
            effective_level = effective_number.count(".") + 1

        pending_number = None

        if effective_number:
            # Activate body mode at first real chapter heading
            if not in_body and effective_number == "1" and "." not in effective_number:
                in_body = True
            if not in_body:
                pending_number = None
                continue

            # Single-digit/int numbers at mapped_level 1 are chapters
            # Skip formula captions, list artifacts, and unit-prefixed lines
            is_chapter = (
                "." not in effective_number and mapped_level <= 1
                and int(effective_number) <= 30
                and len(effective_title) >= 2
                and "单位为" not in effective_title
                and "式中" not in effective_title
                and not effective_title.endswith("；")
                and not effective_title.startswith("-")
                and not effective_title.startswith("—")
                and not re.match(r'^\s*(?:mm|cm|m|km|kPa|MPa|h|min|s|d|a)\b',
                                effective_title)
            )
            if is_chapter:
                ch = Chapter(
                    chapter_id=new_id("ch"), standard_id=standard_id,
                    chapter_number=effective_number, title=effective_title,
                    level=1, order_index=chapter_idx,
                )
                chapter_idx += 1
                chapters.append(ch)
                prev_chapter_id = ch.chapter_id
                prev_at_level = {1: ch.chapter_id}
                # Also create a Clause for the chapter (needed for extractor)
                cl_ch = Clause(
                    clause_id=new_id("cl"), standard_id=standard_id,
                    chapter_id=ch.chapter_id, clause_number=effective_number,
                    title=effective_title, content=effective_title,
                    level=1, order_index=clause_idx,
                )
                clause_idx += 1
                clauses.append(cl_ch)
            else:
                clause_level = effective_number.count(".") + 1
                chapter_id = prev_chapter_id
                cl = Clause(
                    clause_id=new_id("cl"), standard_id=standard_id,
                    chapter_id=chapter_id, clause_number=effective_number,
                    title=effective_title, content=effective_title,
                    level=clause_level, order_index=clause_idx,
                )
                clause_idx += 1
                clauses.append(cl)
                prev_at_level[clause_level] = cl.clause_id
                for l in list(prev_at_level.keys()):
                    if l > clause_level:
                        del prev_at_level[l]
        else:
            # Not a numbered heading — append to last clause as content
            pending_number = None
            if clauses:
                last = clauses[-1]
                last.content = (last.content + "\n" + text) if last.content else text

    # Split merged clauses (e.g. "6.1.1 ... 6.1.2 ..." in one block)
    clauses = _split_merged_clauses(standard_id, clauses)

    logger.info("MinerU parsed: %d chapters, %d clauses from %d blocks",
                len(chapters), len(clauses), len(content_blocks))
    return doc, chapters, clauses


def _split_merged_clauses(standard_id: str, clauses: list[Clause]) -> list[Clause]:
    """Split clauses that contain multiple clause numbers in their content.

    Detects patterns like '4.1 Title ... 4.2 Title ... 4.3 Title' within
    a single merged paragraph and splits them into individual clauses.
    """
    # Clause number at line start: "4.1 Title", "4.1Title", "4.1　Title"
    _CLAUSE_SPLIT_RE = re.compile(
        r'(?:^|\n)\s*(\d+(?:\.\d+){1,3})[\s　]*(?=[一-鿿\w])', re.MULTILINE,
    )

    # First-level headings: "6 Title" or "6Title" (no space)
    _CHAPTER_INLINE_RE = re.compile(
        r'(?:^|\n)\s*(\d{1,2})\s*([一-鿿][\w一-鿿]{1,80})', re.MULTILINE,
    )

    # Patterns to skip (not real clauses)
    _SKIP_PATTERNS = [
        re.compile(r'^[\d.]+\s*(?:mm|cm|m|km|kPa|MPa|kN|%|°)[\s。；，]'),
        re.compile(r'^[\d.]+\s*[~\\×]'),                          # Math: "1 ~ 3"
        re.compile(r'^[\d.]+\s*×\s*\d+'),                          # "1.5 × 2.0"
        re.compile(r'^[\d.]{3,}'),                                  # Long numbers like "2020"
        re.compile(r'^[\d.]+\s*[）)]'),                             # "(3)" or "4)"
    ]

    result: list[Clause] = []

    for cl in clauses:
        content = cl.content or ""

        # Try clause-level splits first: "N.M Title" patterns
        clause_matches = list(_CLAUSE_SPLIT_RE.finditer(content))
        if len(clause_matches) >= 2:
            for i, m in enumerate(clause_matches):
                number = m.group(1)
                start = m.start()
                end = clause_matches[i + 1].start() if i + 1 < len(clause_matches) else len(content)
                sub_text = content[start:end].strip()

                if _should_skip_clause(number, sub_text):
                    continue

                clause_level = number.count(".") + 1
                sc = Clause(
                    clause_id=new_id("cl"), standard_id=standard_id,
                    chapter_id=cl.chapter_id, clause_number=number,
                    title=sub_text[:100], content=sub_text,
                    level=clause_level, order_index=len(result),
                )
                result.append(sc)
        else:
            # No clause-level splits found; try chapter-inline splits
            ch_matches = list(_CHAPTER_INLINE_RE.finditer(content))
            if len(ch_matches) >= 2:
                for i, m in enumerate(ch_matches):
                    number = m.group(1)
                    title_part = m.group(2).strip()
                    start = m.start()
                    end = ch_matches[i + 1].start() if i + 1 < len(ch_matches) else len(content)
                    sub_text = content[start:end].strip()

                    if _should_skip_clause(number, sub_text):
                        continue

                    # Check if this chapter number is a reasonable continuation
                    try:
                        num_int = int(number)
                        if num_int < 1 or num_int > 30:
                            continue
                    except ValueError:
                        continue

                    clause_level = 1
                    sc = Clause(
                        clause_id=new_id("cl"), standard_id=standard_id,
                        chapter_id=cl.chapter_id, clause_number=number,
                        title=title_part[:100], content=sub_text,
                        level=clause_level, order_index=len(result),
                    )
                    result.append(sc)
            else:
                result.append(cl)

    return result


def _should_skip_clause(number: str, text: str) -> bool:
    """Check if a detected clause number is a false positive.

    Real clause numbers are followed by Chinese text. Decimals, units,
    and math expressions are not real clauses.
    """
    # Real clause: number followed by Chinese text → never skip
    if re.match(r'^[\d.]+\s*[一-鿿]', text):
        return False

    # Skip if text starts with math/unit patterns
    for pat in [
        re.compile(r'^[\d.]+\s*(?:mm|cm|m|km|kPa|MPa|kN|%|°)\b'),
        re.compile(r'^[\d.]+\s*[~\\×]'),
        re.compile(r'^[\d.]+\s*×\s*\d+'),
    ]:
        if pat.match(text):
            return True

    return False


def _empty_result(code, title, industry, source_file, issuing_body):
    doc = StandardDocument(
        standard_id=new_id("std"), code=code, title=title or "Untitled",
        industry=industry, issuing_body=issuing_body,
        source_file=source_file, summary="",
    )
    return doc, [], []
