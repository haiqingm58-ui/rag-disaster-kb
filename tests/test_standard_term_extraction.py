"""Tests for term extraction from industry standard documents."""

import pytest

from src.graph.standard.models import Clause
from src.graph.standard.extractor import (
    extract_terms_from_clause, _is_term_definition_chapter,
    _TERM_TITLE_PATTERN, _TERM_PDF_PATTERN, _TERM_PDF_SIMPLE_PATTERN,
)


def make_clause(number="3.1", title="", content="", level=2, standard_id="std-1"):
    return Clause(clause_id=f"cl-{number.replace('.','-')}",
                  standard_id=standard_id, clause_number=number,
                  title=title, content=content, level=level)


class TestTermTitlePattern:
    def test_chinese_english_title(self):
        m = _TERM_TITLE_PATTERN.match("滑坡 landslide")
        assert m is not None
        assert m.group(1) == "滑坡"

    def test_chinese_only_title(self):
        m = _TERM_TITLE_PATTERN.match("滑坡")
        assert m is not None
        assert m.group(1) == "滑坡"

    def test_english_only_title(self):
        m = _TERM_TITLE_PATTERN.match("landslide")
        assert m is not None


class TestTermPDFPattern:
    def test_term_with_english(self):
        content = "滑坡  landslide\n在重力作用下，斜坡上的岩土体沿一定的软弱面整体下滑的现象。"
        m = _TERM_PDF_PATTERN.match(content)
        assert m is not None
        assert m.group(1) == "滑坡"
        assert m.group(2) == "landslide"

    def test_term_simple_no_english(self):
        content = "滑坡\n在重力作用下，斜坡上的岩土体沿一定的软弱面整体下滑。"
        m = _TERM_PDF_SIMPLE_PATTERN.match(content)
        assert m is not None
        assert m.group(1) == "滑坡"


class TestIsTermDefinitionChapter:
    def test_terminology_chapter(self):
        cl = make_clause(number="3", title="术语和定义")
        assert _is_term_definition_chapter(cl) is True

    def test_normal_chapter(self):
        cl = make_clause(number="4", title="总则")
        assert _is_term_definition_chapter(cl) is False


class TestExtractTerms:
    def test_title_based_term(self):
        cl = make_clause(
            number="3.1", title="滑坡 landslide",
            content="在重力作用下，斜坡上的岩土体沿软弱面下滑。",
        )
        terms = extract_terms_from_clause(cl, is_definition_section=True)
        assert len(terms) >= 1
        assert terms[0].name == "滑坡"

    def test_pdf_format_term(self):
        cl = make_clause(
            number="3.2", title="",
            content="滑面  slidingplane\n滑坡滑动和堆积过程中的底界面。",
        )
        terms = extract_terms_from_clause(cl, is_definition_section=True)
        assert len(terms) >= 1
        assert terms[0].name == "滑面"

    def test_term_definition_chapter_filtered(self):
        """Chapter title '术语和定义' should NOT be extracted as a term."""
        cl = make_clause(number="3", title="术语和定义", content="本章规定术语。")
        terms = extract_terms_from_clause(cl, is_definition_section=True)
        names = [t.name for t in terms]
        assert "术语和定义" not in names

    def test_not_in_definition_section(self):
        cl = make_clause(
            number="4.1", title="评估要求",
            content="滑坡稳定性系数不应小于1.15。",
        )
        terms = extract_terms_from_clause(cl, is_definition_section=False)
        assert terms == []
