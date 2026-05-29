"""Tests for schema consistency: JSON schema, Cypher query correctness, and cross-file field name alignment."""

import json
from pathlib import Path

import pytest

from src.graph import models as m
from src.graph import neo4j_queries as q
from src.graph.models import (
    DisasterType, AttrCategory, EventStatus, DataType,
)


SCHEMA_PATH = Path(__file__).parent.parent / "src" / "graph" / "schema.json"


# ── Schema JSON ───────────────────────────────────────────────────────────────

class TestSchemaJSON:
    def test_file_exists_and_valid_json(self):
        assert SCHEMA_PATH.exists(), f"schema.json not found at {SCHEMA_PATH}"
        with open(SCHEMA_PATH) as f:
            data = json.load(f)
        assert "entities" in data
        assert "relationships" in data

    def test_all_entities_present(self):
        with open(SCHEMA_PATH) as f:
            data = json.load(f)
        entities = data["entities"]
        assert "DisasterEvent" in entities
        assert "Attribute" in entities
        assert "Location" in entities
        assert "SourceDocument" in entities

    def test_no_organization_in_entities(self):
        with open(SCHEMA_PATH) as f:
            data = json.load(f)
        assert "Organization" not in data["entities"]

    def test_no_organization_in_relationships(self):
        with open(SCHEMA_PATH) as f:
            data = json.load(f)
        for rel in data["relationships"].values():
            assert "Organization" not in rel["from"]
            assert "Organization" not in rel["to"]

    def test_all_relationships_present(self):
        with open(SCHEMA_PATH) as f:
            data = json.load(f)
        rels = data["relationships"]
        assert "HAS_ATTRIBUTE" in rels
        assert "OCCURRED_AT" in rels
        assert "REPORTED_BY" in rels
        assert "EVIDENCED_BY" in rels


# ── Schema entity field names vs. models.py ───────────────────────────────────

class TestFieldNameConsistency:
    """Ensure schema.json entity examples use the same field names as models.py."""

    @staticmethod
    def _dataclass_fields(cls):
        return {f.name for f in cls.__dataclass_fields__.values()}

    def test_disaster_event_fields_match(self):
        with open(SCHEMA_PATH) as f:
            schema_fields = set(json.load(f)["entities"]["DisasterEvent"]["example"].keys())
        model_fields = self._dataclass_fields(m.DisasterEvent)
        assert schema_fields == model_fields, f"Mismatch: schema={schema_fields - model_fields}, model={model_fields - schema_fields}"

    def test_attribute_fields_match(self):
        with open(SCHEMA_PATH) as f:
            schema_fields = set(json.load(f)["entities"]["Attribute"]["example"].keys())
        model_fields = self._dataclass_fields(m.Attribute)
        assert schema_fields == model_fields, f"Mismatch: schema={schema_fields - model_fields}, model={model_fields - schema_fields}"

    def test_location_fields_match(self):
        with open(SCHEMA_PATH) as f:
            schema_fields = set(json.load(f)["entities"]["Location"]["example"].keys())
        model_fields = self._dataclass_fields(m.Location)
        assert schema_fields == model_fields, f"Mismatch: schema={schema_fields - model_fields}, model={model_fields - schema_fields}"

    def test_source_document_fields_match(self):
        with open(SCHEMA_PATH) as f:
            schema_fields = set(json.load(f)["entities"]["SourceDocument"]["example"].keys())
        model_fields = self._dataclass_fields(m.SourceDocument)
        assert schema_fields == model_fields, f"Mismatch: schema={schema_fields - model_fields}, model={model_fields - schema_fields}"


# ── Parameter helper consistency ──────────────────────────────────────────────

