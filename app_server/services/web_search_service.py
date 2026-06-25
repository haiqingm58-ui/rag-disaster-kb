from __future__ import annotations

import html
import logging
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

from app_server.settings import settings


logger = logging.getLogger(__name__)

DUCKDUCKGO_HTML_URL = "https://duckduckgo.com/html/"
BING_SEARCH_URL = "https://cn.bing.com/search"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)


class DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._capture_title = False
        self._capture_snippet = False
        self._current_title: list[str] = []
        self._current_snippet: list[str] = []
        self._current_href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        classes = set(attr.get("class", "").split())
        if tag == "a" and "result__a" in classes:
            self._capture_title = True
            self._current_title = []
            self._current_href = attr.get("href", "")
        elif "result__snippet" in classes and self.results:
            self._capture_snippet = True
            self._current_snippet = []

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._current_title.append(data)
        elif self._capture_snippet:
            self._current_snippet.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title:
            title = _clean_text("".join(self._current_title))
            if title and self._current_href:
                self.results.append({"title": title, "url": _normalize_ddg_url(self._current_href), "snippet": ""})
            self._capture_title = False
            self._current_title = []
            self._current_href = ""
        elif self._capture_snippet and tag in {"a", "div"}:
            snippet = _clean_text("".join(self._current_snippet))
            if snippet and self.results and not self.results[-1].get("snippet"):
                self.results[-1]["snippet"] = snippet
            self._capture_snippet = False
            self._current_snippet = []


class BingHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._in_result = False
        self._in_h2 = False
        self._in_caption = False
        self._capture_title = False
        self._capture_snippet = False
        self._current: dict[str, str] = {}
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        classes = set(attr.get("class", "").split())
        if tag == "li" and "b_algo" in classes:
            self._finish_current()
            self._in_result = True
            self._current = {}
            return
        if not self._in_result:
            return
        if tag == "h2":
            self._in_h2 = True
        elif tag == "a" and self._in_h2 and attr.get("href", "").startswith("http"):
            self._capture_title = True
            self._title_parts = []
            self._current["url"] = attr["href"]
        elif "b_caption" in classes:
            self._in_caption = True
        elif tag == "p" and self._in_caption:
            self._capture_snippet = True
            self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_parts.append(data)
        elif self._capture_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title:
            self._current["title"] = _clean_text("".join(self._title_parts))
            self._capture_title = False
            self._title_parts = []
        elif tag == "h2":
            self._in_h2 = False
        elif tag == "p" and self._capture_snippet:
            self._current["snippet"] = _clean_text("".join(self._snippet_parts))
            self._capture_snippet = False
            self._snippet_parts = []
        elif tag == "div" and self._in_caption:
            self._in_caption = False
        elif tag == "li" and self._in_result:
            self._finish_current()

    def close(self) -> None:
        self._finish_current()
        super().close()

    def _finish_current(self) -> None:
        title = self._current.get("title", "")
        url = self._current.get("url", "")
        if title and url:
            self.results.append({
                "title": title,
                "url": url,
                "snippet": self._current.get("snippet", ""),
            })
        self._in_result = False
        self._in_h2 = False
        self._in_caption = False
        self._capture_title = False
        self._capture_snippet = False
        self._current = {}
        self._title_parts = []
        self._snippet_parts = []


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(value or "").split())


def _normalize_ddg_url(value: str) -> str:
    if value.startswith("//"):
        value = f"https:{value}"
    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return unquote(query["uddg"][0])
    return value


def search_web(question: str, limit: int = 3) -> list[dict[str, Any]]:
    if not settings.web_search_enabled:
        return []
    firecrawl_results = _search_firecrawl(question, limit=limit)
    if firecrawl_results:
        return firecrawl_results
    query = f"{question} 地质灾害 标准 风险 预警"
    results = _search_duckduckgo(query, limit=limit)
    if results:
        return results
    return _search_bing(query, limit=limit)


def _search_firecrawl(question: str, limit: int) -> list[dict[str, Any]]:
    try:
        from app_server.services.firecrawl_service import FirecrawlError, firecrawl_configured, search_firecrawl
    except Exception as exc:
        logger.warning("firecrawl adapter unavailable: %s", exc)
        return []
    if not firecrawl_configured():
        return []
    try:
        return _dedupe_results(search_firecrawl(f"{question} 地质灾害 标准 风险 预警", limit=limit), limit)
    except FirecrawlError as exc:
        logger.warning("firecrawl web search failed: %s", exc)
        return []


def _search_duckduckgo(query: str, limit: int) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            DUCKDUCKGO_HTML_URL,
            params={"q": query},
            headers={"User-Agent": USER_AGENT},
            timeout=settings.web_search_timeout_seconds,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("duckduckgo search request failed: %s", exc)
        return []

    parser = DuckDuckGoHTMLParser()
    try:
        parser.feed(response.text)
    except Exception as exc:
        logger.warning("duckduckgo search parse failed: %s", exc)
        return []

    return _dedupe_results(parser.results, limit)


def _search_bing(query: str, limit: int) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            BING_SEARCH_URL,
            params={"q": query},
            headers={"User-Agent": USER_AGENT},
            timeout=settings.web_search_timeout_seconds,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("bing search request failed: %s", exc)
        return []

    parser = BingHTMLParser()
    try:
        parser.feed(response.text)
        parser.close()
    except Exception as exc:
        logger.warning("bing search parse failed: %s", exc)
        return []

    return _dedupe_results(parser.results, limit)


def _dedupe_results(raw_results: list[dict[str, str]], limit: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in raw_results:
        url = item.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        results.append({
            "title": item.get("title") or "联网搜索结果",
            "url": url,
            "snippet": item.get("snippet") or "",
            "source": urlparse(url).netloc or "web",
        })
        if len(results) >= limit:
            break
    return results


def search_url(question: str) -> str:
    return f"https://duckduckgo.com/?q={quote_plus(question)}"
