#!/usr/bin/env python3
"""Export common Neo4j Browser Cypher queries as a Markdown reference.

Usage:
  python scripts/export_graph_queries.py
"""

from __future__ import annotations

from pathlib import Path

OUTPUT_PATH = Path("data/standards/import_reports/neo4j_queries.md")

QUERIES: dict[str, list[tuple[str, str]]] = {
    "标准总览": [
        ("查看所有标准", """
MATCH (s:StandardDocument)
RETURN s.code, s.title, s.industry, s.status
ORDER BY s.code
"""),
        ("查看所有标准及节点数量", """
MATCH (s:StandardDocument)
OPTIONAL MATCH (s)-[:HAS_CHAPTER]->(ch:Chapter)
OPTIONAL MATCH (s)-[:HAS_CLAUSE]->(cl:Clause)
OPTIONAL MATCH (s)-[:DEFINES]->(t:Term)
RETURN s.code, s.title,
       count(DISTINCT ch) AS chapters,
       count(DISTINCT cl) AS clauses,
       count(DISTINCT t) AS terms
ORDER BY s.code
"""),
    ],

    "章节结构": [
        ("查看某标准的章节树", """
MATCH (s:StandardDocument {code: "GB/T 32864-2016"})
MATCH (s)-[:HAS_CHAPTER]->(ch:Chapter)
MATCH (ch)-[:HAS_CLAUSE]->(cl:Clause)
RETURN ch.chapter_number, ch.title, cl.clause_number, cl.title
ORDER BY toInteger(ch.chapter_number), cl.clause_number
LIMIT 50
"""),
        ("查看某标准的完整子图", """
MATCH (s:StandardDocument {code: "GB/T 32864-2016"})
MATCH (s)-[*1..3]->(n)
RETURN s, n
LIMIT 200
"""),
        ("查看某标准的完整子图（按标准ID）", """
MATCH (s:StandardDocument {standard_id: "std-ff5ca886ab58"})
MATCH (s)-[*1..2]->(n)
RETURN s, n
"""),
    ],

    "术语查询": [
        ("查看所有术语", """
MATCH (s:StandardDocument)-[:DEFINES]->(t:Term)
RETURN s.code, t.name, t.definition
ORDER BY s.code
LIMIT 50
"""),
        ("查看 T/CAGHP 002-2018 的术语", """
MATCH (s:StandardDocument {code: "T/CAGHP 002-2018"})-[:DEFINES]->(t:Term)
RETURN t.name, t.definition
ORDER BY t.name
LIMIT 50
"""),
        ("查看含特定关键词的术语", """
MATCH (s:StandardDocument)-[:DEFINES]->(t:Term)
WHERE t.name CONTAINS "滑坡" OR t.definition CONTAINS "滑坡"
RETURN s.code, t.name, t.definition
LIMIT 20
"""),
    ],

    "规范要求": [
        ("查看所有规范要求（强制性）", """
MATCH (s:StandardDocument)
MATCH (s)-[:HAS_CLAUSE]->(cl:Clause)
MATCH (cl)-[:HAS_REQUIREMENT]->(r:Requirement)
WHERE r.obligation = "shall"
RETURN s.code, cl.clause_number, r.text
ORDER BY s.code
LIMIT 50
"""),
        ("查看某标准的所有规范要求", """
MATCH (s:StandardDocument {code: "GB/T 32864-2016"})
MATCH (s)-[:HAS_CLAUSE*1..2]->(cl:Clause)
MATCH (cl)-[:HAS_REQUIREMENT]->(r:Requirement)
RETURN cl.clause_number, r.text, r.obligation
ORDER BY cl.clause_number
LIMIT 50
"""),
    ],

    "指标参数": [
        ("查看所有指标参数", """
MATCH (s:StandardDocument)
MATCH (s)-[:HAS_CLAUSE]->(cl:Clause)
MATCH (cl)-[:HAS_INDICATOR]->(i:Indicator)
RETURN s.code, cl.clause_number, i.name, i.operator, i.value, i.unit
ORDER BY s.code
LIMIT 50
"""),
        ("查看某标准的所有指标参数", """
MATCH (s:StandardDocument {code: "GB/T 38509-2020"})
MATCH (s)-[:HAS_CLAUSE*1..2]->(cl:Clause)
MATCH (cl)-[:HAS_INDICATOR]->(i:Indicator)
RETURN cl.clause_number, i.name, i.operator, i.value, i.unit
ORDER BY cl.clause_number
LIMIT 50
"""),
    ],

    "关键词搜索": [
        ("搜索「滑坡」相关条款", """
MATCH (s:StandardDocument)-[:HAS_CLAUSE]->(cl:Clause)
WHERE cl.content CONTAINS "滑坡"
RETURN s.code, cl.clause_number, cl.content
LIMIT 20
"""),
        ("搜索「暴雨」相关条款", """
MATCH (s:StandardDocument)-[:HAS_CLAUSE]->(cl:Clause)
WHERE cl.content CONTAINS "暴雨"
RETURN s.code, cl.clause_number, cl.content
LIMIT 20
"""),
        ("搜索「风险评估」相关条款", """
MATCH (s:StandardDocument)-[:HAS_CLAUSE]->(cl:Clause)
WHERE cl.content CONTAINS "风险评估"
RETURN s.code, cl.clause_number, cl.content
LIMIT 20
"""),
        ("搜索「泥石流」相关条款", """
MATCH (s:StandardDocument)-[:HAS_CLAUSE]->(cl:Clause)
WHERE cl.content CONTAINS "泥石流"
RETURN s.code, cl.clause_number, cl.content
LIMIT 20
"""),
    ],

    "统计查询": [
        ("关系类型统计", """
MATCH ()-[r]->()
RETURN type(r) AS relation_type, count(r) AS count
ORDER BY count DESC
"""),
        ("节点类型统计", """
MATCH (n)
RETURN labels(n)[0] AS node_type, count(n) AS count
ORDER BY count DESC
"""),
        ("按标准统计关系数", """
MATCH (s:StandardDocument)
MATCH (s)-[r]->(n)
RETURN s.code, count(r) AS relationships
ORDER BY relationships DESC
"""),
    ],

    "健康检查": [
        ("检查幽灵节点", """
MATCH (n)
WHERE (n:StandardDocument AND n.standard_id = 'standard_id')
   OR (n:Chapter AND n.chapter_id = 'chapter_id')
   OR (n:Clause AND n.clause_id = 'clause_id')
RETURN labels(n)[0] AS label, count(n) AS count
"""),
        ("检查孤儿节点", """
MATCH (n)
WHERE n.standard_id IS NOT NULL
  AND NOT EXISTS {
    MATCH (s:StandardDocument {standard_id: n.standard_id})
  }
RETURN labels(n)[0] AS label, count(n) AS count
"""),
        ("检查孤立节点", """
MATCH (n)
WHERE (n:Chapter OR n:Clause OR n:Requirement OR n:Indicator OR n:Term)
  AND n.standard_id IS NOT NULL
  AND NOT (n)--()
RETURN labels(n)[0] AS label, count(n) AS count
"""),
        ("删除错误导入的标准", """
MATCH (s:StandardDocument {code: "GB/T XXXXX-XXXX"})
DETACH DELETE s
// 然后运行:
// python scripts/delete_standard_graph.py --code "GB/T XXXXX-XXXX" --confirm
"""),
    ],
}


