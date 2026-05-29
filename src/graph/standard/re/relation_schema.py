"""Relation type schema for industry standard knowledge graph extraction."""

from __future__ import annotations

from dataclasses import dataclass

# ── Relation types ───────────────────────────────────────────────────────────

RELATION_TYPES = [
    "HAS_CHAPTER",          # StandardDocument → Chapter
    "HAS_CLAUSE",           # StandardDocument/Chapter → Clause
    "HAS_SUB_CLAUSE",       # Clause → Clause (parent-child hierarchy)
    "DEFINES",              # StandardDocument/Clause → Term
    "HAS_REQUIREMENT",      # Clause → Requirement
    "HAS_INDICATOR",        # Clause → Indicator
    "USES_METHOD",          # Clause → Method
    "APPLIES_TO",           # Clause → StandardObject
    "ISSUED_BY",            # StandardDocument → Organization
    "REFERENCES",           # StandardDocument → StandardDocument
    "RELATED_TO_DISASTER",  # Clause → DisasterType
]

# ── Mappings ─────────────────────────────────────────────────────────────────

relation_to_id: dict[str, int] = {rel: i for i, rel in enumerate(RELATION_TYPES)}
id_to_relation: dict[int, str] = {i: rel for rel, i in relation_to_id.items()}

# ── Output struct ────────────────────────────────────────────────────────────

@dataclass
class ExtractedRelation:
    """A single extracted relation triple (subject, predicate, object)."""
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    subject_type: str = ""
    object_type: str = ""

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "confidence": self.confidence,
            "subject_type": self.subject_type,
            "object_type": self.object_type,
        }
