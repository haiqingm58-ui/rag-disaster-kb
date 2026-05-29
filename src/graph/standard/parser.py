"""Parse industry standard documents (Markdown/txt) into structured objects.

Extracts StandardDocument metadata, Chapter hierarchy, and Clause content
based on heading numbering patterns (1, 1.1, 1.1.1, etc.).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .models import (
    StandardDocument, Chapter, Clause, StandardStatus,
)
from ..common.utils import new_id

logger = logging.getLogger(__name__)

# Patterns for heading detection
HEADING_PATTERN = re.compile(
    r"^(?:#+\s*)?(\d+(?:\.\d+)*)\s+(.+?)(?:\s*#+\s*)?$",
    re.MULTILINE,
)

# PDF extraction artifact: clause number on its own line, title on next line
_SPLIT_HEADING = re.compile(
    r"^(\d+(?:\.\d+)*)[ \t]*\n([一-鿿\w]{1,60}(?:[ \t]+[a-zA-Z][a-zA-Z]{0,50})?)",
    re.MULTILINE,
)


# Lines that should never be treated as heading titles
_HEADING_TITLE_BLACKLIST = re.compile(
    r"^(GB|DZ|SL|JT|TB|YB|HJ|CJJ|JGJ|DL|NB|SH|SY)[/\-—][TZ]?\s*\d+[\.\-—]\d+$"
)

_FRONTMATTER_LINE = re.compile(
    r"^(ICS|中华人民共和国|前言|目\s*次|目\s*录|前\s*言|引\s*言)",
)


# Patterns for suspicious/non-heading lines common in MinerU output
_SUSPICIOUS_HEADING_PATTERNS = [
    re.compile(r"^[\d\s.,;:：]+$"),                      # Pure numbers/punctuation
    re.compile(r"^\d+\s*(?:mm|cm|m|km|kPa|MPa|GPa|Pa|N|kN|%|°|℃)(?:[。；，]|$)"),  # Unit fragments
    re.compile(r"^(?:mm|cm|m|km|kPa|MPa|GPa|Pa|N|kN)(?:[。；，\d]|$)"),              # Unit-only
    re.compile(r"^[—\-–]{2,}"),                            # "——" dash lines
    re.compile(r"^.{10,}[。；，]$"),                          # Long text ending with punctuation (not title-like)
    re.compile(r"\d+\s*(?:mm|cm|m|km|kPa|MPa|GPa|Pa|N|kN|%|°|℃)[。；，]"),  # Numeric+unit ending
    re.compile(r"[（(]\s*(?:mm|cm|m|km|kPa|MPa|kN|%|°|℃|单位为|见图|见表|详见)\s*[）)]"),  # Units in parens
    re.compile(r"^(?:式中|单位为|见表|见图|详见|参见)"),     # Caption/note prefixes
    re.compile(r"^(?:钢套筒|钻孔|锚索|锚杆|格构|挡墙|排水沟)[；。，]?$"),  # Isolated technical terms
    re.compile(r"^\d+\s*[-—]\s*(?:PE|PVC|HDPE)", re.IGNORECASE),  # "3 -PE钢绞线"
    re.compile(r"^\d+\s+(?:矩形桩|抗滑桩|锚索|锚杆|格构|挡墙|排水沟)\b"),  # Numbered list artifacts
]


def _is_heading_noise(title: str) -> bool:
    """Return True if the title looks like a PDF/MinerU artifact, not a real heading."""
    title = title.strip()
    if not title or len(title) < 2:
        return True
    if _HEADING_TITLE_BLACKLIST.match(title):
        return True
    for pat in _SUSPICIOUS_HEADING_PATTERNS:
        if pat.match(title) or pat.search(title):
            return True
    return False


def _clean_mineru_markdown(text: str) -> str:
    """Clean MinerU-produced Markdown artifacts.

    Removes:
      - Image references: ![](...)
      - Page headers/footers: 'GB/T 32864—2016' and similar
      - Table of Contents entries
      - Table rows, formula captions, unit-only lines
    """
    import re as _re

    # Remove image references
    text = _re.sub(r'!\[.*?\]\(.*?\)', '', text)

    # Remove standard code lines (page headers/footers)
    text = _re.sub(
        r'^\s*(?:GB|DZ|SL|JT|TB|YB|HJ|CJJ|JGJ)[/\-—][TZ]?\s*\d+[\.\-—]\d+\s*$',
        '', text, flags=_re.MULTILINE,
    )

    # Remove lines that are just "目  次" or "目  录" or "前  言"
    text = _re.sub(r'^\s*(?:目\s*次|目\s*录|前\s*言|引\s*言)\s*$', '',
                   text, flags=_re.MULTILINE)

    # Remove Table of Contents section: from 目次 to the first real chapter heading
    text = _strip_toc_section(text)

    # Remove standalone page numbers
    text = _re.sub(r'^\s*\d{1,3}\s*$', '', text, flags=_re.MULTILINE)

    # Remove Table of Contents lines (lines with dots filling and page numbers)
    text = _re.sub(
        r'^\s*.+\.{3,}\s*\d+\s*$', '', text, flags=_re.MULTILINE,
    )
    # Remove trailing page numbers from headings (e.g. "总则·· 4" → "总则")
    text = _re.sub(
        r'^((?:#+\s*)?\d+(?:\.\d+)*\s+.+?)[·•\.]{2,}\s*\d+\s*$',
        r'\1', text, flags=_re.MULTILINE,
    )
    # Remove trailing page numbers from headings (e.g. "基本规定 4")
    text = _re.sub(
        r'^((?:#+\s*)?\d+(?:\.\d+)*\s+.+?)\s+\d{1,3}\s*$',
        r'\1', text, flags=_re.MULTILINE,
    )

    # Remove formula captions and unit-only lines
    text = _re.sub(
        r'^\s*(?:式中|单位为|见表|见图|详见|参见|注[：:]).*$', '',
        text, flags=_re.MULTILINE,
    )

    # Remove unit-only lines (mm。, kPa。, MPa。 etc.)
    text = _re.sub(
        r'^\s*\d*\s*(?:mm|cm|m|km|kPa|MPa|GPa|Pa|N|kN|%|°|℃)\s*[。；，]?\s*$',
        '', text, flags=_re.MULTILINE,
    )

    # Remove numbered list artifacts from table cells
    # e.g. "3 -PE钢绞线；"  "6 钻孔；"  "9 ——钢套筒；"
    text = _re.sub(
        r'^\s*\d+\s*[-—–]\s*.{1,40}[；;]\s*$', '', text, flags=_re.MULTILINE,
    )
    text = _re.sub(
        r'^\s*\d+\s+.{1,20}[；;]\s*$', '', text, flags=_re.MULTILINE,
    )

    # Collapse multiple blank lines
    text = _re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def _strip_toc_section(text: str) -> str:
    """Remove the table of contents section from MinerU output.

    From '目  次' / '目  录' to the first occurrence of '1 范围' or similar.
    """
    import re as _re

    # Find the TOC start
    toc_start = None
    for pat in [r'^\s*目\s*次\s*$', r'^\s*目\s*录\s*$']:
        m = _re.search(pat, text, _re.MULTILINE)
        if m:
            toc_start = m.start()
            break

    if toc_start is None:
        return text

    # Find the first real chapter heading after TOC
    # Skip TOC entries (lines with dots/ellipses or page numbers)
    first_chapter = None
    for m in _re.finditer(
        r'^(?:#+\s*)?(1\s+(?:范围|总\s*则|基本规定).*)$', text[toc_start:],
        _re.MULTILINE,
    ):
        line = m.group(0)
        # Skip if this looks like a TOC entry (has dots or ends with page number)
        if _re.search(r'\.{3,}|\d{1,3}\s*$', line):
            continue
        first_chapter = m
        break
    if first_chapter:
        toc_end = toc_start + first_chapter.start()
        return text[:toc_start] + text[toc_end:]

    return text


def _strip_frontmatter(text: str) -> str:
    """Remove PDF frontmatter lines before the first real chapter heading.

    Lines like 'ICS07.060P13', '中华人民共和国国家标准', standard codes
    at the top of the document are not part of the standard content.
    """
    lines = text.split("\n")
    result: list[str] = []
    found_content = False

    for line in lines:
        stripped = line.strip()
        # Skip metadata lines before the first real heading
        if not found_content:
            if _FRONTMATTER_LINE.match(stripped):
                continue
            if _HEADING_TITLE_BLACKLIST.match(stripped):
                continue
            if not stripped:
                continue
            # Skip English subtitle without spaces (PDF artifact)
            if (stripped.isascii() and len(stripped) > 20 and
                " " not in stripped and not stripped.startswith("1")):
                continue
            found_content = True

        result.append(line)

    return "\n".join(result)


def _normalize_pdf_text(text: str) -> str:
    """Normalize PDF-extracted text where clause numbers and titles are split across lines.

    Example:
        "3.1\\n滑坡  landslide\\n" → "3.1 滑坡  landslide\\n"

    Skips page-header artifacts like "1\\nGB/T32864—2016".
    """
    def _repl(m):
        second = m.group(2).strip()
        # Don't join if the second line looks like a standard code
        if _HEADING_TITLE_BLACKLIST.match(second):
            return m.group(0)  # keep original
        return f"{m.group(1)} {second}"

    return _SPLIT_HEADING.sub(_repl, text)

# Match both Markdown headings (# 1 Title) and plain numbered headings (1 Title)
MD_HEADING = re.compile(r"^(#{1,6})\s+(\d+(?:\.\d+)*)\s+(.+?)\s*$", re.MULTILINE)

# Match references to other standards
REF_PATTERN = re.compile(
    r"(?:GB|DZ|SL|JT|TB|YB|HJ|CJJ|JGJ)(?:/T\s*\d+[\.-]\d+)",
)


def _detect_level(number_str: str) -> int:
    """Return the nesting level of a clause number (e.g. '3.1.2' -> 3)."""
    return number_str.count(".") + 1


def _is_chapter_level(level: int, max_depth: int) -> bool:
    """Heuristic: top 2 levels are chapters, deeper are clauses."""
    return level <= min(2, max_depth)


def parse_standard_document(
    text: str,
    code: str = "",
    title: str = "",
    industry: str = "",
    source_file: str = "",
    issuing_body: str = "",
    max_chapter_depth: int = 1,
) -> tuple[StandardDocument, list[Chapter], list[Clause]]:
    """Parse a standard document text into structured objects.

    Args:
        text: Full text of the standard document (Markdown or plain text).
        code: Standard code (e.g. 'DZ/T 0286-2015').
        title: Standard title.
        industry: Industry domain (e.g. 'geological_disaster').
        source_file: Path to the source file.
        issuing_body: Organization that issued the standard.
        max_chapter_depth: Numbering levels treated as chapters (default 2).

    Returns:
        Tuple of (StandardDocument, list[Chapter], list[Clause]).
    """
    # Clean MinerU Markdown artifacts (images, headers, TOC)
    text = _clean_mineru_markdown(text)
    # Strip PDF frontmatter (ICS headers, standard codes before content)
    text = _strip_frontmatter(text)
    # Normalize PDF artifacts: join split clause numbers and titles
    text = _normalize_pdf_text(text)

    lines = text.split("\n")
    standard_id = new_id("std")

    # Extract summary from first 500 non-empty characters
    non_empty = " ".join(line.strip() for line in lines if line.strip())
    summary = non_empty[:500]

    # Try to extract title from first heading if not provided
    if not title:
        for line in lines[:10]:
            line = line.strip().lstrip("#").strip()
            if line and "前言" not in line and "目" not in line:
                title = line[:200]
                break

    doc = StandardDocument(
        standard_id=standard_id,
        code=code,
        title=title or "Untitled Standard",
        industry=industry,
        status=StandardStatus.CURRENT,
        issuing_body=issuing_body,
        source_file=source_file,
        summary=summary,
    )

    # Parse headings
    chapters: list[Chapter] = []
    clauses: list[Clause] = []
    chapter_index = 0
    clause_index = 0

    # Determine heading patterns in use
    headings: list[tuple[int, int, str, str]] = []  # (line_no, level, number, title)

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Try Markdown heading
        m = MD_HEADING.match(stripped)
        if m:
            level = m.group(1).count("#")
            number = m.group(2)
            heading_title = m.group(3)
            if not _is_heading_noise(heading_title):
                headings.append((i, level, number, heading_title))
            continue

        # Try plain numbered heading
        m = HEADING_PATTERN.match(stripped)
        if m:
            number = m.group(1)
            heading_title = m.group(2)
            if not _is_heading_noise(heading_title):
                # Determine level from number
                level = _detect_level(number)
                headings.append((i, level, number, heading_title))

    if not headings:
        logger.warning("No headings found in document; treating entire text as one clause")
        # Create a single clause from the whole text
        cl = Clause(
            clause_id=new_id("cl"),
            standard_id=standard_id,
            clause_number="1",
            title=title or "全文",
            content=text[:10000],
            level=1,
            order_index=0,
        )
        clauses.append(cl)
        return doc, chapters, clauses

    # Build chapters and clauses from headings
    prev_chapter_ids: dict[int, str] = {}  # level -> chapter_id for parent

    for line_no, level, number, heading_title in headings:
        # Extract content: text from this heading to the next heading
        next_heading_line = len(lines)
        for h_line, h_level, _, _ in headings:
            if h_line > line_no:
                next_heading_line = h_line
                break

        # Collect content lines
        content_lines = []
        for j in range(line_no + 1, next_heading_line):
            content_lines.append(lines[j].strip())

        body = "\n".join(content_lines).strip()

        if _is_chapter_level(level, max_chapter_depth):
            # This is a chapter
            ch = Chapter(
                chapter_id=new_id("ch"),
                standard_id=standard_id,
                chapter_number=number,
                title=heading_title,
                level=level,
                order_index=chapter_index,
            )
            chapter_index += 1
            chapters.append(ch)
            prev_chapter_ids[level] = ch.chapter_id
            # Clear deeper levels
            for l in list(prev_chapter_ids.keys()):
                if l > level:
                    del prev_chapter_ids[l]

        # Always create a clause for every heading
        parent_chapter_id = None
        for l in sorted(prev_chapter_ids.keys(), reverse=True):
            if l < level:
                parent_chapter_id = prev_chapter_ids[l]
                break

        cl = Clause(
            clause_id=new_id("cl"),
            standard_id=standard_id,
            chapter_id=parent_chapter_id,
            clause_number=number,
            title=heading_title,
            content=body[:10000] if body else heading_title,
            level=level,
            order_index=clause_index,
        )
        clause_index += 1
        clauses.append(cl)

    logger.info(
        "Parsed standard '%s': %d chapters, %d clauses",
        doc.code or doc.title, len(chapters), len(clauses),
    )
    return doc, chapters, clauses


def extract_references(text: str) -> list[str]:
    """Extract references to other standards (e.g. 'GB/T 12345-2020')."""
    return list(set(REF_PATTERN.findall(text)))