class TestParamHelpers:
    """Ensure q.event_params, q.attribute_params etc. include all required fields."""

    def test_event_params_keys(self):
        evt = m.DisasterEvent(name="test", disaster_type="earthquake")
        params = q.event_params(evt)
        assert set(params.keys()) == {
            "event_id", "name", "disaster_type", "start_time",
            "end_time", "status", "summary", "confidence",
        }

    def test_attribute_params_keys(self):
        attr = m.Attribute(event_id="evt-1", key="magnitude", value="5.2")
        params = q.attribute_params(attr)
        assert set(params.keys()) == {
            "attr_id", "event_id", "key", "value", "unit",
            "category", "data_type", "source", "update_time",
        }

    def test_location_params_keys(self):
        loc = m.Location(name="test", latitude=1.0, longitude=2.0)
        params = q.location_params(loc)
        assert set(params.keys()) == {
            "loc_id", "name", "latitude", "longitude", "address", "country",
        }

    def test_source_doc_params_keys(self):
        doc = m.SourceDocument(title="test")
        params = q.source_doc_params(doc)
        assert set(params.keys()) == {
            "doc_id", "title", "url", "source_type", "publish_time", "content_snippet",
        }

    def test_datetime_params_are_python_objects(self):
        from datetime import datetime
        evt = m.DisasterEvent(
            name="test", disaster_type="earthquake",
            start_time=datetime(2026, 5, 20, 8, 30),
        )
        params = q.event_params(evt)
        assert isinstance(params["start_time"], datetime)
        assert params["end_time"] is None


# ── Cypher query consistency ──────────────────────────────────────────────────

class TestCypherQueries:
    """Lightweight checks on Cypher query strings."""

    def test_merge_event_matches_event_params(self):
        params = {"event_id", "name", "disaster_type", "start_time",
                   "end_time", "status", "summary", "confidence"}
        for p in params:
            assert f"${p}" in q.MERGE_EVENT, f"Missing ${p} in MERGE_EVENT"

    def test_merge_attribute_matches_attribute_params(self):
        params = {"attr_id", "event_id", "key", "value", "unit",
                   "category", "data_type", "source", "update_time"}
        for p in params:
            assert f"${p}" in q.MERGE_ATTRIBUTE, f"Missing ${p} in MERGE_ATTRIBUTE"

    def test_merge_location_matches_location_params(self):
        params = {"loc_id", "name", "latitude", "longitude", "address", "country"}
        for p in params:
            assert f"${p}" in q.MERGE_LOCATION, f"Missing ${p} in MERGE_LOCATION"

    def test_merge_source_doc_matches_source_doc_params(self):
        params = {"doc_id", "title", "url", "source_type", "publish_time", "content_snippet"}
        for p in params:
            assert f"${p}" in q.MERGE_SOURCE_DOC, f"Missing ${p} in MERGE_SOURCE_DOC"

    def test_constraints_use_correct_id_fields(self):
        constraints_text = " ".join(q.CREATE_CONSTRAINTS)
        assert "e.event_id" in constraints_text
        assert "a.attr_id" in constraints_text
        assert "l.loc_id" in constraints_text
        assert "d.doc_id" in constraints_text

    def test_has_attribute_relationship_uses_correct_ids(self):
        assert "event_id" in q.MERGE_HAS_ATTRIBUTE
        assert "attr_id" in q.MERGE_HAS_ATTRIBUTE

    def test_occurred_at_relationship_uses_correct_ids(self):
        assert "event_id" in q.MERGE_OCCURRED_AT
        assert "loc_id" in q.MERGE_OCCURRED_AT

    def test_reported_by_relationship_uses_correct_ids(self):
        assert "event_id" in q.MERGE_REPORTED_BY
        assert "doc_id" in q.MERGE_REPORTED_BY

    def test_evidenced_by_relationship_uses_correct_ids(self):
        assert "attr_id" in q.MERGE_EVIDENCED_BY
        assert "doc_id" in q.MERGE_EVIDENCED_BY

    def test_dedup_query_uses_event_id_and_key(self):
        assert "$event_id" in q.MERGE_ATTRIBUTE_DEDUP_SIMPLE
        assert "$key" in q.MERGE_ATTRIBUTE_DEDUP_SIMPLE
        assert "$event_id" in q.MERGE_ATTRIBUTE_DEDUP_CREATE
        assert "$key" in q.MERGE_ATTRIBUTE_DEDUP_CREATE


# ── Enums in schema ───────────────────────────────────────────────────────────

class TestEnumValues:
    def test_disaster_type_count(self):
        assert len(DisasterType) == 10  # 9 types + other

    def test_attr_category_count(self):
        assert len(AttrCategory) == 8  # 7 categories + other

    def test_event_status_count(self):
        assert len(EventStatus) == 3

    def test_data_type_count(self):
        assert len(DataType) == 4
