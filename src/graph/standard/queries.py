"""Neo4j Cypher statements for industry standard knowledge graph."""

from __future__ import annotations

import logging

from .models import (
    StandardDocument, Chapter, Clause, Term, Requirement,
    Indicator, Method, StandardObject,
)

logger = logging.getLogger(__name__)

# ── DDL: Constraints ─────────────────────────────────────────────────────────

CREATE_CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (s:StandardDocument) REQUIRE s.standard_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Chapter) REQUIRE c.chapter_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Clause) REQUIRE c.clause_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Term) REQUIRE t.term_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Requirement) REQUIRE r.requirement_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Indicator) REQUIRE i.indicator_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Method) REQUIRE m.method_id IS UNIQUE;",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (o:StandardObject) REQUIRE o.object_id IS UNIQUE;",
]

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (s:StandardDocument) ON (s.code);",
    "CREATE INDEX IF NOT EXISTS FOR (s:StandardDocument) ON (s.industry);",
    "CREATE INDEX IF NOT EXISTS FOR (c:Clause) ON (c.standard_id);",
    "CREATE INDEX IF NOT EXISTS FOR (c:Clause) ON (c.chapter_id);",
    "CREATE INDEX IF NOT EXISTS FOR (r:Requirement) ON (r.obligation);",
    "CREATE INDEX IF NOT EXISTS FOR (o:StandardObject) ON (o.object_type);",
]

# ── DML: Merge nodes ─────────────────────────────────────────────────────────

MERGE_STANDARD = """
MERGE (s:StandardDocument {standard_id: $standard_id})
SET s.code = $code, s.title = $title, s.industry = $industry,
    s.status = $status, s.publish_date = $publish_date,
    s.effective_date = $effective_date, s.issuing_body = $issuing_body,
    s.source_file = $source_file, s.summary = $summary
RETURN s
"""

MERGE_CHAPTER = """
MERGE (c:Chapter {chapter_id: $chapter_id})
SET c.standard_id = $standard_id, c.chapter_number = $chapter_number,
    c.title = $title, c.level = $level, c.order_index = $order_index
RETURN c
"""

MERGE_CLAUSE = """
MERGE (c:Clause {clause_id: $clause_id})
SET c.standard_id = $standard_id, c.chapter_id = $chapter_id,
    c.clause_number = $clause_number, c.title = $title,
    c.content = $content, c.level = $level, c.order_index = $order_index
RETURN c
"""

MERGE_TERM = """
MERGE (t:Term {term_id: $term_id})
SET t.name = $name, t.definition = $definition,
    t.standard_id = $standard_id, t.source_clause_id = $source_clause_id
RETURN t
"""

MERGE_REQUIREMENT = """
MERGE (r:Requirement {requirement_id: $requirement_id})
SET r.clause_id = $clause_id, r.text = $text, r.obligation = $obligation,
    r.standard_id = $standard_id,
    r.requirement_type = $requirement_type, r.confidence = $confidence
RETURN r
"""

MERGE_INDICATOR = """
MERGE (i:Indicator {indicator_id: $indicator_id})
SET i.name = $name, i.value = $value, i.operator = $operator,
    i.unit = $unit, i.description = $description,
    i.standard_id = $standard_id, i.source_clause_id = $source_clause_id
RETURN i
"""

MERGE_METHOD = """
MERGE (m:Method {method_id: $method_id})
SET m.name = $name, m.description = $description,
    m.standard_id = $standard_id, m.source_clause_id = $source_clause_id
RETURN m
"""

MERGE_STANDARD_OBJECT = """
MERGE (o:StandardObject {object_id: $object_id})
SET o.name = $name, o.object_type = $object_type,
    o.standard_id = $standard_id, o.description = $description
RETURN o
"""

# ── DML: Merge relationships ─────────────────────────────────────────────────

MERGE_REL = """
MATCH (a {%s: $a_id})
MATCH (b {%s: $b_id})
MERGE (a)-[:%s]->(b)
"""

# ── Query helpers ────────────────────────────────────────────────────────────

QUERY_STANDARD_BY_CODE = """
MATCH (s:StandardDocument {code: $code})
RETURN s
"""

QUERY_CHAPTER_TREE = """
MATCH (s:StandardDocument {standard_id: $standard_id})
OPTIONAL MATCH (s)-[:HAS_CHAPTER]->(ch:Chapter)
OPTIONAL MATCH (ch)-[:HAS_CLAUSE]->(cl:Clause)
OPTIONAL MATCH (cl)-[:HAS_SUB_CLAUSE]->(sub:Clause)
RETURN s, collect(DISTINCT ch) AS chapters, collect(DISTINCT cl) AS clauses,
       collect(DISTINCT sub) AS sub_clauses
ORDER BY ch.order_index, cl.order_index
"""

QUERY_CLAUSES_BY_KEYWORD = """
MATCH (cl:Clause)
WHERE cl.content CONTAINS $keyword OR cl.title CONTAINS $keyword
OPTIONAL MATCH (cl)<-[:HAS_CLAUSE]-(ch:Chapter)
OPTIONAL MATCH (ch)<-[:HAS_CHAPTER]-(s:StandardDocument)
RETURN cl, ch, s
LIMIT $limit
"""

QUERY_REQUIREMENTS_BY_OBLIGATION = """
MATCH (r:Requirement)
WHERE r.obligation = $obligation
OPTIONAL MATCH (r)<-[:HAS_REQUIREMENT]-(cl:Clause)
OPTIONAL MATCH (cl)<-[:HAS_CLAUSE]-(s:StandardDocument)
RETURN r, cl, s
LIMIT $limit
"""

