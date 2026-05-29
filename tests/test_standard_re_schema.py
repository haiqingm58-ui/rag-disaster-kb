"""Tests for RE relation schema."""

import pytest

from src.graph.standard.re.relation_schema import (
    RELATION_TYPES, relation_to_id, id_to_relation,
    ExtractedRelation,
)


class TestRelationTypes:
    def test_has_required_types(self):
        for rel in ["HAS_CHAPTER", "HAS_CLAUSE", "HAS_SUB_CLAUSE",
                     "DEFINES", "HAS_REQUIREMENT", "HAS_INDICATOR",
                     "USES_METHOD", "APPLIES_TO", "ISSUED_BY",
                     "REFERENCES", "RELATED_TO_DISASTER"]:
            assert rel in RELATION_TYPES, f"Missing relation: {rel}"

    def test_count(self):
        assert len(RELATION_TYPES) == 11


class TestMappings:
    def test_bijective(self):
        assert len(relation_to_id) == len(id_to_relation)
        for rel, rid in relation_to_id.items():
            assert id_to_relation[rid] == rel

    def test_has_chapter_is_zero(self):
        assert relation_to_id["HAS_CHAPTER"] == 0


class TestExtractedRelation:
    def test_dataclass(self):
        rel = ExtractedRelation(
            subject="3.1.2", predicate="HAS_REQUIREMENT",
            object="应采用定量方法", confidence=0.85,
            subject_type="Clause", object_type="Requirement",
        )
        assert rel.subject == "3.1.2"
        assert rel.predicate == "HAS_REQUIREMENT"

    def test_to_dict(self):
        rel = ExtractedRelation(subject="s", predicate="p", object="o")
        d = rel.to_dict()
        assert d["subject"] == "s"
        assert d["predicate"] == "p"
        assert d["confidence"] == 1.0
