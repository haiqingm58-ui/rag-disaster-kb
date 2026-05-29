"""Write disaster event extraction results to Neo4j.

Uses shared neo4j_client from common module for connection management.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..common.neo4j_client import get_session, neo4j_config, check_connection, close_driver
from .models import DisasterEvent, Attribute, Location, SourceDocument
from . import queries as q

logger = logging.getLogger(__name__)


# ── Schema initialization ─────────────────────────────────────────────────────

def init_schema(database: Optional[str] = None) -> None:
    """Create all constraints and indexes. Idempotent."""
    db = database or neo4j_config()[3]
    logger.info("Initializing disaster schema on '%s'", db)
    with get_session(db) as sess:
        for stmt in q.CREATE_CONSTRAINTS:
            sess.run(stmt)
        for stmt in q.CREATE_INDEXES:
            sess.run(stmt)
    logger.info("Disaster schema initialized (%d constraints, %d indexes)",
                len(q.CREATE_CONSTRAINTS), len(q.CREATE_INDEXES))


# ── Node writes ───────────────────────────────────────────────────────────────

def merge_event(event: DisasterEvent, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_EVENT, q.event_params(event))
    logger.debug("Merged event %s", event.event_id)


def merge_attribute(attr: Attribute, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_ATTRIBUTE, q.attribute_params(attr))
    logger.debug("Merged attribute %s", attr.attr_id)


def merge_attribute_dedup(attr: Attribute, database: Optional[str] = None) -> Optional[str]:
    """Insert or update an Attribute, deduplicating by (event_id, key).

    Returns the attr_id of the stored attribute.
    """
    db = database or neo4j_config()[3]
    params = q.attribute_params(attr)
    with get_session(db) as sess:
        result = sess.run(q.MERGE_ATTRIBUTE_DEDUP_SIMPLE, params)
        record = result.single()
        if record and record.get("a"):
            return record["a"].get("attr_id")
        result2 = sess.run(q.MERGE_ATTRIBUTE_DEDUP_CREATE, params)
        record2 = result2.single()
        if record2 and record2.get("a"):
            return record2["a"].get("attr_id")
    merge_attribute(attr, db)
    return attr.attr_id


def merge_location(loc: Location, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_LOCATION, q.location_params(loc))
    logger.debug("Merged location %s", loc.loc_id)


def merge_source_document(doc: SourceDocument, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_SOURCE_DOC, q.source_doc_params(doc))
    logger.debug("Merged source document %s", doc.doc_id)


# ── Relationship writes ───────────────────────────────────────────────────────

def link_has_attribute(event_id: str, attr_id: str, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_HAS_ATTRIBUTE, {"event_id": event_id, "attr_id": attr_id})


def link_occurred_at(event_id: str, loc_id: str, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_OCCURRED_AT, {"event_id": event_id, "loc_id": loc_id})


def link_reported_by(event_id: str, doc_id: str, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_REPORTED_BY, {"event_id": event_id, "doc_id": doc_id})


def link_evidenced_by(attr_id: str, doc_id: str, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_EVIDENCED_BY, {"attr_id": attr_id, "doc_id": doc_id})


# ── Compound operations ───────────────────────────────────────────────────────

def write_extraction_result(
    event: DisasterEvent,
    attributes: list[Attribute],
    location: Optional[Location] = None,
    source_document: Optional[SourceDocument] = None,
    database: Optional[str] = None,
) -> dict:
    """Write complete extraction result to Neo4j. Attributes deduplicated by (event_id, key)."""
    db = database or neo4j_config()[3]
    stats = {"event": 1, "attributes": 0, "location": 0, "source_document": 0}

    merge_event(event, db)

    for attr in attributes:
        merge_attribute_dedup(attr, db)
        if source_document:
            link_evidenced_by(attr.attr_id, source_document.doc_id, db)
        stats["attributes"] += 1

    if location:
        merge_location(location, db)
        link_occurred_at(event.event_id, location.loc_id, db)
        stats["location"] = 1

    if source_document:
        merge_source_document(source_document, db)
        link_reported_by(event.event_id, source_document.doc_id, db)
        stats["source_document"] = 1

    logger.info("Wrote extraction: event=%s, attrs=%d, loc=%d, doc=%d",
                event.event_id, stats["attributes"], stats["location"], stats["source_document"])
    return stats


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_event_context(event_id: str, database: Optional[str] = None) -> Optional[dict]:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        record = sess.run(q.QUERY_EVENT_WITH_CONTEXT, {"event_id": event_id}).single()
        if not record:
            return None
        return {
            "event": dict(record["e"]),
            "attributes": [dict(a) for a in (record.get("attributes") or [])],
            "location": dict(record["l"]) if record.get("l") else None,
            "documents": [dict(d) for d in (record.get("documents") or [])],
        }


def query_recent_events(since: str, limit: int = 20, database: Optional[str] = None) -> list[dict]:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        records = list(sess.run(q.QUERY_RECENT_EVENTS, {"since": since, "limit": limit}))
    return [{"event": dict(r["e"]), "location": dict(r["l"]) if r.get("l") else None} for r in records]