QUERY_INDICATORS = """
MATCH (i:Indicator)
OPTIONAL MATCH (i)<-[:HAS_INDICATOR]-(cl:Clause)
OPTIONAL MATCH (cl)<-[:HAS_CLAUSE]-(s:StandardDocument)
RETURN i, cl, s
LIMIT $limit
"""

QUERY_CLAUSES_BY_OBJECT = """
MATCH (o:StandardObject {name: $object_name})
MATCH (cl:Clause)-[:APPLIES_TO]->(o)
OPTIONAL MATCH (cl)<-[:HAS_CLAUSE]-(s:StandardDocument)
RETURN cl, s, o
LIMIT $limit
"""

QUERY_CLAUSE_SUBGRAPH = """
MATCH (cl:Clause {clause_id: $clause_id})
OPTIONAL MATCH (cl)-[:HAS_REQUIREMENT]->(r:Requirement)
OPTIONAL MATCH (cl)-[:HAS_INDICATOR]->(i:Indicator)
OPTIONAL MATCH (cl)-[:USES_METHOD]->(m:Method)
OPTIONAL MATCH (cl)-[:APPLIES_TO]->(o:StandardObject)
OPTIONAL MATCH (cl)-[:DEFINES]->(t:Term)
OPTIONAL MATCH (cl)-[:HAS_SUB_CLAUSE]->(sub:Clause)
OPTIONAL MATCH (cl)<-[:HAS_CLAUSE]-(ch:Chapter)
RETURN cl, collect(DISTINCT r) AS requirements, collect(DISTINCT i) AS indicators,
       collect(DISTINCT m) AS methods, collect(DISTINCT o) AS objects,
       collect(DISTINCT t) AS terms, collect(DISTINCT sub) AS sub_clauses,
       ch
"""

QUERY_STANDARD_FULL_GRAPH = """
MATCH (s:StandardDocument {standard_id: $standard_id})
OPTIONAL MATCH (s)-[:HAS_CHAPTER]->(ch:Chapter)
OPTIONAL MATCH (s)-[:HAS_CLAUSE]->(cl:Clause)
OPTIONAL MATCH (ch)-[:HAS_CLAUSE]->(cl2:Clause)
OPTIONAL MATCH (s)-[:DEFINES]->(t:Term)
OPTIONAL MATCH (s)-[:REFERENCES]->(ref:StandardDocument)
RETURN s, collect(DISTINCT ch) AS chapters, collect(DISTINCT cl) + collect(DISTINCT cl2) AS clauses,
       collect(DISTINCT t) AS terms, collect(DISTINCT ref) AS references
"""

QUERY_ALL_REQUIREMENTS_FOR_STANDARD = """
MATCH (s:StandardDocument {standard_id: $standard_id})
MATCH (s)-[:HAS_CLAUSE|HAS_CHAPTER*1..3]->(cl:Clause)
MATCH (cl)-[:HAS_REQUIREMENT]->(r:Requirement)
RETURN r, cl
ORDER BY cl.clause_number
"""

QUERY_ALL_INDICATORS_FOR_STANDARD = """
MATCH (s:StandardDocument {standard_id: $standard_id})
MATCH (s)-[:HAS_CLAUSE|HAS_CHAPTER*1..3]->(cl:Clause)
MATCH (cl)-[:HAS_INDICATOR]->(i:Indicator)
RETURN i, cl
ORDER BY cl.clause_number
"""


# ── Param builders ───────────────────────────────────────────────────────────

def standard_params(doc: StandardDocument) -> dict:
    from ..common.utils import dt_iso
    return {
        "standard_id": doc.standard_id, "code": doc.code, "title": doc.title,
        "industry": doc.industry, "status": doc.status.value,
        "publish_date": doc.publish_date.isoformat() if doc.publish_date else None,
        "effective_date": doc.effective_date.isoformat() if doc.effective_date else None,
        "issuing_body": doc.issuing_body, "source_file": doc.source_file,
        "summary": doc.summary,
    }


def chapter_params(ch: Chapter) -> dict:
    return {
        "chapter_id": ch.chapter_id, "standard_id": ch.standard_id,
        "chapter_number": ch.chapter_number, "title": ch.title,
        "level": ch.level, "order_index": ch.order_index,
    }


def clause_params(cl: Clause) -> dict:
    return {
        "clause_id": cl.clause_id, "standard_id": cl.standard_id,
        "chapter_id": cl.chapter_id, "clause_number": cl.clause_number,
        "title": cl.title, "content": cl.content,
        "level": cl.level, "order_index": cl.order_index,
    }


def term_params(t: Term) -> dict:
    return {
        "term_id": t.term_id, "name": t.name, "definition": t.definition,
        "standard_id": t.standard_id, "source_clause_id": t.source_clause_id,
    }


def requirement_params(r: Requirement) -> dict:
    return {
        "requirement_id": r.requirement_id, "clause_id": r.clause_id,
        "text": r.text, "obligation": r.obligation.value,
        "standard_id": r.standard_id,
        "requirement_type": r.requirement_type.value, "confidence": r.confidence,
    }


def indicator_params(ind: Indicator) -> dict:
    return {
        "indicator_id": ind.indicator_id, "name": ind.name,
        "value": ind.value, "operator": ind.operator, "unit": ind.unit,
        "description": ind.description, "standard_id": ind.standard_id,
        "source_clause_id": ind.source_clause_id,
    }


def method_params(m: Method) -> dict:
    return {
        "method_id": m.method_id, "name": m.name,
        "description": m.description, "standard_id": m.standard_id,
        "source_clause_id": m.source_clause_id,
    }


def standard_object_params(o: StandardObject) -> dict:
    return {
        "object_id": o.object_id, "name": o.name,
        "object_type": o.object_type.value, "standard_id": o.standard_id,
        "description": o.description,
    }
