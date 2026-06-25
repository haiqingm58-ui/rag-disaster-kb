from __future__ import annotations

from fastapi import APIRouter

from app_server.services.official_disaster_service import official_source_status


router = APIRouter(prefix="/disaster-sources", tags=["official-disaster-sources"])


@router.get("")
def sources() -> dict:
    items = official_source_status()
    return {"sources": items, "count": len(items)}
