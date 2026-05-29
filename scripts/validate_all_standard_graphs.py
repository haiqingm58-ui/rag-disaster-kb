#!/usr/bin/env python3
"""Validate all imported standard graphs in Neo4j.

Generates Markdown + JSON reports under data/standards/import_reports/.

Usage:
  python scripts/validate_all_standard_graphs.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.graph.common.neo4j_client import get_session, neo4j_config


REPORT_DIR = Path("data/standards/import_reports")

QUERY_STANDARDS = """
MATCH (s:StandardDocument)
RETURN s.standard_id AS standard_id, s.code AS code, s.title AS title,
       s.industry AS industry, s.status AS status
ORDER BY s.code
"""

QUERY_STATS = """
MATCH (s:StandardDocument {standard_id: $sid})
OPTIONAL MATCH (s)-[:HAS_CHAPTER]->(ch:Chapter)
OPTIONAL MATCH (s)-[:HAS_CLAUSE]->(cl:Clause)
OPTIONAL MATCH (s)-[:DEFINES]->(t:Term)
RETURN count(DISTINCT ch) AS chapters,
       count(DISTINCT cl) AS clauses,
       count(DISTINCT t) AS terms
"""

QUERY_EXTRACTED = """
MATCH (s:StandardDocument {standard_id: $sid})
OPTIONAL MATCH (n)
WHERE n.standard_id = $sid AND (
  n:Requirement OR n:Indicator OR n:Method OR n:StandardObject
)
RETURN
  count(CASE WHEN n:Requirement THEN 1 END) AS requirements,
  count(CASE WHEN n:Indicator THEN 1 END) AS indicators,
  count(CASE WHEN n:Method THEN 1 END) AS methods,
  count(CASE WHEN n:StandardObject THEN 1 END) AS objects
"""

QUERY_REL_COUNT = """
MATCH (s:StandardDocument {standard_id: $sid})
MATCH (s)-[r]->(n)
RETURN count(r) AS rels_from_std
"""

QUERY_ALL_RELS = """
MATCH (s:StandardDocument {standard_id: $sid})
OPTIONAL MATCH (n) WHERE n.standard_id = $sid
OPTIONAL MATCH (n)-[r]->()
RETURN count(DISTINCT r) AS total_rels
"""

QUERY_GHOST_NODES = """
MATCH (n)
WHERE (n:StandardDocument AND n.standard_id = 'standard_id')
   OR (n:Chapter AND n.chapter_id = 'chapter_id')
   OR (n:Clause AND n.clause_id = 'clause_id')
   OR (n:Term AND n.term_id = 'term_id')
   OR (n:Requirement AND n.requirement_id = 'requirement_id')
   OR (n:Indicator AND n.indicator_id = 'indicator_id')
   OR (n:Method AND n.method_id = 'method_id')
   OR (n:StandardObject AND n.object_id = 'object_id')
RETURN labels(n)[0] AS label, count(n) AS count
"""

QUERY_ORPHANS = """
MATCH (n)
WHERE (n:Chapter OR n:Clause OR n:Term OR n:Requirement
       OR n:Indicator OR n:Method OR n:StandardObject)
  AND n.standard_id IS NOT NULL
  AND n.standard_id <> ''
  AND NOT EXISTS {
    MATCH (s:StandardDocument {standard_id: n.standard_id})
  }
RETURN labels(n)[0] AS label, count(n) AS count
"""

QUERY_ISOLATED = """
MATCH (n)
WHERE (n:Chapter OR n:Clause OR n:Requirement OR n:Indicator OR n:Term)
  AND n.standard_id IS NOT NULL
  AND n.standard_id <> ''
  AND NOT (n)--()
