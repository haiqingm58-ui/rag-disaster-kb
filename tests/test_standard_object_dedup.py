"""Tests for StandardObject deduplication."""

import pytest

from src.graph.standard.models import Clause, StandardObject
from src.graph.standard.extractor import extract_objects, extract_from_standard


class TestExtractObjectsDedup:
    def test_different_clauses_same_object(self):
        """Two clauses mentioning '滑坡' should return only one StandardObject."""
        clauses = [
            Clause(clause_id="cl-1", standard_id="std-1", clause_number="4.1",
                   content="滑坡评估应考虑降雨影响。"),
            Clause(clause_id="cl-2", standard_id="std-1", clause_number="4.2",
                   content="滑坡治理应采用工程措施。"),
            Clause(clause_id="cl-3", standard_id="std-1", clause_number="5.1",
                   content="崩塌评估应考虑地震影响。"),
        ]
        result = extract_from_standard(clauses)
        objects = result["objects"]
        names = [o.name for o in objects]
        # '滑坡' should appear once, not twice
        assert names.count("滑坡") == 1
        # '崩塌' should appear once
        assert names.count("崩塌") == 1

    def test_no_duplicates_within_same_standard(self):
        clauses = [
            Clause(clause_id=f"cl-{i}", standard_id="std-1",
                   clause_number=f"4.{i}",
                   content=f"滑坡监测点应定期检查。钻孔深度不应小于10m。")
            for i in range(10)
        ]
        result = extract_from_standard(clauses)
        objects = result["objects"]
        names = [o.name for o in objects]
        assert names.count("滑坡") == 1
        assert names.count("钻孔") == 1
        assert names.count("监测点") == 1

    def test_single_clause(self):
        cl = Clause(clause_id="cl-1", standard_id="std-1", clause_number="4.1",
                    content="滑坡和泥石流评估。")
        objs = extract_objects(cl)
        assert len(objs) <= 2
