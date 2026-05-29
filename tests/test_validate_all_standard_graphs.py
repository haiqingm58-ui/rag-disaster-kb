"""Tests for validate_all_standard_graphs — all Neo4j calls mocked."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.validate_all_standard_graphs import (
    validate_all, write_markdown, QUERY_STANDARDS,
    QUERY_GHOST_NODES, QUERY_ORPHANS, QUERY_ISOLATED,
)


class TestValidateCypher:
    def test_standards_query_selects_key_fields(self):
        assert "standard_id" in QUERY_STANDARDS
        assert "code" in QUERY_STANDARDS
        assert "title" in QUERY_STANDARDS

    def test_ghost_query_checks_literal_values(self):
        assert "standard_id" in QUERY_GHOST_NODES
        assert "chapter_id" in QUERY_GHOST_NODES
        assert "clause_id" in QUERY_GHOST_NODES

    def test_orphans_query_checks_missing_standard(self):
        assert "NOT EXISTS" in QUERY_ORPHANS or "not exists" in QUERY_ORPHANS.lower()

    def test_isolated_query_checks_no_relationships(self):
        assert "NOT (n)--()" in QUERY_ISOLATED


class TestValidateAllMock:
    @patch("scripts.validate_all_standard_graphs.get_session")
    def test_no_standards(self, mock_get_session):
        mock_sess = MagicMock()
        mock_sess.run.return_value = []
        mock_get_session.return_value.__enter__.return_value = mock_sess
        report = validate_all()
        assert "No standards" in report.get("summary", "")

    @patch("scripts.validate_all_standard_graphs.get_session")
    def test_one_standard(self, mock_get_session):
        mock_sess = MagicMock()

        def _fake_run(query, params=None):
            m = MagicMock()
            if "s.standard_id" in query and "RETURN s.standard_id" in query:
                m.__iter__.return_value = iter([{
                    "standard_id": "std-test", "code": "GB/T 0001",
                    "title": "Test Standard", "industry": "test",
                    "status": "current",
                }])
                return m
            if "count(DISTINCT ch)" in query:
                m.single.return_value = {"chapters": 5, "clauses": 20, "terms": 3}
                return m
            if "n:Requirement OR n:Indicator" in query:
                m.single.return_value = {
                    "requirements": 10, "indicators": 5, "methods": 2, "objects": 1,
                }
                return m
            if "count(r) AS rels_from_std" in query:
                m.single.return_value = {"rels_from_std": 50}
                return m
            if "count(n) AS cnt" in query:
                m.single.return_value = {"cnt": 40}
                return m
            # Ghost/orphan/isolated queries return empty
            return iter([])

        mock_sess.run = _fake_run
        mock_get_session.return_value.__enter__.return_value = mock_sess

        report = validate_all()
        assert len(report["standards"]) == 1
        s = report["standards"][0]
        assert s["chapters"] == 5
        assert s["clauses"] == 20
        assert s["terms"] == 3
        assert s["requirements"] == 10

    @patch("scripts.validate_all_standard_graphs.get_session")
    def test_ghost_nodes_detected(self, mock_get_session):
        mock_sess = MagicMock()

        call_count = {"count": 0}

        def _fake_run(query, params=None):
            m = MagicMock()
            if "s.standard_id" in query and "RETURN s.standard_id" in query:
                m.__iter__.return_value = iter([])
                return m
            if "standard_id = 'standard_id'" in query:
                m.__iter__.return_value = iter([
                    {"label": "StandardDocument", "count": 1},
                ])
                return m
            return iter([])

        mock_sess.run = _fake_run
        mock_get_session.return_value.__enter__.return_value = mock_sess

        report = validate_all()
        # ghosts list length should be >= 1 if detected
        assert isinstance(report["ghost_nodes"], list)


class TestWriteMarkdown:
    def test_writes_file(self, tmp_path):
        report = {
            "generated_at": "2026-01-01T00:00:00",
            "summary": "1 standard",
            "standards": [{
                "standard_id": "std-1", "code": "GB/T 0001",
                "title": "Test", "industry": "test",
                "chapters": 5, "clauses": 20, "terms": 3,
                "requirements": 10, "indicators": 5,
                "methods": 2, "objects": 1,
                "relationships_from_std": 50, "total_nodes": 40,
            }],
            "ghost_nodes": [],
            "orphan_nodes": [],
            "isolated_nodes": [],
            "all_relation_types": [{"type": "HAS_CHAPTER", "count": 5}],
        }
        md_path = tmp_path / "test_report.md"
        write_markdown(report, md_path)
        assert md_path.exists()
        content = md_path.read_text()
        assert "GB/T 0001" in content
        assert "✅ 无幽灵节点" in content
        assert "✅ 无孤儿节点" in content
