"""Tests for graph data models: dataclasses, enums, serialization."""

from datetime import datetime

import pytest

from src.graph.models import (
    DisasterEvent,
    Attribute,
    Location,
    SourceDocument,
    DisasterType,
    EventStatus,
    AttrCategory,
    DataType,
    _new_id,
    _safe_float,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def test_new_id_prefix():
    assert _new_id("evt").startswith("evt-")
    assert _new_id("attr").startswith("attr-")
    assert _new_id("loc").startswith("loc-")
    assert _new_id("doc").startswith("doc-")


def test_new_id_uniqueness():
    ids = {_new_id("evt") for _ in range(100)}
    assert len(ids) == 100


def test_safe_float():
    assert _safe_float("1.5") == 1.5
    assert _safe_float(3) == 3.0
    assert _safe_float(None) == 0.0
    assert _safe_float("abc") == 0.0


# ── Enums ─────────────────────────────────────────────────────────────────────

class TestDisasterType:
    def test_known_values(self):
        assert DisasterType("earthquake") == DisasterType.EARTHQUAKE
        assert DisasterType("flood") == DisasterType.FLOOD
        assert DisasterType("tsunami") == DisasterType.TSUNAMI

    def test_unknown_falls_back_to_other(self):
        assert DisasterType("nonexistent") == DisasterType.OTHER
        assert DisasterType("暴风雪") == DisasterType.OTHER

    def test_missing_with_non_string_returns_none(self):
        assert DisasterType._missing_(123) is None


class TestEventStatus:
    def test_values(self):
        assert EventStatus("ongoing") == EventStatus.ONGOING
        assert EventStatus("concluded") == EventStatus.CONCLUDED
        assert EventStatus("unconfirmed") == EventStatus.UNCONFIRMED


class TestAttrCategory:
    def test_values(self):
        assert AttrCategory("magnitude") == AttrCategory.MAGNITUDE
        assert AttrCategory("casualties") == AttrCategory.CASUALTIES
        assert AttrCategory("economic_loss") == AttrCategory.ECONOMIC_LOSS


# ── DisasterEvent ─────────────────────────────────────────────────────────────

class TestDisasterEvent:
    def test_minimal_creation(self):
        evt = DisasterEvent(name="测试地震", disaster_type="earthquake")
        assert evt.name == "测试地震"
        assert evt.disaster_type == DisasterType.EARTHQUAKE
        assert evt.status == EventStatus.UNCONFIRMED
        assert evt.confidence == 0.0
        assert evt.event_id.startswith("evt-")

    def test_full_creation(self):
        t = datetime(2026, 5, 20, 8, 30)
        evt = DisasterEvent(
            name="云南漾濞5.2级地震",
            disaster_type="earthquake",
            start_time=t,
            status="ongoing",
            summary="test",
            confidence=0.92,
        )
        assert evt.start_time == t
        assert evt.confidence == 0.92

    def test_confidence_clamped(self):
        evt = DisasterEvent(name="x", disaster_type="earthquake", confidence=1.5)
        assert evt.confidence == 1.0
        evt2 = DisasterEvent(name="x", disaster_type="earthquake", confidence=-0.5)
        assert evt2.confidence == 0.0

    def test_to_dict(self):
        t = datetime(2026, 5, 20, 8, 30)
        evt = DisasterEvent(
            event_id="evt-test123",
            name="test",
            disaster_type="earthquake",
            start_time=t,
            status="ongoing",
            confidence=0.9,
        )
        d = evt.to_dict()
        assert d["event_id"] == "evt-test123"
        assert d["disaster_type"] == "earthquake"
        assert d["status"] == "ongoing"
        assert d["start_time"] == "2026-05-20T08:30:00"
        assert d["end_time"] is None
        assert d["confidence"] == 0.9

    def test_from_dict(self):
        d = {
            "event_id": "evt-fromdict",
            "name": "广东暴雨",
            "disaster_type": "flood",
            "start_time": "2026-05-15T12:00:00",
            "end_time": None,
            "status": "concluded",
            "summary": "test summary",
            "confidence": 0.7,
        }
        evt = DisasterEvent.from_dict(d)
        assert evt.event_id == "evt-fromdict"
        assert evt.name == "广东暴雨"
        assert evt.disaster_type == DisasterType.FLOOD
        assert evt.status == EventStatus.CONCLUDED
        assert evt.start_time == datetime(2026, 5, 15, 12, 0)

    def test_to_dict_from_dict_roundtrip(self):
        evt = DisasterEvent(
            name="roundtrip",
            disaster_type="typhoon",
            start_time=datetime(2026, 5, 10, 6, 0),
            status="ongoing",
            summary="roundtrip test",
            confidence=0.88,
        )
        evt2 = DisasterEvent.from_dict(evt.to_dict())
        assert evt2.name == evt.name
        assert evt2.disaster_type == evt.disaster_type
        assert evt2.start_time == evt.start_time
        assert evt2.status == evt.status
        assert evt2.confidence == evt.confidence


# ── Attribute ─────────────────────────────────────────────────────────────────

class TestAttribute:
    def test_minimal_creation(self):
        attr = Attribute(event_id="evt-1", key="magnitude", value="5.2")
        assert attr.attr_id.startswith("attr-")
        assert attr.category == AttrCategory.OTHER
        assert attr.data_type == DataType.STRING
        assert attr.update_time is not None

    def test_full_creation(self):
        attr = Attribute(
            event_id="evt-1",
            key="casualties_death",
            value="12",
            unit="人",
            category="casualties",
            data_type="number",
        )
        assert attr.key == "casualties_death"
        assert attr.value == "12"
        assert attr.category == AttrCategory.CASUALTIES
        assert attr.data_type == DataType.NUMBER

    def test_to_dict(self):
        attr = Attribute(
            attr_id="attr-x",
            event_id="evt-x",
            key="magnitude",
            value="6.0",
            unit="Mw",
            category="magnitude",
            data_type="number",
        )
        d = attr.to_dict()
        assert d["attr_id"] == "attr-x"
        assert d["key"] == "magnitude"
        assert d["category"] == "magnitude"
        assert d["data_type"] == "number"

    def test_from_dict(self):
        d = {
            "attr_id": "attr-fd",
            "event_id": "evt-fd",
            "key": "affected_area_km2",
            "value": "500",
            "category": "environment",
            "data_type": "number",
        }
        attr = Attribute.from_dict(d)
        assert attr.attr_id == "attr-fd"
        assert attr.key == "affected_area_km2"

    def test_to_dict_from_dict_roundtrip(self):
        attr = Attribute(
            event_id="evt-r",
            key="evacuated",
            value="30000",
            unit="人",
            category="evacuation",
            data_type="number",
            source="rule_extraction",
        )
        attr2 = Attribute.from_dict(attr.to_dict())
        assert attr2.key == attr.key
        assert attr2.value == attr.value
        assert attr2.category == attr.category


# ── Location ──────────────────────────────────────────────────────────────────

class TestLocation:
    def test_creation(self):
        loc = Location(name="漾濞县", latitude=25.67, longitude=99.92, country="中国")
        assert loc.loc_id.startswith("loc-")
        assert loc.latitude == 25.67
        assert loc.longitude == 99.92

    def test_coercion(self):
        loc = Location(name="test", latitude="25.67", longitude="99.92")
        assert isinstance(loc.latitude, float)
        assert isinstance(loc.longitude, float)

    def test_invalid_coercion(self):
        loc = Location(name="test", latitude="abc", longitude=None)
        assert loc.latitude == 0.0
        assert loc.longitude == 0.0

    def test_to_dict_from_dict_roundtrip(self):
        loc = Location(
            loc_id="loc-r",
            name="四川甘孜",
            latitude=30.05,
            longitude=101.96,
            address="四川省甘孜藏族自治州",
            country="中国",
        )
        d = loc.to_dict()
        loc2 = Location.from_dict(d)
        assert loc2.name == loc.name
        assert loc2.latitude == loc.latitude
        assert loc2.address == loc.address


# ── SourceDocument ────────────────────────────────────────────────────────────

class TestSourceDocument:
    def test_creation(self):
        doc = SourceDocument(title="测试新闻", source_type="news")
        assert doc.doc_id.startswith("doc-")
        assert doc.source_type == "news"

    def test_to_dict(self):
        t = datetime(2026, 5, 20, 12, 0)
        doc = SourceDocument(
            doc_id="doc-t",
            title="新闻标题",
            url="https://example.com",
            source_type="report",
            publish_time=t,
            content_snippet="摘要内容",
        )
        d = doc.to_dict()
        assert d["publish_time"] == "2026-05-20T12:00:00"
        assert d["url"] == "https://example.com"

    def test_from_dict(self):
        d = {
            "doc_id": "doc-fd",
            "title": "from dict",
            "source_type": "social_media",
            "publish_time": "2026-05-20T12:00:00",
        }
        doc = SourceDocument.from_dict(d)
        assert doc.doc_id == "doc-fd"
        assert doc.publish_time == datetime(2026, 5, 20, 12, 0)

    def test_from_dict_no_time(self):
        doc = SourceDocument.from_dict({"title": "no time"})
        assert doc.publish_time is None
        assert doc.content_snippet == ""
