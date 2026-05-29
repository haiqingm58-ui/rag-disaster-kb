"""Disaster knowledge graph data model.

Core entities: DisasterEvent, Attribute, Location, SourceDocument.
Relationships:
  DisasterEvent -[HAS_ATTRIBUTE]-> Attribute
  DisasterEvent -[OCCURRED_AT]-> Location
  DisasterEvent -[REPORTED_BY]-> SourceDocument
  Attribute    -[EVIDENCED_BY]-> SourceDocument
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional


# ── Enums ────────────────────────────────────────────────────────────────────

class DisasterType(str, Enum):
    EARTHQUAKE = "earthquake"
    FLOOD = "flood"
    LANDSLIDE = "landslide"
    MUDFLOW = "mudflow"
    TYPHOON = "typhoon"
    WILDFIRE = "wildfire"
    DROUGHT = "drought"
    VOLCANO = "volcano"
    TSUNAMI = "tsunami"
    OTHER = "other"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            return cls.OTHER
        return None


class EventStatus(str, Enum):
    ONGOING = "ongoing"
    CONCLUDED = "concluded"
    UNCONFIRMED = "unconfirmed"


class AttrCategory(str, Enum):
    MAGNITUDE = "magnitude"
    CASUALTIES = "casualties"
    ECONOMIC_LOSS = "economic_loss"
    EVACUATION = "evacuation"
    RESCUE = "rescue"
    ENVIRONMENT = "environment"
    WARNING = "warning"
    OTHER = "other"


class DataType(str, Enum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATETIME = "datetime"


# ── Helper ────────────────────────────────────────────────────────────────────

def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ── Core entities ─────────────────────────────────────────────────────────────

@dataclass
class DisasterEvent:
    """A disaster event node in the knowledge graph."""

    name: str
    disaster_type: DisasterType
    event_id: str = field(default_factory=lambda: _new_id("evt"))
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: EventStatus = EventStatus.UNCONFIRMED
    summary: str = ""
    confidence: float = 0.0

    def __post_init__(self):
        if isinstance(self.disaster_type, str):
            self.disaster_type = DisasterType(self.disaster_type)
        if isinstance(self.status, str):
            self.status = EventStatus(self.status)
        self.confidence = max(0.0, min(1.0, _safe_float(self.confidence, 0.0)))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["disaster_type"] = self.disaster_type.value
        d["status"] = self.status.value
        d["start_time"] = self.start_time.isoformat() if self.start_time else None
        d["end_time"] = self.end_time.isoformat() if self.end_time else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "DisasterEvent":
        start = d.get("start_time")
        end = d.get("end_time")
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)
        return cls(
            event_id=d.get("event_id", _new_id("evt")),
            name=d.get("name", ""),
            disaster_type=DisasterType(d.get("disaster_type", "other")),
            start_time=start,
            end_time=end,
            status=EventStatus(d.get("status", "unconfirmed")),
            summary=d.get("summary", ""),
            confidence=_safe_float(d.get("confidence"), 0.0),
        )


@dataclass
class Attribute:
    """A dynamic key-value attribute attached to a disaster event."""

    event_id: str
    key: str
    value: str
    attr_id: str = field(default_factory=lambda: _new_id("attr"))
    unit: Optional[str] = None
    category: AttrCategory = AttrCategory.OTHER
    data_type: DataType = DataType.STRING
    source: str = "llm_extraction"
    update_time: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if isinstance(self.category, str):
            self.category = AttrCategory(self.category)
        if isinstance(self.data_type, str):
            self.data_type = DataType(self.data_type)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        d["data_type"] = self.data_type.value
        d["update_time"] = self.update_time.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Attribute":
        update_time = d.get("update_time")
        if isinstance(update_time, str):
            update_time = datetime.fromisoformat(update_time)
        return cls(
            attr_id=d.get("attr_id", _new_id("attr")),
            event_id=d.get("event_id", ""),
            key=d.get("key", ""),
            value=str(d.get("value", "")),
            unit=d.get("unit"),
            category=AttrCategory(d.get("category", "other")),
            data_type=DataType(d.get("data_type", "string")),
            source=d.get("source", "llm_extraction"),
            update_time=update_time or datetime.now(),
        )


@dataclass
class Location:
    """A geographic location where an event occurred."""

    name: str
    latitude: float
    longitude: float
    loc_id: str = field(default_factory=lambda: _new_id("loc"))
    address: Optional[str] = None
    country: Optional[str] = None

    def __post_init__(self):
        self.latitude = _safe_float(self.latitude)
        self.longitude = _safe_float(self.longitude)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Location":
        return cls(
            loc_id=d.get("loc_id", _new_id("loc")),
            name=d.get("name", ""),
            latitude=_safe_float(d.get("latitude")),
            longitude=_safe_float(d.get("longitude")),
            address=d.get("address"),
            country=d.get("country"),
        )


@dataclass
class SourceDocument:
    """A source document that reports or provides evidence for an event/attribute."""

    title: str
    doc_id: str = field(default_factory=lambda: _new_id("doc"))
    url: Optional[str] = None
    source_type: str = "news"
    publish_time: Optional[datetime] = None
    content_snippet: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["publish_time"] = self.publish_time.isoformat() if self.publish_time else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SourceDocument":
        pub_time = d.get("publish_time")
        if isinstance(pub_time, str):
            pub_time = datetime.fromisoformat(pub_time)
        return cls(
            doc_id=d.get("doc_id", _new_id("doc")),
            title=d.get("title", ""),
            url=d.get("url"),
            source_type=d.get("source_type", "news"),
            publish_time=pub_time,
            content_snippet=d.get("content_snippet", ""),
        )
