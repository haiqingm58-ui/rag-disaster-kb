"""Relation Extraction for industry standard knowledge graph."""

from .relation_schema import (
    RELATION_TYPES, relation_to_id, id_to_relation,
    ExtractedRelation,
)
from .predictor import RelationPredictor

__all__ = [
    "RELATION_TYPES", "relation_to_id", "id_to_relation",
    "ExtractedRelation", "RelationPredictor",
]
