"""Tests for extractor.py — LLM extraction and rule-based fallback."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.graph.models import (
    DisasterEvent,
    Attribute,
    Location,
    SourceDocument,
    DisasterType,
    AttrCategory,
)
from src.graph.extractor import (
    extract_from_news,
    _rule_extract,
    _clean_json_response,
    _safe_parse_datetime,
    _parse_llm_result,
    _classify_disaster_type,
    _extract_time,
    _extract_location_name,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def test_clean_json_response_no_fence():
    assert _clean_json_response('{"a": 1}') == '{"a": 1}'


def test_clean_json_response_with_fence():
    raw = '```json\n{"a": 1}\n```'
    assert _clean_json_response(raw) == '{"a": 1}'


def test_clean_json_response_no_newline():
    raw = '```{"a": 1}```'
    assert _clean_json_response(raw) == '{"a": 1}'


def test_safe_parse_datetime_valid():
    from datetime import datetime
    assert _safe_parse_datetime("2026-05-20T08:30:00") == datetime(2026, 5, 20, 8, 30)


def test_safe_parse_datetime_none():
    assert _safe_parse_datetime(None) is None


def test_safe_parse_datetime_invalid():
    assert _safe_parse_datetime("not-a-date") is None


# ── Rule extraction ───────────────────────────────────────────────────────────

class TestRuleExtraction:
    def test_earthquake_with_magnitude(self):
        text = "2026年5月20日8时30分，云南大理州漾濞县发生5.2级地震，震源深度10千米。"
        result = _rule_extract(text)
        assert result["method"] == "rule"
        assert result["event"] is not None
        assert result["event"].disaster_type == DisasterType.EARTHQUAKE
        assert "5.2" in result["event"].name or "漾濞" in result["event"].name

        mag_attrs = [a for a in result["attributes"] if a.key == "magnitude"]
        assert len(mag_attrs) == 1
        assert mag_attrs[0].value == "5.2"
        assert mag_attrs[0].category == AttrCategory.MAGNITUDE

    def test_earthquake_with_casualties(self):
        text = "四川甘孜州发生6.8级地震，造成12人死亡、35人受伤，紧急转移安置3000人。"
        result = _rule_extract(text)
        assert result["event"].disaster_type == DisasterType.EARTHQUAKE

        attrs_by_key = {a.key: a.value for a in result["attributes"]}
        assert attrs_by_key.get("magnitude") == "6.8"
        assert attrs_by_key.get("casualties_death") == "12"
        assert attrs_by_key.get("casualties_injured") == "35"
        assert attrs_by_key.get("evacuated") == "3000"

    def test_flood_detection(self):
        text = "湖南省遭遇严重洪涝灾害，多条河流超警戒水位，已转移安置2.5万人。"
        result = _rule_extract(text)
        assert result["event"].disaster_type == DisasterType.FLOOD
        assert any(a.key == "evacuated" for a in result["attributes"])

    def test_typhoon_detection(self):
        text = "台风'山竹'在广东沿海登陆，中心最大风力14级。"
        result = _rule_extract(text)
        assert result["event"].disaster_type == DisasterType.TYPHOON

    def test_wildfire_detection(self):
        text = "四川凉山州发生森林火灾，过火面积超过100公顷。"
        result = _rule_extract(text)
        assert result["event"].disaster_type == DisasterType.WILDFIRE

    def test_location_extraction(self):
        text = "四川省甘孜藏族自治州泸定县发生地震。"
        loc = _extract_location_name(text)
        assert loc is not None
        assert "四川" in loc or "甘孜" in loc or "泸定" in loc

    def test_time_extraction(self):
        text = "2026年5月20日8时30分发生地震。"
        t = _extract_time(text)
        assert t is not None
        assert "2026-05-20" in t

    def test_empty_text(self):
        result = _rule_extract("")
        assert result["method"] == "rule"
        assert result["event"] is not None  # Still creates an event with type=other
        assert result["event"].confidence == 0.3

    def test_source_document_present(self):
        result = _rule_extract("云南发生地震。")
        assert result["source_document"] is not None
        assert result["source_document"].source_type == "news"


# ── LLM result parser ─────────────────────────────────────────────────────────

class TestParseLLMResult:
    def test_parses_event(self):
        data = {
            "event": {
                "name": "云南地震",
                "disaster_type": "earthquake",
                "start_time": "2026-05-20T08:30:00",
                "status": "ongoing",
                "summary": "summary text",
                "confidence": 0.9,
            },
            "attributes": [
                {"key": "magnitude", "value": "5.2", "unit": "Mw",
                 "category": "magnitude", "data_type": "number"},
            ],
            "location": {
                "name": "漾濞县", "latitude": 25.67, "longitude": 99.92, "country": "中国",
            },
            "source_document": {
                "title": "新闻标题", "source_type": "news",
            },
        }
        result = _parse_llm_result(data)
        assert result["event"] is not None
        assert result["event"].name == "云南地震"
        assert result["event"].disaster_type == DisasterType.EARTHQUAKE
        assert len(result["attributes"]) == 1
        assert result["attributes"][0].key == "magnitude"
        assert result["location"] is not None
        assert result["location"].name == "漾濞县"
        assert result["source_document"] is not None

    def test_parses_missing_location(self):
        data = {
            "event": {"name": "test", "disaster_type": "flood", "confidence": 0.5},
            "attributes": [],
            "location": {},
            "source_document": {},
        }
        result = _parse_llm_result(data)
        assert result["event"] is not None
        assert result["location"] is None
        assert result["source_document"] is None

    def test_parses_empty_event(self):
        data = {"event": {}, "attributes": [], "location": {}, "source_document": {}}
        result = _parse_llm_result(data)
        assert result["event"] is None


# ── LLM extraction (with mock) ────────────────────────────────────────────────

class TestExtractFromNewsWithMock:
    def test_llm_successful(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "event": {
                "name": "云南地震",
                "disaster_type": "earthquake",
                "start_time": "2026-05-20T08:30:00",
                "status": "ongoing",
                "summary": "summary",
                "confidence": 0.9,
            },
            "attributes": [
                {"key": "magnitude", "value": "5.2", "unit": "Mw",
                 "category": "magnitude", "data_type": "number"},
            ],
            "location": {"name": "漾濞县", "latitude": 25.67, "longitude": 99.92},
            "source_document": {"title": "新闻", "source_type": "news"},
        }, ensure_ascii=False)
        mock_llm.invoke.return_value = mock_response

        result = extract_from_news("云南发生5.2级地震", llm=mock_llm, fallback=False)
        assert result["method"] == "llm"
        assert result["error"] == ""
        assert result["event"].name == "云南地震"
        assert len(result["attributes"]) == 1
        assert result["location"].name == "漾濞县"

    def test_llm_returns_markdown_fenced_json(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '```json\n{"event": {"name": "test", "disaster_type": "earthquake", "confidence": 0.5}, "attributes": [], "location": {}, "source_document": {}}\n```'
        mock_llm.invoke.return_value = mock_response

        result = extract_from_news("test text", llm=mock_llm, fallback=False)
        assert result["method"] == "llm"
        assert result["event"].name == "test"

    def test_llm_fails_with_fallback(self):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("API error")

        result = extract_from_news("云南大理发生5.2级地震", llm=mock_llm, fallback=True)
        assert result["method"] == "rule"
        assert result["event"] is not None
        assert "LLM failed" in result["error"]

    def test_llm_fails_without_fallback(self):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("API error")

        result = extract_from_news("test", llm=mock_llm, fallback=False)
        assert result["method"] == "none"
        assert result["event"] is None
        assert "LLM call failed" in result["error"]

    def test_llm_returns_bad_json_with_fallback(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "this is not json at all {{{"
        mock_llm.invoke.return_value = mock_response

        result = extract_from_news("云南大理发生5.2级地震", llm=mock_llm, fallback=True)
        assert result["method"] == "rule"
        assert "LLM failed" in result["error"]

    def test_empty_text(self):
        mock_llm = MagicMock()
        result = extract_from_news("", llm=mock_llm)
        assert result["method"] == "none"
        assert result["error"] == "Empty input text"
        mock_llm.invoke.assert_not_called()

    def test_llm_returns_empty_event_with_fallback(self):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "event": {}, "attributes": [], "location": {}, "source_document": {},
        })
        mock_llm.invoke.return_value = mock_response

        result = extract_from_news("云南大理发生5.2级地震", llm=mock_llm, fallback=True)
        assert result["method"] == "rule"
        assert "LLM returned no event" in result["error"]
