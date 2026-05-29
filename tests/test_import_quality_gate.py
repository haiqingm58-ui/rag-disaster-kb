"""Tests for the import quality gate logic."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.import_standard_graph import _check_quality


class FakeChapter:
    def __init__(self, chapter_number, title=""):
        self.chapter_number = chapter_number
        self.title = title


class FakeClause:
    def __init__(self, clause_number, title="", content=""):
        self.clause_number = clause_number
        self.title = title
        self.content = content


class FakeDoc:
    def __init__(self, code="TEST"):
        self.code = code


class TestQualityGate:
    def test_too_many_chapters(self):
        doc = FakeDoc()
        chapters = [FakeChapter(str(i)) for i in range(60)]
        clauses = [FakeClause(str(i), f"title{i}") for i in range(10)]
        extraction = {"terms": [], "requirements": [1], "indicators": [1]}
        issues = _check_quality(doc, chapters, clauses, extraction)
        assert any("60" in i or "异常" in i for i in issues)

    def test_no_clauses(self):
        doc = FakeDoc()
        issues = _check_quality(doc, [], [], {"terms": [], "requirements": [], "indicators": []})
        assert any("条款" in i for i in issues)

    def test_term_chapter_no_terms(self):
        doc = FakeDoc()
        chapters = [FakeChapter("3", "术语和定义")]
        clauses = [FakeClause("1", "范围"), FakeClause("3", "术语")]
        extraction = {"terms": [], "requirements": [1], "indicators": [1]}
        issues = _check_quality(doc, chapters, clauses, extraction)
        assert any("术语" in i for i in issues)

    def test_no_requirements_or_indicators(self):
        doc = FakeDoc()
        chapters = [FakeChapter("1", "范围")]
        clauses = [FakeClause("1", "范围", "本文档规定了...")]
        extraction = {"terms": [], "requirements": [], "indicators": []}
        issues = _check_quality(doc, chapters, clauses, extraction)
        assert any("要求" in i or "指标" in i for i in issues)

    def test_pass_quality(self):
        doc = FakeDoc()
        chapters = [FakeChapter(str(i), f"Chapter {i}") for i in range(1, 14)]
        clauses = [
            FakeClause(f"{i}.{j}", f"Clause {i}.{j}", "应执行评估要求。")
            for i in range(1, 14) for j in range(1, 6)
        ] + [FakeClause("3", "术语和定义")]
        extraction = {
            "terms": [FakeTerm(), FakeTerm(), FakeTerm()],
            "requirements": [1] * 20,
            "indicators": [1] * 5,
        }
        issues = _check_quality(doc, chapters, clauses, extraction)
        errors = [i for i in issues if i.startswith("ERROR")]
        assert errors == [], f"Should have no errors, got: {errors}"

    def test_chapters_much_more_than_top_level(self):
        doc = FakeDoc()
        # 30 chapters but only 5 top-level numbers
        chapters = [FakeChapter(str(i)) for i in range(30)]
        clauses = [FakeClause(str(i % 5)) for i in range(30)]
        extraction = {"terms": [], "requirements": [1], "indicators": []}
        issues = _check_quality(doc, chapters, clauses, extraction)
        assert any("远大于" in i for i in issues)


class FakeTerm:
    def __init__(self, name="test"):
        self.name = name
