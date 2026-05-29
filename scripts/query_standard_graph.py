#!/usr/bin/env python3
"""Query the industry standard knowledge graph in Neo4j.

Usage:
  python scripts/query_standard_graph.py --code "DZ/T 0286-2015"
  python scripts/query_standard_graph.py --keyword "滑坡"
  python scripts/query_standard_graph.py --requirements
  python scripts/query_standard_graph.py --indicators
  python scripts/query_standard_graph.py --object "泥石流"
  python scripts/query_standard_graph.py --clause-id "cl-xxxxxxxxxxxx"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.common.neo4j_client import check_connection, neo4j_config
from src.graph.standard import queries as q
from src.graph.standard.writer import get_session as std_get_session

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    ap = argparse.ArgumentParser(description="Query the standard knowledge graph")
    ap.add_argument("--code", help="Query by standard code")
    ap.add_argument("--keyword", help="Search clauses by keyword")
    ap.add_argument("--requirements", action="store_true", help="List all shall requirements")
    ap.add_argument("--indicators", action="store_true", help="List all indicators")
    ap.add_argument("--object", help="Find clauses related to an object")
    ap.add_argument("--clause-id", help="Show full subgraph for a clause")
    ap.add_argument("--limit", type=int, default=20, help="Max results (default 20)")
    ap.add_argument("--tree", action="store_true", help="Show full chapter/clause tree")
    args = ap.parse_args()

    conn = check_connection()
    if not conn["ok"]:
        print(f"ERROR: {conn['error']}")
        sys.exit(1)

    if args.code:
        if args.tree:
            _query_tree(args.code)
        else:
            _query_by_code(args.code)

    elif args.keyword:
        _query_keyword(args.keyword, args.limit)

    elif args.requirements:
        _query_requirements(args.limit)

    elif args.indicators:
        _query_indicators(args.limit)

    elif args.object:
        _query_object(args.object, args.limit)

    elif args.clause_id:
        _query_clause_subgraph(args.clause_id)

    else:
        ap.print_help()


def _query_by_code(code: str):
    from src.graph.common.neo4j_client import get_session
    with get_session() as sess:
        rec = sess.run(q.QUERY_STANDARD_BY_CODE, {"code": code}).single()
        if not rec:
            print(f"No standard found with code: {code}")
            return
        s = rec["s"]
        print(f"标准: {s.get('code')} — {s.get('title')}")
        print(f"行业: {s.get('industry')}  状态: {s.get('status')}")
        print(f"发布机构: {s.get('issuing_body')}")
        print(f"摘要: {s.get('summary', '')[:200]}")


def _query_tree(code: str):
    from src.graph.common.neo4j_client import get_session
    std_record = None
    with get_session() as sess:
        std_record = sess.run(q.QUERY_STANDARD_BY_CODE, {"code": code}).single()
    if not std_record:
        print(f"No standard found with code: {code}")
        return
    std_id = std_record["s"]["standard_id"]

    with get_session() as sess:
        rec = sess.run(q.QUERY_CHAPTER_TREE, {"standard_id": std_id}).single()
        if not rec:
            print("No chapters found")
            return
        print(f"标准: {code}")
        for ch in (rec.get("chapters") or []):
            print(f"  [{ch.get('chapter_number')}] {ch.get('title')}")
        for cl in (rec.get("clauses") or [])[:30]:
            print(f"    [{cl.get('clause_number')}] {cl.get('title') or cl.get('content', '')[:60]}")


def _query_keyword(keyword: str, limit: int):
    from src.graph.common.neo4j_client import get_session
    with get_session() as sess:
        records = list(sess.run(q.QUERY_CLAUSES_BY_KEYWORD, {"keyword": keyword, "limit": limit}))
    print(f"找到 {len(records)} 条包含 '{keyword}' 的条款:")
    for r in records:
        cl = r["cl"]
        s = r.get("s")
        std_code = s.get("code", "") if s else ""
        print(f"  [{std_code}] {cl.get('clause_number')}: {cl.get('content', '')[:100]}")


def _query_requirements(limit: int):
    from src.graph.common.neo4j_client import get_session
    with get_session() as sess:
        records = list(sess.run(q.QUERY_REQUIREMENTS_BY_OBLIGATION, {"obligation": "shall", "limit": limit}))
    print(f"强制性要求 (shall): {len(records)} 条")
    for r in records:
        req = r["r"]
        cl = r.get("cl")
        cl_num = cl.get("clause_number", "") if cl else ""
        print(f"  [{cl_num}] {req.get('text', '')[:120]}")


def _query_indicators(limit: int):
    from src.graph.common.neo4j_client import get_session
    with get_session() as sess:
        records = list(sess.run(q.QUERY_INDICATORS, {"limit": limit}))
    print(f"指标参数: {len(records)} 条")
    for r in records:
        ind = r["i"]
        cl = r.get("cl")
        cl_num = cl.get("clause_number", "") if cl else ""
        print(f"  [{cl_num}] {ind.get('name')} {ind.get('operator')} {ind.get('value')} {ind.get('unit', '')}")


def _query_object(obj_name: str, limit: int):
    from src.graph.common.neo4j_client import get_session
    with get_session() as sess:
        records = list(sess.run(q.QUERY_CLAUSES_BY_OBJECT, {"object_name": obj_name, "limit": limit}))
    print(f"与 '{obj_name}' 相关的条款: {len(records)} 条")
    for r in records:
        cl = r["cl"]
        s = r.get("s")
        std_code = s.get("code", "") if s else ""
        print(f"  [{std_code}] {cl.get('clause_number')}: {cl.get('content', '')[:100]}")


def _query_clause_subgraph(clause_id: str):
    from src.graph.common.neo4j_client import get_session
    with get_session() as sess:
        rec = sess.run(q.QUERY_CLAUSE_SUBGRAPH, {"clause_id": clause_id}).single()
        if not rec:
            print(f"No clause found: {clause_id}")
            return
        cl = rec["cl"]
        print(f"条款: [{cl.get('clause_number')}] {cl.get('title')}")
        print(f"内容: {cl.get('content', '')[:200]}")

        for label, key in [("要求", "requirements"), ("指标", "indicators"),
                           ("方法", "methods"), ("术语", "terms")]:
            items = rec.get(key) or []
            if items:
                print(f"\n{label} ({len(items)}):")
                for item in items[:5]:
                    print(f"  - {item.get('text') or item.get('name') or item}")


if __name__ == "__main__":
    main()
