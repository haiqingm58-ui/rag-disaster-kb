from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class GraphSummary(BaseModel):
    standards: int
    chapters: int
    clauses: int
    terms: int
    requirements: int
    indicators: int
    methods: int


class GraphSearchResult(BaseModel):
    type: str
    code: str = ""
    title: str = ""
    text: str = ""
    node_id: str | None = None
    score: float | None = None
    extra: dict[str, Any] = {}
