"""Tests for T/CAGHP terminology standard term extraction."""

import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.graph.standard.models import Clause
from src.graph.standard.extractor import (
    extract_terms_from_clause, _looks_like_term_title,
    _looks_like_terminology_standard, _is_term_definition_chapter,
)


class TestLooksLikeTermTitle:
    def test_chinese_english_term(self):
        assert _looks_like_term_title("地质环境geological environments") is True

    def test_chinese_english_with_space(self):
        assert _looks_like_term_title("地质环境条件 geoenvironmentalconditions") is True

    def test_chinese_only_term(self):
        assert _looks_like_term_title("地质灾害") is True

    def test_chapter_title_not_term(self):
        for t in ["范围", "规范性引用文件", "术语和定义", "目 次", "前 言", "附录"]:
            assert not _looks_like_term_title(t), f"'{t}' should not be a term"

    def test_requirement_not_term(self):
        assert not _looks_like_term_title("应采用定量方法")

    def test_clause_number_not_term(self):
        assert not _looks_like_term_title("2.1 一般术语")


class TestTerminologyStandardDetection:
    def test_many_term_like_titles(self):
        clauses = [
            Clause(clause_id=f"cl-{i}", standard_id="s", clause_number=f"2.{i}.{j}",
                   title=title, content=title, level=3)
            for i in range(1, 5) for j in range(1, 11)
            for title in ["地质环境geological environments"]
        ]
        assert _looks_like_terminology_standard(clauses) is True

    def test_normal_standard(self):
        clauses = [
            Clause(clause_id="cl-1", standard_id="s", clause_number="4.1",
                   title="评估要求", content="应进行滑坡评估。", level=2),
            Clause(clause_id="cl-2", standard_id="s", clause_number="4.2",
                   title="基本规定", content="应符合标准。", level=2),
        ]
        assert _looks_like_terminology_standard(clauses) is False


class TestExtractTermsFromClause:
    def test_tcaghp_format_title_based(self):
        cl = Clause(clause_id="cl-x", standard_id="s", clause_number="2.1.1",
                    title="地质环境geological environments",
                    content="地质环境geological environments\n由岩石圈表层与大气圈、水圈、生物圈相互作用形成的自然系统。",
                    level=3)
        terms = extract_terms_from_clause(cl, is_definition_section=True)
        assert len(terms) >= 1
        assert any("地质环境" in t.name for t in terms)

    def test_tcaghp_format_pdf(self):
        cl = Clause(clause_id="cl-x", standard_id="s", clause_number="2.1.2",
                    title="",
                    content="地质环境条件geoenvironmentalconditions\n专指与地质灾害形成和发展有关的所有地质要素。",
                    level=3)
        terms = extract_terms_from_clause(cl, is_definition_section=True)
        assert len(terms) >= 1
