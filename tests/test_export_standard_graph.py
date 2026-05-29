"""Tests for export_standard_graph — mock Neo4j, no real connection."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.export_standard_graph import (
    _sanitize_path, _build_cypher, _build_schema_md,
    _build_import_guide_md, _build_summary_md,
)


class TestSanitizePath:
    def test_strips_absolute_path(self):
        assert _sanitize_path("/Users/georisk/Documents/test.pdf") == "test.pdf"

    def test_preserves_relative_path(self):
        assert _sanitize_path("data/test.pdf") == "test.pdf"

    def test_none_value(self):
        assert _sanitize_path(None) is None
        assert _sanitize_path("") == ""


class TestBuildCypher:
    def test_no_internal_neo4j_ids(self):
        nodes = [{
            "id": "4:abc:123",
            "labels": ["StandardDocument"],
            "properties": {"standard_id": "std-001", "code": "GB/T 0001", "title": "Test"},
        }, {
            "id": "4:def:456",
            "labels": ["Chapter"],
            "properties": {"chapter_id": "ch-001", "standard_id": "std-001", "title": "Ch1"},
        }]
        rels = [{
            "id": "5:ghi:789",
            "type": "HAS_CHAPTER",
            "start_node": "4:abc:123",
            "end_node": "4:def:456",
        }]
        cypher = _build_cypher(nodes, rels)
        # Should use stable IDs, not Neo4j internal IDs
        assert "std-001" in cypher
        assert "ch-001" in cypher
        assert "HAS_CHAPTER" in cypher
        # Should NOT contain Neo4j element IDs
        assert "4:abc:123" not in cypher
        assert "4:def:456" not in cypher

    def test_no_api_key_in_cypher(self):
        nodes = [{
            "id": "4:abc",
            "labels": ["StandardDocument"],
            "properties": {"standard_id": "std-001", "code": "GB/T 0001"},
        }]
        cypher = _build_cypher(nodes, [])
        assert "DEEPSEEK" not in cypher
        assert "sk-" not in cypher.lower()

    def test_no_password_in_cypher(self):
        nodes = [{
            "id": "4:abc",
            "labels": ["StandardDocument"],
            "properties": {"standard_id": "std-001"},
        }]
        cypher = _build_cypher(nodes, [])
        assert "password" not in cypher.lower()
        assert "NEO4J_PASSWORD" not in cypher

    def test_cypher_uses_merge(self):
        nodes = [{
            "id": "4:abc",
            "labels": ["StandardDocument"],
            "properties": {"standard_id": "std-001", "code": "GB/T 0001", "title": "Test"},
        }]
        cypher = _build_cypher(nodes, [])
        assert "MERGE" in cypher

    def test_empty_nodes(self):
        result = _build_cypher([], [])
        # Should not crash, should return a string (header only)
        assert isinstance(result, str)
        assert "MERGE" not in result  # No nodes to create


class TestBuildSchema:
    def test_mentions_all_node_types(self):
        schema = _build_schema_md()
        for t in ["StandardDocument", "Chapter", "Clause", "Term",
                   "Requirement", "Indicator", "Method", "StandardObject"]:
            assert t in schema

    def test_mentions_all_relations(self):
        schema = _build_schema_md()
        for r in ["HAS_CHAPTER", "HAS_CLAUSE", "HAS_SUB_CLAUSE", "DEFINES",
                   "HAS_REQUIREMENT", "HAS_INDICATOR", "USES_METHOD", "APPLIES_TO"]:
            assert r in schema


class TestBuildImportGuide:
    def test_mentions_neo4j(self):
        guide = _build_import_guide_md()
        assert "Neo4j" in guide

    def test_mentions_cypher_shell(self):
        guide = _build_import_guide_md()
        assert "cypher-shell" in guide


class TestBuildSummary:
    def test_includes_stats(self):
        stats = {
            "exported_at": "2026-01-01T00:00:00",
            "standard_count": 2,
            "node_count": 100,
            "rel_count": 200,
            "standards": [{"code": "GB/T 0001", "title": "Test"}],
            "files": ["nodes.json", "graph.cypher"],
        }
        md = _build_summary_md(stats)
        assert "2" in md
        assert "100" in md
        assert "200" in md
        assert "GB/T 0001" in md
        assert "✅" in md
