"""Industry standard knowledge graph data model.

Entities:
  StandardDocument -- a published industry standard
  Chapter          -- a top-level or nested chapter/section
  Clause           -- a numbered clause/paragraph
  Term             -- a defined term
  Requirement      -- a normative requirement (shall/should/may)
  Indicator        -- a quantitative indicator/parameter
  Method           -- a methodology or procedure
  StandardObject   -- an entity the standard applies to
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum
from typing import Optional

from ..common.utils import new_id, safe_float, dt_iso, parse_dt


# ── Enums ────────────────────────────────────────────────────────────────────

class StandardStatus(str, Enum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    DRAFT = "draft"
    ABOLISHED = "abolished"


class Obligation(str, Enum):
    SHALL = "shall"
    SHOULD = "should"
    MAY = "may"


class RequirementType(str, Enum):
    TECHNICAL = "technical"
    MANAGEMENT = "management"
    SAFETY = "safety"
    QUALITY = "quality"
    ENVIRONMENTAL = "environmental"
    OTHER = "other"


class ObjectType(str, Enum):
    FACILITY = "facility"
    EQUIPMENT = "equipment"
    MATERIAL = "material"
    PROCESS = "process"
    PERSONNEL = "personnel"
    DATA = "data"
    OTHER = "other"


# ── Entities ─────────────────────────────────────────────────────────────────

@dataclass
class StandardDocument:
    """A published industry standard document."""

    code: str
    title: str
    industry: str
    standard_id: str = field(default_factory=lambda: new_id("std"))
    status: StandardStatus = StandardStatus.CURRENT
    publish_date: Optional[date] = None
    effective_date: Optional[date] = None
    issuing_body: str = ""
    source_file: str = ""
    summary: str = ""

    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = StandardStatus(self.status)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["publish_date"] = self.publish_date.isoformat() if self.publish_date else None
        d["effective_date"] = self.effective_date.isoformat() if self.effective_date else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "StandardDocument":
        return cls(
            standard_id=d.get("standard_id", new_id("std")),
            code=d.get("code", ""),
            title=d.get("title", ""),
            industry=d.get("industry", ""),
            status=StandardStatus(d.get("status", "current")),
            publish_date=_parse_date(d.get("publish_date")),
            effective_date=_parse_date(d.get("effective_date")),
            issuing_body=d.get("issuing_body", ""),
            source_file=d.get("source_file", ""),
            summary=d.get("summary", ""),
        )


@dataclass
class Chapter:
    """A chapter or section within a standard."""

    standard_id: str
    chapter_number: str
    title: str
    chapter_id: str = field(default_factory=lambda: new_id("ch"))
    level: int = 1
    order_index: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Chapter":
        return cls(
            chapter_id=d.get("chapter_id", new_id("ch")),
            standard_id=d.get("standard_id", ""),
            chapter_number=d.get("chapter_number", ""),
            title=d.get("title", ""),
            level=d.get("level", 1),
            order_index=d.get("order_index", 0),
        )


@dataclass
class Clause:
    """A numbered clause/paragraph within a standard."""

    standard_id: str
    clause_number: str
    content: str
    clause_id: str = field(default_factory=lambda: new_id("cl"))
    chapter_id: Optional[str] = None
    title: str = ""
    level: int = 1
    order_index: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Clause":
        return cls(
            clause_id=d.get("clause_id", new_id("cl")),
            standard_id=d.get("standard_id", ""),
            chapter_id=d.get("chapter_id"),
            clause_number=d.get("clause_number", ""),
            title=d.get("title", ""),
            content=d.get("content", ""),
            level=d.get("level", 1),
            order_index=d.get("order_index", 0),
        )


@dataclass
class Term:
    """A defined term in the standard."""

    name: str
    definition: str
    term_id: str = field(default_factory=lambda: new_id("term"))
    standard_id: str = ""
    source_clause_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Term":
        return cls(
            term_id=d.get("term_id", new_id("term")),
            name=d.get("name", ""),
            definition=d.get("definition", ""),
            source_clause_id=d.get("source_clause_id"),
        )


@dataclass
class Requirement:
    """A normative requirement extracted from a clause."""

    clause_id: str
    text: str
    obligation: Obligation = Obligation.SHALL
    requirement_id: str = field(default_factory=lambda: new_id("req"))
    standard_id: str = ""
    requirement_type: RequirementType = RequirementType.OTHER
    confidence: float = 0.0

    def __post_init__(self):
        if isinstance(self.obligation, str):
            self.obligation = Obligation(self.obligation)
        if isinstance(self.requirement_type, str):
            self.requirement_type = RequirementType(self.requirement_type)
        self.confidence = max(0.0, min(1.0, safe_float(self.confidence, 0.0)))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["obligation"] = self.obligation.value
        d["requirement_type"] = self.requirement_type.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Requirement":
        return cls(
            requirement_id=d.get("requirement_id", new_id("req")),
            clause_id=d.get("clause_id", ""),
            text=d.get("text", ""),
            obligation=Obligation(d.get("obligation", "shall")),
            requirement_type=RequirementType(d.get("requirement_type", "other")),
            confidence=safe_float(d.get("confidence"), 0.0),
        )


@dataclass
class Indicator:
    """A quantitative indicator/parameter from a clause."""

    name: str
    indicator_id: str = field(default_factory=lambda: new_id("ind"))
    standard_id: str = ""
    value: Optional[str] = None
    operator: str = ""
    unit: str = ""
    description: str = ""
    source_clause_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Indicator":
        return cls(
            indicator_id=d.get("indicator_id", new_id("ind")),
            name=d.get("name", ""),
            value=d.get("value"),
            operator=d.get("operator", ""),
            unit=d.get("unit", ""),
            description=d.get("description", ""),
            source_clause_id=d.get("source_clause_id"),
        )


@dataclass
class Method:
    """A methodology or procedure referenced in a clause."""

    name: str
    method_id: str = field(default_factory=lambda: new_id("meth"))
    standard_id: str = ""
    description: str = ""
    source_clause_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Method":
        return cls(
            method_id=d.get("method_id", new_id("meth")),
            name=d.get("name", ""),
            description=d.get("description", ""),
            source_clause_id=d.get("source_clause_id"),
        )


@dataclass
class StandardObject:
    """An entity that a standard applies to (facility, equipment, material, etc.)."""

    name: str
    object_type: ObjectType = ObjectType.OTHER
    object_id: str = field(default_factory=lambda: new_id("obj"))
    standard_id: str = ""
    description: str = ""

    def __post_init__(self):
        if isinstance(self.object_type, str):
            self.object_type = ObjectType(self.object_type)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["object_type"] = self.object_type.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "StandardObject":
        return cls(
            object_id=d.get("object_id", new_id("obj")),
            name=d.get("name", ""),
            object_type=ObjectType(d.get("object_type", "other")),
            description=d.get("description", ""),
        )


# ── Helper ───────────────────────────────────────────────────────────────────

def _parse_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None
