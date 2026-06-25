from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import requests

from app_server.settings import settings


logger = logging.getLogger(__name__)


class FirecrawlError(RuntimeError):
    """Raised when the optional Firecrawl adapter cannot complete a request."""


def firecrawl_configured() -> bool:
    return bool(settings.firecrawl_api_key.strip())


def _endpoint(path: str) -> str:
    return f"{settings.firecrawl_base_url.rstrip('/')}{path}"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.firecrawl_api_key}",
        "Content-Type": "application/json",
    }


def _normalize_search_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        data = payload.get("data") or payload.get("results") or []
        if isinstance(data, dict):
            raw_items = []
            for value in data.values():
                if isinstance(value, list):
                    raw_items.extend(value)
        else:
            raw_items = data
    else:
        raw_items = []

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        url = item.get("url") or item.get("sourceURL") or metadata.get("sourceURL") or metadata.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        parsed = urlparse(url)
        title = item.get("title") or metadata.get("title") or parsed.netloc or "联网灾害信息"
        snippet = item.get("description") or item.get("snippet") or metadata.get("description") or ""
        markdown = item.get("markdown") or item.get("content") or ""
        results.append({
            "title": title,
            "url": url,
            "snippet": snippet,
            "markdown": markdown,
            "source": parsed.netloc or "firecrawl",
        })
    return results


def search_firecrawl(query: str, limit: int | None = None, scrape: bool = True) -> list[dict[str, Any]]:
    """Search web pages through Firecrawl and return normalized snippets.

    Firecrawl is optional. Callers should check `firecrawl_configured` or handle
    `FirecrawlError` and continue with non-Firecrawl data sources.
    """
    if not firecrawl_configured():
        raise FirecrawlError("FIRECRAWL_API_KEY 未配置，已跳过 Firecrawl 联网爬取。")

    payload: dict[str, Any] = {
        "query": query,
        "limit": limit or settings.firecrawl_search_limit,
    }
    if scrape:
        payload["scrapeOptions"] = {
            "formats": ["markdown"],
            "onlyMainContent": True,
        }
    try:
        response = requests.post(
            _endpoint("/v2/search"),
            headers=_headers(),
            json=payload,
            timeout=settings.firecrawl_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("firecrawl search failed query=%s error=%s", query, exc)
        raise FirecrawlError(f"Firecrawl 搜索失败：{exc}") from exc

    if isinstance(data, dict) and data.get("success") is False:
        message = data.get("error") or data.get("message") or "Firecrawl 返回失败状态。"
        raise FirecrawlError(str(message))
    return _normalize_search_payload(data)


def scrape_firecrawl(url: str) -> dict[str, Any]:
    """Scrape one URL into markdown through Firecrawl."""
    if not firecrawl_configured():
        raise FirecrawlError("FIRECRAWL_API_KEY 未配置，已跳过 Firecrawl 网页抓取。")

    try:
        response = requests.post(
            _endpoint("/v2/scrape"),
            headers=_headers(),
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            timeout=settings.firecrawl_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("firecrawl scrape failed url=%s error=%s", url, exc)
        raise FirecrawlError(f"Firecrawl 抓取失败：{exc}") from exc

    payload = data.get("data") if isinstance(data, dict) else data
    if not isinstance(payload, dict):
        payload = {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        "title": metadata.get("title") or payload.get("title") or url,
        "url": metadata.get("sourceURL") or metadata.get("url") or url,
        "snippet": metadata.get("description") or "",
        "markdown": payload.get("markdown") or "",
        "source": urlparse(url).netloc or "firecrawl",
    }
