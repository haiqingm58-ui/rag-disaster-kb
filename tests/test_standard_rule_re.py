"""Tests for rule-based relation extraction."""

import pytest

from src.graph.standard.re.rule_re import (
    extract_relations_from_clause,
    extract_structural_relations,
)


class TestExtractRelationsFromClause:
    def test_has_requirement(self):
        rels = extract_relations_from_clause(
            "滑坡稳定性系数不应小于1.15。", "3.1.2",
        )
        req_rels = [r for r in rels if r.predicate == "HAS_REQUIREMENT"]
        assert len(req_rels) >= 1

    def test_has_indicator(self):
        rels = extract_relations_from_clause(
            "挡土墙高度不宜大于5m。", "3.2.1",
        )
        ind_rels = [r for r in rels if r.predicate == "HAS_INDICATOR"]
        assert len(ind_rels) >= 1

    def test_defines_term(self):
        rels = extract_relations_from_clause(
            "地质灾害：指自然因素引发的危害人民生命财产安全的地质现象。", "2.1",
        )
        term_rels = [r for r in rels if r.predicate == "DEFINES"]
        assert len(term_rels) >= 1

    def test_uses_method(self):
        rels = extract_relations_from_clause(
            "应采用现场踏勘、遥感解译和数值模拟。", "3.1",
        )
        method_rels = [r for r in rels if r.predicate == "USES_METHOD"]
        # Should find at least 2 methods
        assert len(method_rels) >= 2

    def test_applies_to(self):
        rels = extract_relations_from_clause(
            "滑坡评估应考虑降雨和地震影响。", "3.1",
        )
        obj_rels = [r for r in rels if r.predicate == "APPLIES_TO"]
        assert len(obj_rels) >= 1


class TestExtractStructuralRelations:
    def test_chapter_relations(self):
        chapter_mapping = [("1", "ch-1"), ("2", "ch-2")]
        clause_mapping = []
        rels = extract_structural_relations("std-1", chapter_mapping, clause_mapping)
        ch_rels = [r for r in rels if r.predicate == "HAS_CHAPTER"]
        assert len(ch_rels) == 2

    def test_clause_relations(self):
        chapter_mapping = [("3", "ch-3")]
        clause_mapping = [
            ("3.1", "cl-31", "ch-3"),
            ("3.1.1", "cl-311", "ch-3"),
            ("3.1.2", "cl-312", "ch-3"),
        ]
        rels = extract_structural_relations("std-1", chapter_mapping, clause_mapping)
        # HAS_CLAUSE from standard (3) + from chapter (3) + HAS_SUB_CLAUSE (2: 3.1->3.1.1, 3.1->3.1.2)
        clause_rels = [r for r in rels if r.predicate == "HAS_CLAUSE"]
        sub_rels = [r for r in rels if r.predicate == "HAS_SUB_CLAUSE"]
        assert len(clause_rels) >= 6
        assert len(sub_rels) == 2

    def test_empty(self):
        rels = extract_structural_relations("std-1", [], [])
        assert rels == []
