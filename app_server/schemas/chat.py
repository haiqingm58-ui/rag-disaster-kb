from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: str | None = None
    use_graph: bool = True
    use_realtime: bool = True
    top_k: int = Field(default=5, ge=1, le=20)


class SourceItem(BaseModel):
    type: Literal["document", "graph", "realtime", "general"]
    title: str
    content: str
    score: float | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    graph_context: list[dict[str, Any]]
    realtime_events: list[dict[str, Any]]
    debug: dict[str, Any]
