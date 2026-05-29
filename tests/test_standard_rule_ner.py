"""Tests for rule-based NER entity extraction."""

import pytest

from src.graph.standard.ner.rule_ner import extract_entities
from src.graph.standard.ner.label_schema import ExtractedEntity


class TestRuleNER:
    def test_requirement_shall(self):
        entities = extract_entities("滑坡评估应采用定性与定量相结合的方法。")
        reqs = [e for e in entities if e.entity_type == "REQUIREMENT"]
        assert len(reqs) >= 1
        assert any("采用" in r.text for r in reqs)

    def test_requirement_must(self):
        entities = extract_entities("必须进行现场调查。")
        reqs = [e for e in entities if e.entity_type == "REQUIREMENT"]
        assert len(reqs) >= 1

    def test_requirement_should(self):
        entities = extract_entities("宜采用极限平衡法进行分析。")
        reqs = [e for e in entities if e.entity_type == "REQUIREMENT"]
        assert len(reqs) >= 1

    def test_indicator(self):
        entities = extract_entities("滑坡稳定性系数不应小于1.15。")
        inds = [e for e in entities if e.entity_type == "INDICATOR"]
        assert len(inds) >= 1

    def test_indicator_with_unit(self):
        entities = extract_entities("挡土墙高度不宜大于5m。")
        inds = [e for e in entities if e.entity_type == "INDICATOR"]
        assert len(inds) >= 1

    def test_term(self):
        entities = extract_entities("地质灾害：指自然因素引发的危害人民生命财产安全的地质现象。")
        terms = [e for e in entities if e.entity_type == "TERM"]
        assert len(terms) >= 1

    def test_method(self):
        entities = extract_entities("应采用现场踏勘、遥感解译和工程地质测绘。")
        methods = [e for e in entities if e.entity_type == "METHOD"]
        assert len(methods) >= 1

    def test_disaster_type(self):
        entities = extract_entities("该区域存在滑坡、崩塌和泥石流等地质灾害。")
        dtypes = [e for e in entities if e.entity_type == "DISASTER_TYPE"]
        assert len(dtypes) >= 2  # landslide, collapse at least

    def test_organization(self):
        entities = extract_entities("自然资源部发布了本标准。")
        orgs = [e for e in entities if e.entity_type == "ORGANIZATION"]
        assert len(orgs) >= 1

    def test_standard_code(self):
        entities = extract_entities("应符合GB/T 12345-2020的规定。")
        stds = [e for e in entities if e.entity_type == "STANDARD"]
        assert len(stds) >= 1

    def test_empty_text(self):
        entities = extract_entities("")
        assert entities == []

    def test_entities_are_sorted(self):
        entities = extract_entities("滑坡稳定性系数不应小于1.15。宜采用极限平衡法。")
        for i in range(len(entities) - 1):
            assert entities[i].start_char <= entities[i + 1].start_char

    def test_no_exact_duplicate_spans(self):
        """Entities may partially overlap in rule-based NER (e.g., a REQUIREMENT
        containing a METHOD keyword), but exact duplicates should be deduplicated."""
        entities = extract_entities("滑坡应采用定量评估。应符合标准。")
        spans = [(e.start_char, e.end_char) for e in entities]
        # No exact duplicate spans
        assert len(spans) == len(set(spans)), f"Duplicate spans found: {spans}"
