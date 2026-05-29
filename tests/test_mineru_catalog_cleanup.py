"""Tests that catalog/ToC content is stripped from MinerU output."""

import pytest
from src.graph.standard.parser import _clean_mineru_markdown, _strip_toc_section


class TestStripTocSection:
    def test_removes_toc_before_chapter_1(self):
        text = """目  次
1 范围 .................................... 1
2 规范性引用文件 ........................... 3
1 范围
本标准规定了...
"""
        cleaned = _strip_toc_section(text)
        assert "...." not in cleaned
        # The real "1 范围" after the TOC should remain
        assert cleaned.count("1 范围") >= 1

    def test_no_toc_preserves_text(self):
        text = "1 范围\n本标准规定了..."
        cleaned = _strip_toc_section(text)
        assert "1 范围" in cleaned


class TestCleanMineruMarkdownExtended:
    def test_removes_unit_only_lines(self):
        text = "正文内容\nmm。\n继续正文"
        cleaned = _clean_mineru_markdown(text)
        assert "mm。" not in cleaned or "mm。" == cleaned.strip()

    def test_removes_numbered_list_artifacts(self):
        text = "正文\n3 -PE钢绞线；\n继续"
        cleaned = _clean_mineru_markdown(text)
        assert "PE钢绞线" not in cleaned

    def test_removes_drill_hole_artifact(self):
        text = "正文\n6 钻孔；\n继续"
        cleaned = _clean_mineru_markdown(text)
        assert "钻孔" not in cleaned

    def test_preserves_real_content(self):
        text = "1 范围\n本标准规定了滑坡防治设计的技术要求。"
        cleaned = _clean_mineru_markdown(text)
        assert "1 范围" in cleaned
        assert "滑坡防治设计" in cleaned
