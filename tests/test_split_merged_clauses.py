"""Tests for _split_merged_clauses in mineru_parser."""

import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.graph.standard.models import Clause
from src.graph.standard.mineru_parser import _split_merged_clauses, _should_skip_clause


def make_clause(number, content, chapter_id=None, standard_id="std-1"):
    return Clause(clause_id=f"cl-{number.replace('.','-')}",
                  standard_id=standard_id, chapter_id=chapter_id,
                  clause_number=number, content=content, level=1)


class TestSplitMergedClauses:
    def test_splits_clause_level_numbers(self):
        clauses = [
            make_clause("6", "6.1 一般规定\n滑坡防治工程分级。\n6.1.1 应符合表1。\n6.1.2 还应符合表2。\n6.2 荷载标准\n荷载应包括。")
        ]
        result = _split_merged_clauses("std-1", clauses)
        # Should have at least 4 sub-clauses
        assert len(result) >= 4
        numbers = {cl.clause_number for cl in result}
        assert "6.1" in numbers
        assert "6.1.1" in numbers
        assert "6.1.2" in numbers
        assert "6.2" in numbers

    def test_splits_deep_level_numbers(self):
        clauses = [
            make_clause("10", "10.1 一般规定\n10.1.1 设计要求\n10.1.2 施工要求\n10.1.2.1 具体要求\n10.2 计算方法")
        ]
        result = _split_merged_clauses("std-1", clauses)
        numbers = {cl.clause_number for cl in result}
        assert "10.1" in numbers
        assert "10.1.1" in numbers
        assert "10.1.2" in numbers
        assert "10.1.2.1" in numbers
        assert "10.2" in numbers

    def test_no_split_when_single(self):
        clauses = [
            make_clause("4", "4 总则 本章规定了基本要求。")
        ]
        result = _split_merged_clauses("std-1", clauses)
        assert len(result) == 1

    def test_chapter_inline_split(self):
        clauses = [
            make_clause("1", "1范围\n本标准规定了。\n2规范性引用文件\n下列文件。\n3术语和定义\n下列术语。")
        ]
        result = _split_merged_clauses("std-1", clauses)
        assert len(result) >= 3


class TestSkipClause:
    def test_skips_table_number(self):
        assert _should_skip_clause("1", "表 1 滑坡分类") is False

    def test_skips_decimal_math(self):
        assert _should_skip_clause("1.15", "1.15 ~ 2.0 范围") is True

    def test_skips_unit_unit(self):
        assert _should_skip_clause("0", "0.5 mm 厚度") is True

    def test_does_not_skip_real_clause(self):
        assert _should_skip_clause("4.1", "4.1 一般规定") is False
        assert _should_skip_clause("10", "10 抗滑桩工程") is False


class TestNonClausePatterns:
    def test_table_not_clause(self):
        from src.graph.standard.mineru_parser import NON_CLAUSE_RE
        assert NON_CLAUSE_RE.match("表 1 滑坡分类")
        assert NON_CLAUSE_RE.match("图 2 示意图")
        assert NON_CLAUSE_RE.match("式（3）")
        assert NON_CLAUSE_RE.match("附录A")

    def test_real_clause_not_filtered(self):
        from src.graph.standard.mineru_parser import NON_CLAUSE_RE
        assert not NON_CLAUSE_RE.match("4 总则")
        assert not NON_CLAUSE_RE.match("4.1 一般规定")
        assert not NON_CLAUSE_RE.match("10.2.1 计算方法")
