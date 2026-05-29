"""PDF parser for industry standard documents.

Extracts text from PDF files using PyMuPDF (fitz), preserves page numbers,
and detects scanned (image-only) PDFs.

Usage:
    from src.graph.standard.pdf_parser import parse_pdf

    result = parse_pdf("data/standards/example.pdf")
    # result["text"]       → full extracted text
    # result["pages"]      → list of {"page_number": 1, "text": "..."}
    # result["is_scanned"] → True if no text could be extracted
    # result["error"]      → error message if any
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import fitz
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


def _pymupdf_not_installed_error() -> dict:
    return {
        "text": "",
        "pages": [],
        "total_pages": 0,
        "is_scanned": False,
        "error": (
            "PyMuPDF (fitz) 未安装。PDF 解析需要 PyMuPDF。\n"
            "请执行: pip install pymupdf\n"
            "或使用文本格式 (.md / .txt) 导入标准文档。"
        ),
    }


def parse_pdf(file_path: str, min_text_per_page: int = 30) -> dict:
    """Parse a PDF file and extract text content.

    Args:
        file_path: Path to the PDF file.
        min_text_per_page: Minimum character count per page before
                           considering it as having meaningful text.

    Returns:
        dict with keys:
          - "text": Full concatenated text of the PDF.
          - "pages": List of {"page_number": int, "text": str}.
          - "total_pages": Total number of pages in the PDF.
          - "is_scanned": True if most pages have no extractable text.
          - "error": Error message string (empty if successful).
    """
    if not HAS_PYMUPDF:
        return _pymupdf_not_installed_error()

    path = Path(file_path)
    if not path.exists():
        return {
            "text": "", "pages": [], "total_pages": 0,
            "is_scanned": False,
            "error": f"文件不存在: {file_path}",
        }

    if path.suffix.lower() != ".pdf":
        return {
            "text": "", "pages": [], "total_pages": 0,
            "is_scanned": False,
            "error": f"不是 PDF 文件: {file_path} (后缀: {path.suffix})",
        }

    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        logger.error("Failed to open PDF '%s': %s", file_path, exc)
        return {
            "text": "", "pages": [], "total_pages": 0,
            "is_scanned": False,
            "error": f"无法打开 PDF 文件: {exc}",
        }

    pages: list[dict] = []
    text_parts: list[str] = []
    pages_with_text = 0
    total_pages = len(doc)

    for page_idx in range(total_pages):
        try:
            page = doc[page_idx]
            page_text = page.get_text("text", sort=True) or ""
        except Exception as exc:
            logger.warning("Failed to extract text from page %d: %s", page_idx + 1, exc)
            page_text = ""

        # Clean excessive whitespace
        page_text = _clean_page_text(page_text)

        pages.append({
            "page_number": page_idx + 1,
            "text": page_text,
        })

        if len(page_text.strip()) >= min_text_per_page:
            pages_with_text += 1
            text_parts.append(page_text)
        else:
            text_parts.append(page_text)  # still include, may be title page

    doc.close()

    full_text = "\n\n".join(text_parts)

    # Heuristic: if fewer than 30% of pages have extractable text, flag as scanned
    text_page_ratio = pages_with_text / max(total_pages, 1)
    is_scanned = text_page_ratio < 0.3

    if is_scanned:
        logger.warning(
            "PDF '%s' appears to be scanned: only %d/%d pages have extractable text",
            file_path, pages_with_text, total_pages,
        )

    logger.info(
        "PDF parsed: '%s' — %d pages, %d chars, scanned=%s",
        path.name, total_pages, len(full_text), is_scanned,
    )

    return {
        "text": full_text,
        "pages": pages,
        "total_pages": total_pages,
        "is_scanned": is_scanned,
        "error": "",
    }


def _clean_page_text(text: str) -> str:
    """Normalize whitespace in extracted page text."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if line:
            cleaned.append(line)
    return "\n".join(cleaned)


def is_scanned_pdf(file_path: str) -> Optional[bool]:
    """Quick check: is this PDF likely scanned (image-only)?

    Returns True if scanned, False if has extractable text, None on error.
    """
    result = parse_pdf(file_path)
    if result["error"]:
        return None
    return result["is_scanned"]


def detect_garbled_text(text: str, min_chinese_ratio: float = 0.05) -> bool:
    """Detect if PDF text has a CMap/font encoding issue.

    Returns True if the text appears garbled (bad CMap mapping).
    """
    if not text or len(text) < 100:
        return False

    # Count CJK characters
    cjk = sum(1 for ch in text if '一' <= ch <= '鿿')

    # Count garbled indicator characters (from bad CMap)
    garbled = sum(1 for ch in text if ch in '犐犆犛犘犌犅犜')

    total = len(text)
    cjk_ratio = cjk / total if total > 0 else 0

    # If text is long enough but has almost no CJK, likely garbled
    if cjk_ratio < min_chinese_ratio and total > 500:
        return True

    # Presence of garbled indicator chars
    if garbled > 3:
        return True

    return False


def assess_pdf_quality(file_path: str) -> dict:
    """Assess PDF text quality for standard import.

    Returns dict with: quality ('ok'|'bad_cmap'|'needs_ocr'), reason, text_length.
    """
    result = parse_pdf(file_path)
    if result["error"]:
        return {"quality": "needs_ocr", "reason": result["error"], "text_length": 0}

    text = result["text"]
    if detect_garbled_text(text):
        return {
            "quality": "bad_cmap",
            "reason": "中文字体 CMap 映射异常，PyMuPDF 提取文本不可用。建议使用 MinerU OCR JSON。",
            "text_length": len(text),
        }

    return {"quality": "ok", "reason": "", "text_length": len(text)}


def get_pdf_info(file_path: str) -> dict:
    """Return basic PDF metadata without full text extraction.

    Returns dict with: total_pages, has_text, is_scanned, error.
    """
    if not HAS_PYMUPDF:
        return {"total_pages": 0, "has_text": False, "is_scanned": False,
                "error": "PyMuPDF 未安装"}

    path = Path(file_path)
    if not path.exists():
        return {"total_pages": 0, "has_text": False, "is_scanned": False,
                "error": f"文件不存在: {file_path}"}

    try:
        doc = fitz.open(str(path))
        total_pages = len(doc)
        has_text = False
        for i in range(min(3, total_pages)):
            page_text = doc[i].get_text("text", sort=True) or ""
            if len(page_text.strip()) > 30:
                has_text = True
                break
        doc.close()
        return {
            "total_pages": total_pages,
            "has_text": has_text,
            "is_scanned": not has_text and total_pages > 0,
            "error": "",
        }
    except Exception as exc:
        return {"total_pages": 0, "has_text": False, "is_scanned": False,
                "error": str(exc)}
