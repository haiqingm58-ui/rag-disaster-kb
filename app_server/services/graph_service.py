from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from app_server.settings import settings


logger = logging.getLogger(__name__)

GRAPH_CANDIDATES = [
    Path("docs/data/graph_data.json"),
    Path("exports/standard_kg_browser/graph_data.json"),
]
SEARCH_CANDIDATES = [
    Path("docs/data/search_index.json"),
    Path("exports/standard_kg_browser/search_index.json"),
]

TYPE_TO_COLLECTION = {
    "标准": "standards",
    "条款": "clauses",
    "术语": "terms",
    "要求": "requirements",
    "指标": "indicators",
    "方法": "methods",
    "章节": "chapters",
}
DOMAIN_TERMS = (
    "滑坡",
    "泥石流",
    "崩塌",
    "洪水",
    "暴雨",
    "山洪",
    "风险",
    "评估",
    "危险性",
    "监测",
    "预警",
    "应急",
    "抗滑桩",
    "挡土墙",
    "排水",
    "治理",
    "防治",
    "勘查",
    "设计",
    "施工",
    "要求",
    "指标",
    "标准",
    "条款",
)


def _first_existing(paths: list[Path]) -> Path | None:
    return next((p for p in paths if p.exists()), None)


def _norm(text: Any) -> str:
    return str(text or "").lower()


def _query_terms(query: str) -> list[str]:
    query_norm = query.lower().strip()
    terms = [w for w in query_norm.split() if w]
    terms.extend(term.lower() for term in DOMAIN_TERMS if term in query)
    if not terms and query_norm:
        terms.append(query_norm)
    unique_terms: list[str] = []
    for term in terms:
        if term and term not in unique_terms:
            unique_terms.append(term)
    return unique_terms


class GraphService:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.graph_path = _first_existing(GRAPH_CANDIDATES)
        self.search_path = _first_existing(SEARCH_CANDIDATES)
        self.data = self._load_graph()
        self.search_index = self._load_search_index()
        self.node_map = self._build_node_map()

    @property
    def ready(self) -> bool:
        return bool(self.data and self.data.get("standards"))

    def _load_graph(self) -> dict[str, Any]:
        if not self.graph_path:
            self.errors.append("graph_data.json not found")
            return {}
        try:
            return json.loads(self.graph_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.exception("load graph data failed path=%s", self.graph_path)
            self.errors.append(f"graph_data.json load failed: {exc}")
            return {}

    def _load_search_index(self) -> list[dict[str, Any]]:
        if self.search_path:
            try:
                return json.loads(self.search_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.exception("load search index failed path=%s", self.search_path)
                self.errors.append(f"search_index.json load failed: {exc}")
                return []
        if not self.data.get("search_index"):
            self.errors.append("search_index.json not found")
        return self.data.get("search_index", []) if self.data else []

    def _build_node_map(self) -> dict[str, dict[str, Any]]:
        mapping: dict[str, dict[str, Any]] = {}
        for collection in TYPE_TO_COLLECTION.values():
            for item in self.data.get(collection, []) or []:
                node_id = item.get("id") or item.get("standard_id")
                if node_id:
                    mapping[node_id] = {"collection": collection, **item}
        return mapping

    def summary(self) -> dict[str, int]:
        counts = {
            "standards": len(self.data.get("standards", [])),
            "chapters": len(self.data.get("chapters", [])),
            "clauses": len(self.data.get("clauses", [])),
            "terms": len(self.data.get("terms", [])),
            "requirements": len(self.data.get("requirements", [])),
            "indicators": len(self.data.get("indicators", [])),
            "methods": len(self.data.get("methods", [])),
        }
        counts["nodes"] = sum(counts.values())
        counts["relationships"] = len(self.data.get("relationships", []))
        return counts

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        limit = min(max(limit, 1), settings.graph_top_k)
        words = _query_terms(query)
        results = []
        for item in self.search_index:
            haystack = _norm(" ".join([item.get("text", ""), item.get("title", ""), item.get("code", "")]))
            score = sum(2 if w in haystack else 0 for w in words)
            if query.lower() in haystack:
                score += 3
            if score <= 0:
                continue
            result = dict(item)
            result["score"] = float(score)
            result["node_id"] = self._guess_node_id(item)
            results.append(result)
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[:limit]

    def _guess_node_id(self, item: dict[str, Any]) -> str | None:
        collection = TYPE_TO_COLLECTION.get(item.get("type", ""))
        if not collection:
            return None
        code = item.get("code", "")
        number = item.get("number", "")
        title = item.get("title", "")
        for node in self.data.get(collection, []):
            if code and node.get("code") != code:
                continue
            if number and node.get("number", node.get("clause_number")) != number:
                continue
            if title and title not in str(node):
                continue
            return node.get("id") or node.get("standard_id")
        return None

    def standards(self) -> list[dict[str, Any]]:
        return self.data.get("standards", [])

    def standard_detail(self, code: str) -> dict[str, Any] | None:
        standard = next((s for s in self.standards() if s.get("code") == code), None)
        if not standard:
            return None
        return {
            "standard": standard,
            "chapters": [x for x in self.data.get("chapters", []) if x.get("code") == code],
            "clauses": [x for x in self.data.get("clauses", []) if x.get("code") == code],
            "terms": [x for x in self.data.get("terms", []) if x.get("code") == code],
            "requirements": [x for x in self.data.get("requirements", []) if x.get("code") == code],
            "indicators": [x for x in self.data.get("indicators", []) if x.get("code") == code],
            "methods": [x for x in self.data.get("methods", []) if x.get("code") == code],
        }

    def node(self, node_id: str) -> dict[str, Any] | None:
        node = self.node_map.get(node_id)
        if not node:
            return None
        return {"node": node, "relations": self._relations_for(node)}

    def _relations_for(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        code = node.get("code")
        clause_number = node.get("number") or node.get("clause_number")
        relations = []
        if code:
            standard = next((s for s in self.standards() if s.get("code") == code), None)
            if standard:
                relations.append({"type": "BELONGS_TO", "target": standard})
        if clause_number and code:
            for key, rel_type in [("terms", "DEFINES"), ("requirements", "HAS_REQUIREMENT"), ("indicators", "HAS_INDICATOR"), ("methods", "USES_METHOD")]:
                for item in self.data.get(key, []):
                    if item.get("code") == code and item.get("clause_number") == clause_number:
                        relations.append({"type": rel_type, "target": item})
        return relations[:50]

    def context_for_question(self, question: str, limit: int = 5) -> list[dict[str, Any]]:
        context = []
        for item in self.search(question, limit=limit):
            node_id = item.get("node_id")
            detail = self.node(node_id) if node_id else None
            context.append({
                "node_id": node_id or "",
                "label": item.get("title") or item.get("text", "")[:80],
                "type": item.get("type", ""),
                "code": item.get("code", ""),
                "number": item.get("number", ""),
                "clause_number": item.get("clause_number", ""),
                "content": item.get("text", ""),
                "relations": (detail or {}).get("relations", [])[:8],
            })
        return context


@lru_cache(maxsize=1)
def get_graph_service() -> GraphService:
    return GraphService()
