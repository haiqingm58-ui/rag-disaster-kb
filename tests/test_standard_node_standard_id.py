"""Tests that all node types include standard_id in write params."""

import pytest

from src.graph.standard import queries as q
from src.graph.standard.models import (
    StandardDocument, Chapter, Clause, Term, Requirement,
    Indicator, Method, StandardObject,
)


class TestNodeStandardId:
    def test_chapter_has_standard_id(self):
        ch = Chapter(standard_id="std-1", chapter_number="1", title="Test")
        assert ch.standard_id == "std-1"

    def test_clause_has_standard_id(self):
        cl = Clause(standard_id="std-1", clause_number="1.1", content="test")
        assert cl.standard_id == "std-1"

    def test_term_has_standard_id(self):
        t = Term(name="test", definition="def", standard_id="std-1")
        assert t.standard_id == "std-1"

    def test_requirement_has_standard_id(self):
        r = Requirement(clause_id="cl-1", text="test", standard_id="std-1")
        assert r.standard_id == "std-1"

    def test_indicator_has_standard_id(self):
        i = Indicator(name="test", standard_id="std-1")
        assert i.standard_id == "std-1"

    def test_method_has_standard_id(self):
        m = Method(name="test", standard_id="std-1")
        assert m.standard_id == "std-1"

    def test_standard_object_has_standard_id(self):
        o = StandardObject(name="test", standard_id="std-1")
        assert o.standard_id == "std-1"


class TestParamBuildersIncludeStandardId:
    def test_term_params(self):
        t = Term(term_id="t-1", name="n", definition="d", standard_id="std-1")
        p = q.term_params(t)
        assert p["standard_id"] == "std-1"

    def test_requirement_params(self):
        r = Requirement(requirement_id="r-1", clause_id="c-1", text="t",
                        standard_id="std-1")
        p = q.requirement_params(r)
        assert p["standard_id"] == "std-1"

    def test_indicator_params(self):
        i = Indicator(indicator_id="i-1", name="n", standard_id="std-1")
        p = q.indicator_params(i)
        assert p["standard_id"] == "std-1"

    def test_method_params(self):
        m = Method(method_id="m-1", name="n", standard_id="std-1")
        p = q.method_params(m)
        assert p["standard_id"] == "std-1"

    def test_object_params(self):
        o = StandardObject(object_id="o-1", name="n", standard_id="std-1")
        p = q.standard_object_params(o)
        assert p["standard_id"] == "std-1"


class TestCypherMergeIncludesStandardId:
    def test_merge_term(self):
        assert "$standard_id" in q.MERGE_TERM

    def test_merge_requirement(self):
        assert "$standard_id" in q.MERGE_REQUIREMENT

    def test_merge_indicator(self):
        assert "$standard_id" in q.MERGE_INDICATOR

    def test_merge_method(self):
        assert "$standard_id" in q.MERGE_METHOD

    def test_merge_standard_object(self):
        assert "$standard_id" in q.MERGE_STANDARD_OBJECT
