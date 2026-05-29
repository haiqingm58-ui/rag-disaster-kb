"""Knowledge graph module for disaster events and industry standards."""

# Disaster event submodule (backward-compatible re-exports)
from .disaster.models import (
    DisasterEvent,
    Attribute,
    Location,
    SourceDocument,
    DisasterType,
    EventStatus,
    AttrCategory,
    DataType,
)

# Standard submodule
from .standard.models import (
    StandardDocument,
    Chapter,
    Clause,
    Term,
    Requirement,
    Indicator,
    Method,
    StandardObject,
    Obligation,
    RequirementType,
    StandardStatus,
    ObjectType,
)

__all__ = [
    # Disaster
    "DisasterEvent", "Attribute", "Location", "SourceDocument",
    "DisasterType", "EventStatus", "AttrCategory", "DataType",
    # Standard
    "StandardDocument", "Chapter", "Clause", "Term",
    "Requirement", "Indicator", "Method", "StandardObject",
    "Obligation", "RequirementType", "StandardStatus", "ObjectType",
]