def build_markdown() -> str:
    lines = [
        "# Neo4j 知识图谱查询参考",
        "",
        "> 在 Neo4j Browser 中粘贴并执行以下查询。",
        "> 替换 `{code}` 和 `{standard_id}` 占位符为实际值。",
        "",
        "## 当前已导入标准",
        "",
        "| 编号 | 标题 | Standard ID |",
        "|------|------|-------------|",
        "| GB/T 32864-2016 | 滑坡防治工程勘查规范 | std-ff5ca886ab58 |",
        "| GB/T 38509-2020 | 滑坡防治设计规范 | std-183dcb017448 |",
        "| T/CAGHP 002-2018 | 地质灾害防治基本术语 | std-e4dda33fcbb4 |",
        "| GB/T 4012-2021 | 地质灾害危险性评估规范 | std-b70ab92e6acc |",
        "| GB/T 33680-2017 | 暴雨灾害等级 | std-950a7dee2b65 |",
        "| GB/T 44011.1-2024 | 自然灾害综合风险评估技术规范 | std-a52a771275a7 |",
        "",
    ]

    for section, queries in QUERIES.items():
        lines.append(f"## {section}")
        lines.append("")
        for title, cypher in queries:
            lines.append(f"### {title}")
            lines.append("")
            lines.append("```cypher")
            lines.append(cypher.strip())
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    markdown = build_markdown()
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")
    print(f"查询参考已导出: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
