from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import requests

from app_server.settings import settings


logger = logging.getLogger(__name__)


TAVILY_DEFAULT_BASE_URL = "https://api.tavily.com"


class TavilyError(RuntimeError):
    """Raised when the optional Tavily adapter cannot complete a request."""


def tavily_configured() -> bool:
    return bool(settings.tavily_api_key.strip())


def _endpoint(path: str) -> str:
    return f"{settings.tavily_base_url.rstrip('/') or TAVILY_DEFAULT_BASE_URL}{path}"


def _normalize_results(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("results") or []
    if not isinstance(raw_items, list):
        return []

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        parsed = urlparse(url)
        title = item.get("title") or parsed.netloc or "Tavily 联网灾害信息"
        # Tavily returns:
        #   - "content": short LLM-friendly snippet (always present)
        #   - "raw_content": full cleaned page text (present when include_raw_content=True)
        snippet = item.get("content") or ""
        markdown = item.get("raw_content") or snippet
        results.append({
            "title": title,
            "url": url,
            "snippet": snippet,
            "markdown": markdown,
            "source": parsed.netloc or "tavily",
        })
    return results


def search_tavily(query: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Search the web through Tavily and return Firecrawl-shaped snippets.

    Tavily is optional. Callers should check `tavily_configured` or handle
    `TavilyError` and continue with the existing fallback search chain
    (Firecrawl → DuckDuckGo → Bing).
    """
    if not tavily_configured():
        raise TavilyError("TAVILY_API_KEY 未配置，已跳过 Tavily 联网搜索。")

    payload: dict[str, Any] = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": limit or settings.tavily_max_results,
        "search_depth": settings.tavily_search_depth,
        "include_raw_content": True,
        "include_answer": False,
    }
    try:
        response = requests.post(
            _endpoint("/search"),
            json=payload,
            timeout=settings.tavily_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("tavily search failed query=%s error=%s", query, exc)
        raise TavilyError(f"Tavily 搜索失败：{exc}") from exc

    if isinstance(data, dict) and data.get("error"):
        raise TavilyError(str(data.get("error")))
    return _normalize_results(data)
