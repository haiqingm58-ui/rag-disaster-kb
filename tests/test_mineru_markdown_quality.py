"""Tests for MinerU Markdown cleaning and quality."""

import pytest

from src.graph.standard.parser import (
    _clean_mineru_markdown, parse_standard_document,
)


class TestCleanMineruMarkdown:
    def test_removes_image_references(self):
        text = "正文 ![](images/fig1.jpg) 继续正文"
        cleaned = _clean_mineru_markdown(text)
        assert "![](" not in cleaned

    def test_removes_standard_code_header(self):
        text = "GB/T 32864-2016\n\n正文内容"
        cleaned = _clean_mineru_markdown(text)
        assert "GB/T 32864-2016" not in cleaned

    def test_removes_standard_code_with_emdash(self):
        text = "GB/T 32864—2016\n\n正文内容"
        cleaned = _clean_mineru_markdown(text)
        assert "32864" not in cleaned

    def test_removes_toc_lines(self):
        text = "1 范围 .................................... 1\n正文"
        cleaned = _clean_mineru_markdown(text)
        assert "...." not in cleaned

    def test_removes_mulu(self):
        text = "目  次\n\n正文"
        cleaned = _clean_mineru_markdown(text)
        assert "目" not in cleaned

    def test_preserves_real_content(self):
        text = "1 范围\n本标准规定了滑坡防治工程勘查的技术要求。"
        cleaned = _clean_mineru_markdown(text)
        assert "1 范围" in cleaned
        assert "滑坡防治工程勘查" in cleaned

    def test_collapses_multiple_blank_lines(self):
        text = "line1\n\n\n\n\nline2"
        cleaned = _clean_mineru_markdown(text)
        assert "\n\n\n\n" not in cleaned


class TestParseMineruStyle:
    def test_second_level_not_chapter(self):
        """4.1 should be a Clause, not Chapter, with default depth."""
        text = """1 范围
第一条。

4 总则
4.1 评估要求
应进行滑坡评估。
4.1.1 具体规定
安全系数不应小于1.15。
"""
        doc, chapters, clauses = parse_standard_document(
            text, code="T", title="T", industry="G",
        )
        chapter_nums = {ch.chapter_number for ch in chapters}
        clause_nums = {cl.clause_number for cl in clauses}
        assert "4.1" in clause_nums
        assert "4.1" not in chapter_nums

    def test_term_format_with_english(self):
        text = """3 术语和定义
3.1 滑坡  landslide
在重力作用下，斜坡上的岩土体沿一定的软弱面整体下滑的现象。
"""
        doc, chapters, clauses = parse_standard_document(
            text, code="T", title="T", industry="G",
        )
        # Should have a clause for 3.1
        term_clauses = [cl for cl in clauses if cl.clause_number == "3.1"]
        assert len(term_clauses) >= 1
