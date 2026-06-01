from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter

from app_server.settings import settings
from app_server.services.graph_service import get_graph_service
from config import CACHE_DIR, CHROMA_DIR, COLLECTION_DOCS, DOCUMENTS_DIR, EMBEDDING_PROVIDER, LLM_PROVIDER
from src.vectorstore.chroma_store import collection_count, embedding_config_status


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    errors = []
    try:
        collection_count(COLLECTION_DOCS)
        chroma_ready = True
    except Exception as exc:
        chroma_ready = False
        errors.append(f"Chroma unavailable: {exc}")

    graph = get_graph_service()
    graph_counts = graph.summary()
    if graph.errors:
        errors.extend(graph.errors)

    data_dirs = {
        "chroma": Path(CHROMA_DIR).exists(),
        "documents": Path(DOCUMENTS_DIR).exists(),
        "cache": Path(CACHE_DIR).exists(),
    }
    for name, exists in data_dirs.items():
        if not exists:
            errors.append(f"data dir missing: {name}")

    embedding_status = embedding_config_status()
    if not embedding_status["ready"]:
        errors.append(embedding_status["message"])

    status = "ok" if chroma_ready and graph.ready and embedding_status["ready"] and not errors else "degraded"
    return {
        "status": status,
        "app_env": settings.app_env,
        "version": settings.version,
        "llm_provider": LLM_PROVIDER,
        "embedding_provider": EMBEDDING_PROVIDER,
        "embedding_ready": embedding_status["ready"],
        "embedding_status": embedding_status,
        "chroma_ready": chroma_ready,
        "graph_ready": graph.ready,
        "graph_counts": {
            "standards": graph_counts.get("standards", 0),
            "chapters": graph_counts.get("chapters", 0),
            "clauses": graph_counts.get("clauses", 0),
        },
        "data_dirs": data_dirs,
        "server_time": datetime.now().isoformat(timespec="seconds"),
        "errors": errors,
    }
