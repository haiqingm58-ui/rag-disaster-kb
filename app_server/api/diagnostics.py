from __future__ import annotations

import os
import platform
import re
import sys
import time
from pathlib import Path

from fastapi import APIRouter

from app_server.settings import settings
from config import (
    BASE_DIR,
    CACHE_DIR,
    CHROMA_DIR,
    DATA_DIR,
    EMBEDDING_PROVIDER,
    LLM_PROVIDER,
)
from src.vectorstore.chroma_store import embedding_config_status


router = APIRouter(tags=["diagnostics"])
START_TIME = time.time()


def _exists(path: Path) -> bool:
    return Path(path).exists()


def _recent_errors(limit: int = 5) -> list[str]:
    log_path = settings.logs_dir / "app.log"
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return ["日志文件读取失败"]
    errors = [_redact(line[-500:]) for line in lines if " ERROR " in line or "Traceback" in line]
    return errors[-limit:]


def _redact(text: str) -> str:
    text = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-***", text)
    text = re.sub(r"(?i)(api[_-]?key['\"]?\s*[:=]\s*)[^,\s]+", r"\1***", text)
    return text


def _recommendations(paths: dict, embedding_ready: bool) -> list[str]:
    tips = []
    if settings.is_production and not settings.cors_origins_raw.strip():
        tips.append("生产环境建议配置 CORS_ORIGINS 为你的域名或公网 IP。")
    if not embedding_ready:
        tips.append("Embedding 配置不可用；2G 服务器建议配置远程 openai_compatible embedding，或使用已构建好的 Chroma 数据。")
    if not paths["graph_data"]:
        tips.append("未找到 graph_data.json，知识图谱接口会降级为空数据。")
    if not paths["search_index"]:
        tips.append("未找到 search_index.json，知识图谱搜索会降级为空列表。")
    if not paths["chroma_dir"]:
        tips.append("Chroma 目录不存在或不可访问，请检查 CHROMA_DIR。")
    if not paths["logs_dir"]:
        tips.append("logs 目录不存在，建议创建以便排查生产问题。")
    return tips


@router.get("/diagnostics")
def diagnostics() -> dict:
    graph_candidates = [BASE_DIR / "docs/data/graph_data.json", BASE_DIR / "exports/standard_kg_browser/graph_data.json"]
    search_candidates = [BASE_DIR / "docs/data/search_index.json", BASE_DIR / "exports/standard_kg_browser/search_index.json"]
    paths = {
        "data_dir": _exists(DATA_DIR),
        "cache_dir": _exists(CACHE_DIR),
        "chroma_dir": _exists(CHROMA_DIR),
        "graph_data": any(path.exists() for path in graph_candidates),
        "search_index": any(path.exists() for path in search_candidates),
        "logs_dir": _exists(settings.logs_dir),
    }
    embedding_status = embedding_config_status()
    recommendations = _recommendations(paths, embedding_status["ready"])
    memory_hint = "limited" if (os.cpu_count() or 1) <= 2 else "normal"
    return {
        "status": "ok" if not recommendations else "degraded",
        "app": {
            "env": settings.app_env,
            "version": settings.version,
            "uptime_seconds": round(time.time() - START_TIME),
        },
        "system": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "memory_hint": memory_hint,
        },
        "config": {
            "llm_provider": LLM_PROVIDER,
            "embedding_provider": EMBEDDING_PROVIDER,
            "embedding_ready": embedding_status["ready"],
            "embedding_model": embedding_status["model"],
            "max_upload_mb": settings.max_upload_mb,
            "graph_top_k": settings.graph_top_k,
        },
        "paths": paths,
        "recent_errors": _recent_errors(),
        "recommendations": recommendations,
    }
