"""Neo4j Cypher statements for the disaster knowledge graph.

Provides DDL (constraints, indexes), DML (insert/merge nodes and relationships),
and query helpers for RAG retrieval use cases.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from .models import DisasterEvent, Attribute, Location, SourceDocument

logger = logging.getLogger(__name__)

# ── DDL: Constraints & Indexes ────────────────────────────────────────────────

CREATE_CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (e:DisasterEvent) REQUIRE e.event_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Attribute) REQUIRE a.attr_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (l:Location) REQUIRE l.loc_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (d:SourceDocument) REQUIRE d.doc_id IS UNIQUE;",
]

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (e:DisasterEvent) ON (e.disaster_type);",
    "CREATE INDEX IF NOT EXISTS FOR (e:DisasterEvent) ON (e.status);",
    "CREATE INDEX IF NOT EXISTS FOR (e:DisasterEvent) ON (e.start_time);",
    "CREATE INDEX IF NOT EXISTS FOR (a:Attribute) ON (a.event_id);",
    "CREATE INDEX IF NOT EXISTS FOR (a:Attribute) ON (a.key);",
    "CREATE INDEX IF NOT EXISTS FOR (a:Attribute) ON (a.category);",
    "CREATE INDEX IF NOT EXISTS FOR (l:Location) ON (l.country);",
]

# Composite index for attribute dedup on (event_id, key).
CREATE_INDEXES.append(
    "CREATE INDEX IF NOT EXISTS FOR (a:Attribute) ON (a.event_id, a.key);"
)

# ── DML: Merge nodes ──────────────────────────────────────────────────────────

MERGE_EVENT = """
MERGE (e:DisasterEvent {event_id: $event_id})
SET e.name = $name,
    e.disaster_type = $disaster_type,
    e.start_time = $start_time,
    e.end_time = $end_time,
    e.status = $status,
    e.summary = $summary,
    e.confidence = $confidence
RETURN e
"""

MERGE_ATTRIBUTE = """
MERGE (a:Attribute {attr_id: $attr_id})
SET a.event_id = $event_id,
    a.key = $key,
    a.value = $value,
    a.unit = $unit,
    a.category = $category,
    a.data_type = $data_type,
    a.source = $source,
    a.update_time = $update_time
RETURN a
"""


MERGE_ATTRIBUTE_DEDUP = """
// Dedup-safe merge: match on (event_id, key) to avoid creating duplicate attributes.
// If a matching attribute exists, update its value and update_time.
// If not, create a new one.
MATCH (e:DisasterEvent {event_id: $event_id})
CALL {
  WITH e
  OPTIONAL MATCH (e)-[:HAS_ATTRIBUTE]->(existing:Attribute {key: $key})
  RETURN existing
}
WITH e, existing
CALL apoc.do.when(
  existing IS NOT NULL,
  '
    SET existing.value = $value,
        existing.unit = $unit,
        existing.category = $category,
        existing.data_type = $data_type,
        existing.source = $source,
        existing.update_time = $update_time
    RETURN existing AS a
  ',
  '
    CREATE (a:Attribute {
      attr_id: $attr_id,
      event_id: $event_id,
      key: $key,
      value: $value,
      unit: $unit,
      category: $category,
      data_type: $data_type,
      source: $source,
      update_time: $update_time
    })
    MERGE (e)-[:HAS_ATTRIBUTE]->(a)
    RETURN a
  ',
  {e: e, existing: existing, attr_id: $attr_id, event_id: $event_id,
   key: $key, value: $value, unit: $unit, category: $category,
   data_type: $data_type, source: $source, update_time: $update_time}
)
YIELD value
RETURN value.a AS a
"""


MERGE_ATTRIBUTE_DEDUP_SIMPLE = """
// Simple dedup-safe merge without APOC dependency.
// First try to match an existing attribute by (event_id, key).
OPTIONAL MATCH (e:DisasterEvent {event_id: $event_id})-[:HAS_ATTRIBUTE]->(existing:Attribute {key: $key})
WITH e, existing
WHERE existing IS NOT NULL
SET existing.value = $value,
    existing.unit = $unit,
    existing.category = $category,
    existing.data_type = $data_type,
    existing.source = $source,
    existing.update_time = $update_time
RETURN existing AS a
"""

MERGE_ATTRIBUTE_DEDUP_CREATE = """
// Create a new attribute only if none exists for (event_id, key).
MATCH (e:DisasterEvent {event_id: $event_id})
WHERE NOT EXISTS((e)-[:HAS_ATTRIBUTE]->(:Attribute {key: $key}))
CREATE (a:Attribute {
  attr_id: $attr_id,
  event_id: $event_id,
  key: $key,
  value: $value,
  unit: $unit,
  category: $category,
  data_type: $data_type,
  source: $source,
  update_time: $update_time
})
MERGE (e)-[:HAS_ATTRIBUTE]->(a)
RETURN a
"""


MERGE_LOCATION = """
MERGE (l:Location {loc_id: $loc_id})
SET l.name = $name,
    l.latitude = $latitude,
    l.longitude = $longitude,
    l.address = $address,
    l.country = $country
