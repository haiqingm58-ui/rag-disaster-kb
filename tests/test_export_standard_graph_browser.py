"""Tests for graph browser export — mock Neo4j."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from scripts.export_standard_graph_browser import (
    _fetch_graph, _build_search_index, _build_html,
)


@pytest.fixture
def sample_data():
    return {
        "generated_at": "2026-01-01T00:00:00",
        "standards": [
            {"standard_id": "std-001", "code": "GB/T 0001", "title": "测试标准",
             "industry": "test", "source_file": "test.pdf",
             "chapters": 3, "clauses": 10, "terms": 2, "requirements": 5,
             "indicators": 3, "methods": 1, "objects": 1},
        ],
        "chapters": [{"code": "GB/T 0001", "number": "1", "title": "范围", "id": "ch-1"}],
        "clauses": [{"code": "GB/T 0001", "number": "1.1", "title": "测试",
                      "content": "应采用定量方法评估。", "id": "cl-1",
                      "chapter_id": "ch-1", "level": 2}],
        "terms": [{"code": "GB/T 0001", "name": "滑坡", "definition": "岩土体下滑。",
                    "id": "t-1", "source_clause_id": "cl-1"}],
        "requirements": [{"code": "GB/T 0001", "clause_number": "4.1",
                           "text": "应采用方法。", "obligation": "shall", "id": "r-1"}],
        "indicators": [{"code": "GB/T 0001", "clause_number": "4.2",
                         "name": "系数", "value": "1.15", "operator": ">=", "unit": ""}],
        "methods": [{"code": "GB/T 0001", "clause_number": "4.3",
                      "name": "极限平衡法", "description": "边坡稳定性分析方法"}],
        "objects": [{"code": "GB/T 0001", "clause_number": "4.4",
                      "name": "滑坡", "object_type": "process"}],
        "node_counts": [{"type": "Clause", "count": 10}, {"type": "Term", "count": 2}],
        "search_index": [],
    }


class TestBuildSearchIndex:
    def test_indexes_terms(self, sample_data):
        idx = _build_search_index(sample_data)
        assert any("滑坡" in i["text"] for i in idx)

    def test_indexes_clauses(self, sample_data):
        idx = _build_search_index(sample_data)
        assert any("定量方法" in i["text"] for i in idx)


class TestBuildHtml:
    def test_contains_standard_title(self, sample_data):
        data_json = json.dumps(sample_data, ensure_ascii=False)
        html = _build_html().replace("__DATA_PLACEHOLDER__", data_json)
        assert "GB/T 0001" in html
        assert "测试标准" in html

    def test_no_api_key(self, sample_data):
        data_json = json.dumps(sample_data, ensure_ascii=False)
        html = _build_html().replace("__DATA_PLACEHOLDER__", data_json)
        assert "DEEPSEEK" not in html
        assert "sk-" not in html.lower()

    def test_no_absolute_path(self, sample_data):
        data_json = json.dumps(sample_data, ensure_ascii=False)
        html = _build_html().replace("__DATA_PLACEHOLDER__", data_json)
        assert "/Users/" not in html

    def test_self_contained(self, sample_data):
        data_json = json.dumps(sample_data, ensure_ascii=False)
        html = _build_html().replace("__DATA_PLACEHOLDER__", data_json)
        # No CDN dependencies
        assert "cdn" not in html.lower()
        assert "http://" not in html
        assert "https://" not in html
