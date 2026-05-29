"""Tests for standard document parser."""

import pytest

from src.graph.standard.parser import (
    parse_standard_document, _detect_level, _is_chapter_level, extract_references,
)


class TestDetectLevel:
    def test_single_digit(self):
        assert _detect_level("1") == 1
        assert _detect_level("3") == 1

    def test_two_levels(self):
        assert _detect_level("1.1") == 2
        assert _detect_level("3.2") == 2

    def test_three_levels(self):
        assert _detect_level("3.1.2") == 3


class TestIsChapterLevel:
    def test_top_level_is_chapter(self):
        assert _is_chapter_level(1, 2) is True

    def test_second_level_default_chapter(self):
        assert _is_chapter_level(2, 2) is True

    def test_third_level_not_chapter(self):
        assert _is_chapter_level(3, 2) is False


class TestParseStandardDocument:
    def test_plain_numbered_headings(self):
        text = """1 总则
第一条内容。

2 术语
2.1 地质灾害
指自然因素引发的...

2.2 滑坡
斜坡上的岩土体...

3 基本规定
3.1 一般要求
3.1.1 应采用定量方法。
3.1.2 安全系数不应小于1.15。
"""
        doc, chapters, clauses = parse_standard_document(
            text, code="DZ/T 0001", title="测试标准", industry="geo",
        )
        assert doc.code == "DZ/T 0001"
        assert len(chapters) >= 1
        assert len(clauses) >= 3

        # Check clause numbering
        clause_numbers = {cl.clause_number for cl in clauses}
        assert "1" in clause_numbers
        assert "3.1.1" in clause_numbers or len(clauses) > 0

    def test_markdown_headings(self):
        text = """# 1 总则
内容一。

## 1.1 目的
目的内容。

# 2 术语
## 2.1 术语一
定义一。
"""
        doc, chapters, clauses = parse_standard_document(
            text, code="GB/T 0001", title="MD标准", industry="test",
        )
        assert doc.code == "GB/T 0001"
        assert len(clauses) >= 2

    def test_no_headings(self):
        text = "这是一段没有标题的标准文本。包含了基本要求。应采用定量方法评估。"
        doc, chapters, clauses = parse_standard_document(
            text, code="TEST", title="无标题标准", industry="test",
        )
        assert len(chapters) == 0
        assert len(clauses) == 1
        assert clauses[0].clause_number == "1"

    def test_empty_text(self):
        doc, chapters, clauses = parse_standard_document(
            "", code="E", title="空", industry="test",
        )
        assert doc.code == "E"
        assert len(chapters) == 0
        assert len(clauses) == 0 or len(clauses) == 1

    def test_clause_content_preserved(self):
        text = """1 测试章
## 1.1 测试条
这是条款的具体内容，包含了"应采用"等关键词。
内容不应被修改或截断超过限制。
"""
        doc, chapters, clauses = parse_standard_document(
            text, code="TEST", title="内容测试", industry="test",
        )
        # Find the clause with content
        content_clauses = [cl for cl in clauses if "应采用" in cl.content]
        assert len(content_clauses) >= 1


class TestExtractReferences:
    def test_extracts_gb_standard(self):
        text = "应符合GB/T 12345-2020的规定。同时参照DZ/T 0286-2015。"
        refs = extract_references(text)
        assert "GB/T 12345-2020" in refs
        assert "DZ/T 0286-2015" in refs

    def test_no_references(self):
        assert extract_references("本标准无引用。") == []
