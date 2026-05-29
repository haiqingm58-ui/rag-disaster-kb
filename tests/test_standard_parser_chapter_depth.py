"""Tests for chapter depth parsing."""

import pytest

from src.graph.standard.parser import (
    parse_standard_document, _detect_level, _is_chapter_level,
)


class TestDetectLevel:
    def test_top_level(self):
        assert _detect_level("1") == 1
        assert _detect_level("5") == 1

    def test_second_level(self):
        assert _detect_level("4.1") == 2

    def test_third_level(self):
        assert _detect_level("4.1.1") == 3


class TestIsChapterLevel:
    def test_default_depth_1(self):
        """With max_chapter_depth=1, only level 1 headings are chapters."""
        assert _is_chapter_level(1, 1) is True
        assert _is_chapter_level(2, 1) is False
        assert _is_chapter_level(3, 1) is False

    def test_depth_2(self):
        """With max_chapter_depth=2, levels 1 and 2 are chapters."""
        assert _is_chapter_level(1, 2) is True
        assert _is_chapter_level(2, 2) is True
        assert _is_chapter_level(3, 2) is False


class TestParseWithDefaultDepth:
    def test_default_depth_treats_second_level_as_clause(self):
        """Default max_chapter_depth=1: '4 总则' is Chapter, '4.1 xxx' is Clause."""
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
            # Using default max_chapter_depth=1
        )
        chapter_numbers = {ch.chapter_number for ch in chapters}
        clause_numbers = {cl.clause_number for cl in clauses}

        assert "1" in chapter_numbers
        assert "4" in chapter_numbers
        assert "4.1" in clause_numbers
        assert "4.1.1" in clause_numbers

    def test_explicit_depth_2(self):
        """With max_chapter_depth=2: '4.1' becomes a Chapter."""
        text = """1 范围
第一条。

4 总则
4.1 评估要求
应进行滑坡评估。
"""
        doc, chapters, clauses = parse_standard_document(
            text, code="T", title="T", industry="G",
            max_chapter_depth=2,
        )
        chapter_numbers = {ch.chapter_number for ch in chapters}
        assert "1" in chapter_numbers
        assert "4" in chapter_numbers
        assert "4.1" in chapter_numbers  # Now a chapter
