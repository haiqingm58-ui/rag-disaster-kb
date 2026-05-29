"""Tests for PDF parser — graceful when PyMuPDF is not installed."""

import pytest

from src.graph.standard.pdf_parser import (
    parse_pdf, is_scanned_pdf, get_pdf_info,
    HAS_PYMUPDF, _clean_page_text,
)


class TestCleanPageText:
    def test_removes_blank_lines(self):
        result = _clean_page_text("  line1  \n\n  line2  \n  ")
        assert result == "line1\nline2"

    def test_empty_string(self):
        assert _clean_page_text("") == ""


class TestParsePdfErrorHandling:
    """When PyMuPDF is available, file-not-found returns clear error.
    When PyMuPDF is NOT available, returns installation error."""

    def test_nonexistent_file_returns_error(self):
        result = parse_pdf("/nonexistent/path/file.pdf")
        assert result["text"] == ""
        assert len(result["pages"]) == 0
        # Either PyMuPDF not installed OR file not found
        assert result["error"] != ""
        assert ("pip install pymupdf" in result["error"].lower() or
                "不存在" in result["error"])

    def test_txt_extension(self):
        result = parse_pdf("test.txt")
        assert result["error"] != ""
        if HAS_PYMUPDF:
            assert "不是 PDF" in result["error"] or "不存在" in result["error"]

    def test_empty_result_structure(self):
        """All error paths should return the same result structure."""
        result = parse_pdf("nonexistent.pdf")
        for key in ["text", "pages", "total_pages", "is_scanned", "error"]:
            assert key in result


class TestIsScannedPdf:
    def test_returns_none_on_error(self):
        result = is_scanned_pdf("/nonexistent/path/file.pdf")
        # None on error, or False/True on success
        if not HAS_PYMUPDF:
            assert result is None


class TestGetPdfInfo:
    def test_returns_dict(self):
        result = get_pdf_info("test.pdf")
        for key in ["total_pages", "has_text", "is_scanned", "error"]:
            assert key in result

    def test_error_when_no_pymupdf(self):
        result = get_pdf_info("test.pdf")
        if not HAS_PYMUPDF:
            assert "未安装" in result["error"] or "PyMuPDF" in result.get("error", "")
            assert result["total_pages"] == 0
        else:
            # With PyMuPDF, nonexistent file returns error too
            assert result["error"] != ""
