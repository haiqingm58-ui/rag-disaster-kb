"""Tests for standard Cypher queries (DDL/DML validity, no real DB)."""

import pytest

from src.graph.standard import queries as q


class TestConstraints:
    def test_all_entity_constraints(self):
        constraints = " ".join(q.CREATE_CONSTRAINTS)
        assert "StandardDocument" in constraints
        assert "Chapter" in constraints
        assert "Clause" in constraints
        assert "Term" in constraints
        assert "Requirement" in constraints
        assert "Indicator" in constraints
        assert "Method" in constraints
        assert "StandardObject" in constraints

    def test_correct_id_fields(self):
        constraints = " ".join(q.CREATE_CONSTRAINTS)
        assert "s.standard_id" in constraints
        assert "c.chapter_id" in constraints
        assert "c.clause_id" in constraints
        assert "t.term_id" in constraints
        assert "r.requirement_id" in constraints
        assert "i.indicator_id" in constraints
        assert "m.method_id" in constraints
        assert "o.object_id" in constraints


class TestMergeStatements:
    def test_merge_standard_params(self):
        params = {"standard_id", "code", "title", "industry", "status",
                   "publish_date", "effective_date", "issuing_body",
                   "source_file", "summary"}
        for p in params:
            assert f"${p}" in q.MERGE_STANDARD, f"Missing ${p} in MERGE_STANDARD"

    def test_merge_chapter_params(self):
        params = {"chapter_id", "standard_id", "chapter_number", "title", "level", "order_index"}
        for p in params:
            assert f"${p}" in q.MERGE_CHAPTER, f"Missing ${p}"

    def test_merge_clause_params(self):
        params = {"clause_id", "standard_id", "chapter_id", "clause_number",
                   "title", "content", "level", "order_index"}
        for p in params:
            assert f"${p}" in q.MERGE_CLAUSE, f"Missing ${p}"

    def test_merge_term_params(self):
        params = {"term_id", "name", "definition", "source_clause_id"}
        for p in params:
            assert f"${p}" in q.MERGE_TERM, f"Missing ${p}"

    def test_merge_requirement_params(self):
        params = {"requirement_id", "clause_id", "text", "obligation",
                   "requirement_type", "confidence"}
        for p in params:
            assert f"${p}" in q.MERGE_REQUIREMENT, f"Missing ${p}"

    def test_merge_indicator_params(self):
        params = {"indicator_id", "name", "value", "operator", "unit",
                   "description", "source_clause_id"}
        for p in params:
            assert f"${p}" in q.MERGE_INDICATOR, f"Missing ${p}"

    def test_merge_method_params(self):
        params = {"method_id", "name", "description", "source_clause_id"}
        for p in params:
            assert f"${p}" in q.MERGE_METHOD, f"Missing ${p}"

    def test_merge_object_params(self):
        params = {"object_id", "name", "object_type", "description"}
        for p in params:
            assert f"${p}" in q.MERGE_STANDARD_OBJECT, f"Missing ${p}"


class TestQueryStatements:
    def test_query_by_code(self):
        assert "$code" in q.QUERY_STANDARD_BY_CODE

    def test_query_chapter_tree(self):
        assert "$standard_id" in q.QUERY_CHAPTER_TREE
        assert "HAS_CHAPTER" in q.QUERY_CHAPTER_TREE
        assert "HAS_CLAUSE" in q.QUERY_CHAPTER_TREE

    def test_query_clauses_by_keyword(self):
        assert "$keyword" in q.QUERY_CLAUSES_BY_KEYWORD
        assert "$limit" in q.QUERY_CLAUSES_BY_KEYWORD

    def test_query_requirements(self):
        assert "$obligation" in q.QUERY_REQUIREMENTS_BY_OBLIGATION

    def test_query_indicators(self):
        assert "Indicator" in q.QUERY_INDICATORS

    def test_query_by_object(self):
        assert "APPLIES_TO" in q.QUERY_CLAUSES_BY_OBJECT
        assert "$object_name" in q.QUERY_CLAUSES_BY_OBJECT

    def test_query_clause_subgraph(self):
        assert "HAS_REQUIREMENT" in q.QUERY_CLAUSE_SUBGRAPH
        assert "HAS_INDICATOR" in q.QUERY_CLAUSE_SUBGRAPH
        assert "USES_METHOD" in q.QUERY_CLAUSE_SUBGRAPH
        assert "APPLIES_TO" in q.QUERY_CLAUSE_SUBGRAPH

    def test_query_standard_full_graph(self):
        assert "REFERENCES" in q.QUERY_STANDARD_FULL_GRAPH

    def test_query_all_requirements_for_standard(self):
        assert "HAS_REQUIREMENT" in q.QUERY_ALL_REQUIREMENTS_FOR_STANDARD

    def test_query_all_indicators_for_standard(self):
        assert "HAS_INDICATOR" in q.QUERY_ALL_INDICATORS_FOR_STANDARD
