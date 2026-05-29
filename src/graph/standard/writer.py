"""Write industry standard knowledge graph to Neo4j.

Handles writing all 8 node types and 11 relationship types using MERGE
for idempotent writes.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..common.neo4j_client import get_session, neo4j_config
from .models import (
    StandardDocument, Chapter, Clause, Term, Requirement,
    Indicator, Method, StandardObject,
)
from . import queries as q

logger = logging.getLogger(__name__)


# ── Schema init ──────────────────────────────────────────────────────────────

def init_schema(database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    logger.info("Initializing standard schema on '%s'", db)
    with get_session(db) as sess:
        for stmt in q.CREATE_CONSTRAINTS:
            sess.run(stmt)
        for stmt in q.CREATE_INDEXES:
            sess.run(stmt)
    logger.info("Standard schema initialized (%d constraints, %d indexes)",
                len(q.CREATE_CONSTRAINTS), len(q.CREATE_INDEXES))


# ── Node writes ──────────────────────────────────────────────────────────────

def merge_standard(doc: StandardDocument, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_STANDARD, q.standard_params(doc))
    logger.debug("Merged standard %s", doc.standard_id)


def merge_chapter(ch: Chapter, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_CHAPTER, q.chapter_params(ch))
    logger.debug("Merged chapter %s", ch.chapter_id)


def merge_clause(cl: Clause, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_CLAUSE, q.clause_params(cl))
    logger.debug("Merged clause %s", cl.clause_id)


def merge_term(term: Term, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_TERM, q.term_params(term))
    logger.debug("Merged term %s", term.term_id)


def merge_requirement(req: Requirement, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_REQUIREMENT, q.requirement_params(req))
    logger.debug("Merged requirement %s", req.requirement_id)


def merge_indicator(ind: Indicator, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_INDICATOR, q.indicator_params(ind))
    logger.debug("Merged indicator %s", ind.indicator_id)


def merge_method(meth: Method, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_METHOD, q.method_params(meth))
    logger.debug("Merged method %s", meth.method_id)


def merge_standard_object(obj: StandardObject, database: Optional[str] = None) -> None:
    db = database or neo4j_config()[3]
    with get_session(db) as sess:
        sess.run(q.MERGE_STANDARD_OBJECT, q.standard_object_params(obj))
    logger.debug("Merged object %s", obj.object_id)


# ── Relationship writes ──────────────────────────────────────────────────────

def _merge_rel(
    label_a: str, id_field_a: str, id_value_a: str,
    label_b: str, id_field_b: str, id_value_b: str,
    rel_type: str,
    database: Optional[str] = None,
) -> None:
    """Create a MERGE relationship between two nodes.

    Args:
        label_a: Node label for side A (e.g. "StandardDocument").
        id_field_a: Property name to match side A (e.g. "standard_id").
        id_value_a: Actual value for side A's property (e.g. "std-xxx").
        label_b: Node label for side B.
        id_field_b: Property name to match side B.
        id_value_b: Actual value for side B's property.
        rel_type: Relationship type (e.g. "HAS_CHAPTER").
        database: Neo4j database name.
    """
    db = database or neo4j_config()[3]
    stmt = (
        f"MATCH (a:{label_a} {{{id_field_a}: $a_id}}) "
        f"MATCH (b:{label_b} {{{id_field_b}: $b_id}}) "
        f"MERGE (a)-[:{rel_type}]->(b)"
    )
    with get_session(db) as sess:
        sess.run(stmt, {"a_id": id_value_a, "b_id": id_value_b})


def link_standard_to_chapter(std_id: str, ch_id: str, db=None):
    _merge_rel("StandardDocument", "standard_id", std_id,
               "Chapter", "chapter_id", ch_id, "HAS_CHAPTER", db)

def link_standard_to_clause(std_id: str, cl_id: str, db=None):
    _merge_rel("StandardDocument", "standard_id", std_id,
               "Clause", "clause_id", cl_id, "HAS_CLAUSE", db)

def link_chapter_to_clause(ch_id: str, cl_id: str, db=None):
    _merge_rel("Chapter", "chapter_id", ch_id,
               "Clause", "clause_id", cl_id, "HAS_CLAUSE", db)

def link_clause_to_sub_clause(parent_id: str, child_id: str, db=None):
    _merge_rel("Clause", "clause_id", parent_id,
               "Clause", "clause_id", child_id, "HAS_SUB_CLAUSE", db)

def link_standard_defines_term(std_id: str, term_id: str, db=None):
    _merge_rel("StandardDocument", "standard_id", std_id,
               "Term", "term_id", term_id, "DEFINES", db)

def link_clause_defines_term(cl_id: str, term_id: str, db=None):
    _merge_rel("Clause", "clause_id", cl_id,
               "Term", "term_id", term_id, "DEFINES", db)

def link_requirement_to_clause(req_id: str, cl_id: str, db=None):
    """Note: direction is Clause -> Requirement (HAS_REQUIREMENT)."""
    _merge_rel("Clause", "clause_id", cl_id,
               "Requirement", "requirement_id", req_id, "HAS_REQUIREMENT", db)

def link_indicator_to_clause(ind_id: str, cl_id: str, db=None):
    _merge_rel("Clause", "clause_id", cl_id,
               "Indicator", "indicator_id", ind_id, "HAS_INDICATOR", db)

def link_method_to_clause(meth_id: str, cl_id: str, db=None):
    _merge_rel("Clause", "clause_id", cl_id,
               "Method", "method_id", meth_id, "USES_METHOD", db)

def link_clause_applies_to(cl_id: str, obj_id: str, db=None):
    _merge_rel("Clause", "clause_id", cl_id,
               "StandardObject", "object_id", obj_id, "APPLIES_TO", db)

def link_standard_reference(std_id: str, ref_std_id: str, db=None):
    _merge_rel("StandardDocument", "standard_id", std_id,
               "StandardDocument", "standard_id", ref_std_id, "REFERENCES", db)


# ── Compound write ───────────────────────────────────────────────────────────

def write_standard_graph(
    doc: StandardDocument,
    chapters: list[Chapter],
    clauses: list[Clause],
    terms: Optional[list[Term]] = None,
    requirements: Optional[list[Requirement]] = None,
    indicators: Optional[list[Indicator]] = None,
    methods: Optional[list[Method]] = None,
    objects: Optional[list[StandardObject]] = None,
    database: Optional[str] = None,
) -> dict:
    """Write a complete standard with all extracted knowledge to Neo4j.

    All writes use MERGE — safe to call multiple times.
    """
    db = database or neo4j_config()[3]
    stats = {
        "standard": 1, "chapters": 0, "clauses": 0,
        "terms": 0, "requirements": 0, "indicators": 0,
        "methods": 0, "objects": 0, "relationships": 0,
    }

    merge_standard(doc, db)

    # Chapter -> StandardDocument relationship
    for ch in chapters:
        merge_chapter(ch, db)
        link_standard_to_chapter(doc.standard_id, ch.chapter_id, db)
        stats["chapters"] += 1
        stats["relationships"] += 1

    # Clauses
    clause_id_to_parent: dict[str, Optional[str]] = {}
    prev_at_level: dict[int, str] = {}

    for cl in clauses:
        merge_clause(cl, db)

        # Link to standard
        link_standard_to_clause(doc.standard_id, cl.clause_id, db)
        stats["relationships"] += 1

        # Link to chapter
        if cl.chapter_id:
            link_chapter_to_clause(cl.chapter_id, cl.clause_id, db)
            stats["relationships"] += 1

        # Link parent-child clauses (based on numbering hierarchy)
        if cl.level > 1:
            parent_level = cl.level - 1
            if parent_level in prev_at_level:
                link_clause_to_sub_clause(prev_at_level[parent_level], cl.clause_id, db)
                stats["relationships"] += 1

        prev_at_level[cl.level] = cl.clause_id
        # Clear deeper levels
        for l in list(prev_at_level.keys()):
            if l > cl.level:
                del prev_at_level[l]

        stats["clauses"] += 1

    # Terms
    for term in (terms or []):
        merge_term(term, db)
        link_standard_defines_term(doc.standard_id, term.term_id, db)
        if term.source_clause_id:
            link_clause_defines_term(term.source_clause_id, term.term_id, db)
        stats["terms"] += 1
        stats["relationships"] += 1

    # Requirements
    for req in (requirements or []):
        merge_requirement(req, db)
        link_requirement_to_clause(req.requirement_id, req.clause_id, db)
        stats["requirements"] += 1
        stats["relationships"] += 1

    # Indicators
    for ind in (indicators or []):
        merge_indicator(ind, db)
        if ind.source_clause_id:
            link_indicator_to_clause(ind.indicator_id, ind.source_clause_id, db)
        stats["indicators"] += 1
        stats["relationships"] += 1

    # Methods
    for meth in (methods or []):
        merge_method(meth, db)
        if meth.source_clause_id:
            link_method_to_clause(meth.method_id, meth.source_clause_id, db)
        stats["methods"] += 1
        stats["relationships"] += 1

    # Objects
    for obj in (objects or []):
        merge_standard_object(obj, db)
        stats["objects"] += 1

    logger.info(
        "Wrote standard graph: std=%s, ch=%d, cl=%d, terms=%d, reqs=%d, "
        "inds=%d, meths=%d, objs=%d, rels=%d",
        doc.code, stats["chapters"], stats["clauses"], stats["terms"],
        stats["requirements"], stats["indicators"], stats["methods"],
        stats["objects"], stats["relationships"],
    )
    return stats