RETURN labels(n)[0] AS label, count(n) AS count
"""

QUERY_RELATION_TYPES = """
MATCH ()-[r]->()
RETURN type(r) AS rel_type, count(r) AS count
ORDER BY count DESC
"""


def validate_all() -> dict:
    """Run all validations and return a report dict."""
    db = neo4j_config()[3]
    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "standards": [],
        "ghost_nodes": [],
        "orphan_nodes": [],
        "isolated_nodes": [],
        "all_relation_types": [],
    }

    with get_session(db) as sess:
        # List all standards
        std_records = list(sess.run(QUERY_STANDARDS))
        if not std_records:
            report["summary"] = "No standards found in database."
            return report

        for rec in std_records:
            sid = rec["standard_id"]
            code = rec.get("code", "") or sid

            # Stats
            stats = sess.run(QUERY_STATS, {"sid": sid}).single()
            extracted = sess.run(QUERY_EXTRACTED, {"sid": sid}).single()
            rels = sess.run(QUERY_REL_COUNT, {"sid": sid}).single()

            # Count all nodes with this standard_id
            node_count = sess.run(
                "MATCH (n {standard_id: $sid}) RETURN count(n) AS cnt",
                {"sid": sid},
            ).single()

            std_report = {
                "standard_id": sid,
                "code": code,
                "title": rec.get("title", "") or "",
                "industry": rec.get("industry", "") or "",
                "chapters": stats["chapters"] if stats else 0,
                "clauses": stats["clauses"] if stats else 0,
                "terms": stats["terms"] if stats else 0,
                "requirements": extracted["requirements"] if extracted else 0,
                "indicators": extracted["indicators"] if extracted else 0,
                "methods": extracted["methods"] if extracted else 0,
                "objects": extracted["objects"] if extracted else 0,
                "relationships_from_std": rels["rels_from_std"] if rels else 0,
                "total_nodes": node_count["cnt"] if node_count else 0,
            }
            report["standards"].append(std_report)

        # Ghost nodes
        ghost = list(sess.run(QUERY_GHOST_NODES))
        report["ghost_nodes"] = [
            {"label": r["label"], "count": r["count"]} for r in ghost
        ]

        # Orphan nodes (standard_id pointing to nonexistent standard)
        orphans = list(sess.run(QUERY_ORPHANS))
        report["orphan_nodes"] = [
            {"label": r["label"], "count": r["count"]} for r in orphans
        ]

        # Isolated nodes (having standard_id but no relationships)
        isolated = list(sess.run(QUERY_ISOLATED))
        report["isolated_nodes"] = [
            {"label": r["label"], "count": r["count"]} for r in isolated
        ]

        # All relation types
        rel_types = list(sess.run(QUERY_RELATION_TYPES))
        report["all_relation_types"] = [
            {"type": r["rel_type"], "count": r["count"]} for r in rel_types
        ]

    # Summary
    report["summary"] = (
        f"{len(report['standards'])} standards, "
        f"{sum(s['total_nodes'] for s in report['standards'])} total nodes, "
        f"{sum(s['relationships_from_std'] for s in report['standards'])} relationships"
    )

    return report


def write_markdown(report: dict, path: Path) -> None:
    """Write the report as Markdown."""
    lines = [
        "# 知识图谱验证报告",
        f"\n生成时间：{report['generated_at']}",
        f"\n## 概览",
        f"\n{report.get('summary', 'N/A')}",
    ]

    lines.append("\n## 标准列表\n")
    lines.append("| 标准编号 | 标题 | Ch | Cl | Terms | Reqs | Inds | Meths | Objs | 节点 | 关系 |")
    lines.append("|----------|------|-----|-----|-------|------|------|-------|------|------|------|")
    for s in report.get("standards", []):
        lines.append(
            f"| {s['code']} | {s['title'][:30]} | {s['chapters']} | {s['clauses']} | "
            f"{s['terms']} | {s['requirements']} | {s['indicators']} | "
            f"{s['methods']} | {s['objects']} | {s['total_nodes']} | "
            f"{s['relationships_from_std']} |"
        )

    ghosts = report.get("ghost_nodes", [])
    if ghosts:
        lines.append("\n## 幽灵节点（属性名为属性值）\n")
        lines.append("| 标签 | 数量 |")
        lines.append("|------|------|")
        for g in ghosts:
            lines.append(f"| {g['label']} | {g['count']} |")
    else:
        lines.append("\n## 幽灵节点\n\n✅ 无幽灵节点。")

    orphans = report.get("orphan_nodes", [])
    if orphans:
        lines.append("\n## 孤儿节点（standard_id 指向不存在的标准）\n")
        lines.append("| 标签 | 数量 |")
        lines.append("|------|------|")
        for o in orphans:
            lines.append(f"| {o['label']} | {o['count']} |")
    else:
        lines.append("\n## 孤儿节点\n\n✅ 无孤儿节点。")

    isolated = report.get("isolated_nodes", [])
    if isolated:
        lines.append("\n## 孤立节点（无任何关系）\n")
        lines.append("| 标签 | 数量 |")
        lines.append("|------|------|")
        for i in isolated:
            lines.append(f"| {i['label']} | {i['count']} |")
    else:
        lines.append("\n## 孤立节点\n\n✅ 无孤立节点。")

    rels = report.get("all_relation_types", [])
    if rels:
        lines.append("\n## 关系类型统计\n")
        lines.append("| 关系类型 | 数量 |")
        lines.append("|----------|------|")
        for r in rels:
            lines.append(f"| {r['type']} | {r['count']} |")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Markdown report: {path}")


def main():
    print("Running validation...")
    report = validate_all()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    md_path = REPORT_DIR / "graph_validation_report.md"
    json_path = REPORT_DIR / "graph_validation_report.json"

    write_markdown(report, md_path)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"JSON report: {json_path}")

    # Print summary
    print(f"\n{report['summary']}")
    for s in report.get("standards", []):
        print(f"  {s['code']}: {s['chapters']}ch/{s['clauses']}cl/"
              f"{s['terms']}t/{s['requirements']}r/{s['indicators']}i")

    ghosts = report.get("ghost_nodes", [])
    print(f"\nGhost nodes: {sum(g['count'] for g in ghosts) if ghosts else 0}")
    orphans = report.get("orphan_nodes", [])
    print(f"Orphan nodes: {sum(o['count'] for o in orphans) if orphans else 0}")
    isolated = report.get("isolated_nodes", [])
    print(f"Isolated nodes: {sum(i['count'] for i in isolated) if isolated else 0}")


if __name__ == "__main__":
    main()
