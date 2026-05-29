"""Tests for NER label schema: BIO labels, mappings, entity conversion."""

import pytest

from src.graph.standard.ner.label_schema import (
    ENTITY_TYPES, BIO_LABELS, label_to_id, id_to_label,
    ExtractedEntity, bio_tags_to_entities,
)


class TestEntityTypes:
    def test_has_required_types(self):
        for etype in ["STANDARD", "TERM", "REQUIREMENT", "INDICATOR",
                       "METHOD", "OBJECT", "ORGANIZATION", "LOCATION",
                       "DISASTER_TYPE", "CHAPTER", "CLAUSE"]:
            assert etype in ENTITY_TYPES, f"Missing entity type: {etype}"

    def test_count(self):
        assert len(ENTITY_TYPES) == 11


class TestBIOLabels:
    def test_starts_with_o(self):
        assert BIO_LABELS[0] == "O"

    def test_bio_pattern(self):
        for etype in ENTITY_TYPES:
            assert f"B-{etype}" in BIO_LABELS
            assert f"I-{etype}" in BIO_LABELS

    def test_count(self):
        # 1 O + 11 * 2 B/I tags = 23
        assert len(BIO_LABELS) == 23


class TestMappings:
    def test_label_to_id_is_bijective(self):
        assert len(label_to_id) == len(id_to_label)
        for label, lid in label_to_id.items():
            assert id_to_label[lid] == label

    def test_o_is_zero(self):
        assert label_to_id["O"] == 0

    def test_first_b_tag_is_one(self):
        assert label_to_id["B-STANDARD"] == 1


class TestExtractedEntity:
    def test_dataclass(self):
        e = ExtractedEntity(text="滑坡", entity_type="DISASTER_TYPE",
                            start_char=0, end_char=2, confidence=0.9)
        assert e.text == "滑坡"
        assert e.entity_type == "DISASTER_TYPE"

    def test_to_dict(self):
        e = ExtractedEntity(text="test", entity_type="TERM", start_char=0, end_char=4)
        d = e.to_dict()
        assert d["text"] == "test"
        assert d["entity_type"] == "TERM"
        assert d["confidence"] == 1.0


class TestBioTagsToEntities:
    def test_single_entity(self):
        tokens = ["滑", "坡"]
        tags = ["B-DISASTER_TYPE", "I-DISASTER_TYPE"]
        entities = bio_tags_to_entities(tokens, tags)
        assert len(entities) == 1
        assert entities[0].text == "滑坡"
        assert entities[0].entity_type == "DISASTER_TYPE"

    def test_two_entities(self):
        tokens = ["滑", "坡", "应", "评", "估"]
        tags = ["B-DISASTER_TYPE", "I-DISASTER_TYPE", "B-REQUIREMENT", "I-REQUIREMENT", "I-REQUIREMENT"]
        entities = bio_tags_to_entities(tokens, tags)
        assert len(entities) == 2
        assert {e.entity_type for e in entities} == {"DISASTER_TYPE", "REQUIREMENT"}

    def test_all_o(self):
        tokens = ["。", "。"]
        tags = ["O", "O"]
        entities = bio_tags_to_entities(tokens, tags)
        assert entities == []

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            bio_tags_to_entities(["a"], ["O", "O"])
