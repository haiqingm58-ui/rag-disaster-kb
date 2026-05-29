#!/usr/bin/env python3
"""Delete a complete standard knowledge graph from Neo4j.

Deletes a StandardDocument and ALL its related nodes (Chapter, Clause, Term,
Requirement, Indicator, Method, StandardObject). Also cleans up orphan nodes
that lost their parent.

Usage:
  # Dry-run (no actual deletion)
  python scripts/delete_standard_graph.py --code "GB/T 32864-2016"
  python scripts/delete_standard_graph.py --standard-id std-xxx

  # Confirm deletion
  python scripts/delete_standard_graph.py --code "GB/T 32864-2016" --confirm
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.common.neo4j_client import check_connection, get_session, neo4j_config


DELETE_BY_CODE = """
MATCH (s:StandardDocument {code: $code})
WITH s, s.standard_id AS sid
DETACH DELETE s
WITH sid
OPTIONAL MATCH (n)
WHERE n.standard_id = sid
DETACH DELETE n
"""

DELETE_BY_STANDARD_ID = """
MATCH (s:StandardDocument {standard_id: $standard_id})
WITH s, s.standard_id AS sid
DETACH DELETE s
WITH sid
OPTIONAL MATCH (n)
WHERE n.standard_id = sid
DETACH DELETE n
"""

DELETE_GHOST_NODES = """
MATCH (n)
WHERE (n:StandardDocument AND n.standard_id = 'standard_id')
   OR (n:Chapter AND n.chapter_id = 'chapter_id')
   OR (n:Clause AND n.clause_id = 'clause_id')
   OR (n:Term AND n.term_id = 'term_id')
   OR (n:Requirement AND n.requirement_id = 'requirement_id')
   OR (n:Indicator AND n.indicator_id = 'indicator_id')
   OR (n:Method AND n.method_id = 'method_id')
   OR (n:StandardObject AND n.object_id = 'object_id')
DETACH DELETE n
RETURN count(n) AS ghost_count
"""

COUNT_BY_CODE = """
MATCH (s:StandardDocument {code: $code})
OPTIONAL MATCH (s)-[:HAS_CHAPTER]->(ch:Chapter)
OPTIONAL MATCH (s)-[:HAS_CLAUSE]->(cl:Clause)
OPTIONAL MATCH (s)-[:DEFINES]->(t:Term)
RETURN count(DISTINCT s) AS standards,
       count(DISTINCT ch) AS chapters,
       count(DISTINCT cl) AS clauses,
       count(DISTINCT t) AS terms
"""

COUNT_ORPHANS = """
MATCH (n)
WHERE n.standard_id IS NOT NULL
  AND NOT EXISTS {
    MATCH (s:StandardDocument {standard_id: n.standard_id})
  }
RETURN labels(n)[0] AS label, count(n) AS count
"""


def _count_nodes(code: str = "", standard_id: str = ""):
    db = neo4j_config()[3]
    with get_session(db) as sess:
        if code:
            rec = sess.run(COUNT_BY_CODE, {"code": code}).single()
        elif standard_id:
            rec = sess.run(
                "MATCH (s:StandardDocument {standard_id: $sid}) "
                "OPTIONAL MATCH (s)-[*0..2]->(n) "
                "RETURN count(DISTINCT s) AS standards, count(DISTINCT n) AS related",
                {"sid": standard_id},
            ).single()
        else:
            return {}
        return dict(rec) if rec else {}


def main():
    ap = argparse.ArgumentParser(description="Delete a standard graph from Neo4j")
    ap.add_argument("--code", help="Standard code (e.g. GB/T 32864-2016)")
    ap.add_argument("--standard-id", help="Standard ID (e.g. std-xxx)")
    ap.add_argument("--confirm", action="store_true",
                    help="Required to actually delete. Without this, runs dry-run.")
    ap.add_argument("--clean-orphans", action="store_true",
                    help="After deletion, also clean any orphan nodes.")
    args = ap.parse_args()

    if not args.code and not args.standard_id:
        ap.error("Must specify --code or --standard-id")

    conn = check_connection()
    if not conn["ok"]:
        print(f"ERROR: {conn['error']}")
        sys.exit(1)

    db = neo4j_config()[3]
    code = args.code
    sid = args.standard_id

    # Dry-run: count what would be deleted
    print("=" * 60)
    if not args.confirm:
        print("DRY-RUN — 不会实际删除")
    print("=" * 60)

    with get_session(db) as sess:
        if code:
            # Find the standard_id first
            rec = sess.run(
                "MATCH (s:StandardDocument {code: $code}) RETURN s.standard_id AS sid, s.title AS title",
                {"code": code},
            ).single()
            if not rec:
                print(f"未找到标准: {code}")
                return
            sid = rec["sid"]
            print(f"标准: {code} — {rec.get('title', '')}")
            print(f"Standard ID: {sid}")

        print(f"Standard ID: {sid}")

        # Count all related nodes
        count_result = sess.run(
            "MATCH (n) WHERE n.standard_id = $sid OR "
            "  EXISTS { MATCH (s:StandardDocument {standard_id: $sid})-[:HAS_CHAPTER|HAS_CLAUSE|DEFINES]->(n) } "
            "RETURN labels(n)[0] AS label, count(n) AS cnt",
            {"sid": sid},
        )
        counts = {r["label"]: r["cnt"] for r in count_result}
        total = sum(counts.values())

        print()
        print("将要删除的节点:")
        for label in ["StandardDocument", "Chapter", "Clause", "Term",
                       "Requirement", "Indicator", "Method", "StandardObject"]:
            c = counts.get(label, 0)
            if c > 0:
                print(f"  {label}: {c}")
        print(f"  ─────────────────")
        print(f"  总计: {total}")

    if not args.confirm:
        print()
        print("这是 dry-run。要实际删除请加 --confirm")
        return

    # Confirm deletion
    print()
    print(f"确认删除标准 {sid} 的所有节点? 输入 yes 继续:")
    user_input = input("> ").strip().lower()
    if user_input != "yes":
        print("已取消。")
        return

    with get_session(db) as sess:
        if code:
            sess.run(DELETE_BY_CODE, {"code": code})
        else:
            sess.run(DELETE_BY_STANDARD_ID, {"standard_id": sid})

    print("✅ 删除完成")

    if args.clean_orphans:
        with get_session(db) as sess:
            orphan_result = list(sess.run(COUNT_ORPHANS))
        if orphan_result:
            print("发现孤立节点:")
            for r in orphan_result:
                print(f"  {r['label']}: {r['count']}")
            with get_session(db) as sess:
                sess.run("MATCH (n) WHERE n.standard_id IS NOT NULL "
                         "AND NOT EXISTS { MATCH (s:StandardDocument "
                         "{standard_id: n.standard_id}) } DETACH DELETE n")
            print("✅ 孤立节点已清理")
        else:
            print("无孤立节点")


if __name__ == "__main__":
    main()