RETURN l
"""

MERGE_SOURCE_DOC = """
MERGE (d:SourceDocument {doc_id: $doc_id})
SET d.title = $title,
    d.url = $url,
    d.source_type = $source_type,
    d.publish_time = $publish_time,
    d.content_snippet = $content_snippet
RETURN d
"""

# ── DML: Merge relationships ──────────────────────────────────────────────────

MERGE_HAS_ATTRIBUTE = """
MATCH (e:DisasterEvent {event_id: $event_id})
MATCH (a:Attribute {attr_id: $attr_id})
MERGE (e)-[r:HAS_ATTRIBUTE]->(a)
RETURN r
"""

MERGE_OCCURRED_AT = """
MATCH (e:DisasterEvent {event_id: $event_id})
MATCH (l:Location {loc_id: $loc_id})
MERGE (e)-[r:OCCURRED_AT]->(l)
RETURN r
"""

MERGE_REPORTED_BY = """
MATCH (e:DisasterEvent {event_id: $event_id})
MATCH (d:SourceDocument {doc_id: $doc_id})
MERGE (e)-[r:REPORTED_BY]->(d)
RETURN r
"""

MERGE_EVIDENCED_BY = """
MATCH (a:Attribute {attr_id: $attr_id})
MATCH (d:SourceDocument {doc_id: $doc_id})
MERGE (a)-[r:EVIDENCED_BY]->(d)
RETURN r
"""

# ── Query helpers ─────────────────────────────────────────────────────────────

QUERY_EVENT_WITH_CONTEXT = """
MATCH (e:DisasterEvent {event_id: $event_id})
OPTIONAL MATCH (e)-[:HAS_ATTRIBUTE]->(a:Attribute)
OPTIONAL MATCH (e)-[:OCCURRED_AT]->(l:Location)
OPTIONAL MATCH (e)-[:REPORTED_BY]->(d:SourceDocument)
RETURN e, collect(DISTINCT a) AS attributes, l, collect(DISTINCT d) AS documents
"""

QUERY_EVENTS_BY_TYPE = """
MATCH (e:DisasterEvent)
WHERE e.disaster_type = $disaster_type
OPTIONAL MATCH (e)-[:OCCURRED_AT]->(l:Location)
RETURN e, l
ORDER BY e.start_time DESC
LIMIT $limit
"""

QUERY_RECENT_EVENTS = """
MATCH (e:DisasterEvent)
WHERE e.start_time >= $since
OPTIONAL MATCH (e)-[:OCCURRED_AT]->(l:Location)
RETURN e, l
ORDER BY e.start_time DESC
LIMIT $limit
"""

QUERY_ATTRIBUTES_BY_KEY = """
MATCH (a:Attribute)
WHERE a.key = $key
RETURN a
ORDER BY a.update_time DESC
LIMIT $limit
"""

QUERY_EVENT_BY_NAME_FUZZY = """
MATCH (e:DisasterEvent)
WHERE e.name CONTAINS $name_fragment
RETURN e
LIMIT $limit
"""

# ── Helper: build params from dataclasses ─────────────────────────────────────

def event_params(evt: DisasterEvent) -> dict:
    return {
        "event_id": evt.event_id,
        "name": evt.name,
        "disaster_type": evt.disaster_type.value,
        "start_time": evt.start_time,
        "end_time": evt.end_time,
        "status": evt.status.value,
        "summary": evt.summary,
        "confidence": evt.confidence,
    }


def attribute_params(attr: Attribute) -> dict:
    return {
        "attr_id": attr.attr_id,
        "event_id": attr.event_id,
        "key": attr.key,
        "value": attr.value,
        "unit": attr.unit,
        "category": attr.category.value,
        "data_type": attr.data_type.value,
        "source": attr.source,
        "update_time": attr.update_time,
    }


def location_params(loc: Location) -> dict:
    return {
        "loc_id": loc.loc_id,
        "name": loc.name,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "address": loc.address,
        "country": loc.country,
    }


def source_doc_params(doc: SourceDocument) -> dict:
    return {
        "doc_id": doc.doc_id,
        "title": doc.title,
        "url": doc.url,
        "source_type": doc.source_type,
        "publish_time": doc.publish_time,
        "content_snippet": doc.content_snippet,
    }
