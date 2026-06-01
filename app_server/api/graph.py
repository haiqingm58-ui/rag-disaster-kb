from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app_server.schemas.graph import GraphSummary
from app_server.services.graph_service import get_graph_service


router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/summary", response_model=GraphSummary)
def summary() -> dict:
    return get_graph_service().summary()


@router.get("/search")
def search(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)) -> list[dict]:
    return get_graph_service().search(q, limit=limit)


@router.get("/standards")
def standards() -> list[dict]:
    return get_graph_service().standards()


@router.get("/standards/{code:path}")
def standard_detail(code: str) -> dict:
    detail = get_graph_service().standard_detail(code)
    if not detail:
        raise HTTPException(status_code=404, detail="standard not found")
    return detail


@router.get("/node/{node_id}")
def node(node_id: str) -> dict:
    detail = get_graph_service().node(node_id)
    if not detail:
        raise HTTPException(status_code=404, detail="node not found")
    return detail
