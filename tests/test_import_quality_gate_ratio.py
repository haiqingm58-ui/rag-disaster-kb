"""Tests for ratio-based quality gate rules."""

import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.import_standard_graph import _check_quality


class FakeChapter:
    def __init__(self, number, title=""):
        self.chapter_number = number; self.title = title

class FakeClause:
    def __init__(self, number, title="", content=""):
        self.clause_number = number; self.title = title; self.content = content

class FakeDoc:
    code = "TEST"


class TestRatioRules:
    def test_req_too_high_ratio(self):
        """457 reqs for 26 clauses should trigger ERROR."""
        doc = FakeDoc()
        chapters = [FakeChapter(str(i), f"Ch{i}") for i in range(1, 23)]
        clauses = [FakeClause(f"{i}.1", f"Cl{i}") for i in range(1, 27)]
        extraction = {"terms": [1], "requirements": [1]*457, "indicators": [1]*5}
        issues = _check_quality(doc, chapters, clauses, extraction)
        assert any("Requirements/Clauses" in i for i in issues)

    def test_indicator_too_high_ratio(self):
        """100 indicators for 26 clauses should trigger ERROR."""
        doc = FakeDoc()
        chapters = [FakeChapter(str(i), f"Ch{i}") for i in range(1, 23)]
        clauses = [FakeClause(f"{i}.1", f"Cl{i}") for i in range(1, 27)]
        extraction = {"terms": [1], "requirements": [1]*5, "indicators": [1]*100}
        issues = _check_quality(doc, chapters, clauses, extraction)
        assert any("Indicators/Clauses" in i for i in issues)

    def test_few_clauses_vs_chapters(self):
        """26 clauses vs 22 chapters should trigger ERROR."""
        doc = FakeDoc()
        chapters = [FakeChapter(str(i), f"Ch{i}") for i in range(1, 23)]
        clauses = [FakeClause(f"{i}.1", f"Cl{i}") for i in range(1, 27)]
        extraction = {"terms": [1], "requirements": [1], "indicators": [1]}
        issues = _check_quality(doc, chapters, clauses, extraction)
        assert any("Clauses" in i and "Chapters" in i and "3 倍" in i for i in issues)

    def test_normal_passes(self):
        """Normal data should not trigger ratio errors."""
        doc = FakeDoc()
        chapters = [FakeChapter(str(i), f"Ch{i}") for i in range(1, 16)]
        clauses = [FakeClause(f"{i}.{j}", f"C{i}.{j}", "应执行标准。")
                   for i in range(1, 16) for j in range(1, 11)]
        n_cl = len(clauses)
        extraction = {"terms": [1]*10, "requirements": [1]*(n_cl*2), "indicators": [1]*20}
        issues = _check_quality(doc, chapters, clauses, extraction)
        errors = [i for i in issues if i.startswith("ERROR")]
        assert errors == [], f"Should pass but got errors: {errors}"
