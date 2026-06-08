from __future__ import annotations

import importlib
import logging
from types import ModuleType
from typing import Any

from app.crawlers.dedupe import DisasterEventStore
from app.crawlers.html_fetcher import HtmlFetcher, SkippedError
from app.crawlers.normalize import normalize_event
from app.crawlers.pdf_fetcher import PdfFetcher
from app.crawlers.source_config import DisasterSource
from app.models.disaster_event import DisasterEvent


logger = logging.getLogger(__name__)


def load_parser(parser_type: str) -> ModuleType:
    safe_name = "".join(ch for ch in parser_type if ch.isalnum() or ch == "_")
    try:
        return importlib.import_module(f"app.crawlers.parsers.{safe_name}")
    except ModuleNotFoundError:
        return importlib.import_module("app.crawlers.parsers.generic_html")


class BaseDisasterCrawler:
    def __init__(
        self,
        source: DisasterSource,
        fetcher: HtmlFetcher | None = None,
        pdf_fetcher: PdfFetcher | None = None,
        store: DisasterEventStore | None = None,
    ) -> None:
        self.source = source
        self.fetcher = fetcher or HtmlFetcher()
        self.pdf_fetcher = pdf_fetcher or PdfFetcher()
        self.store = store or DisasterEventStore()
        self.parser = load_parser(source.parser_type)

    def fetch_list(self) -> list[Any]:
        urls = self.source.urls if self.source.urls else [self.source.url]
        all_items: list[Any] = []
        seen_urls: set[str] = set()
        for url in urls:
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            try:
                html = self.fetcher.fetch(url)
                items = self.parser.parse_list(html, url)
                all_items.extend(items)
                if items:
                    logger.info("fetched %s items from url=%s", len(items), url)
            except SkippedError:
                # URL is external/non-gov — skip the URL itself, not the whole source.
                logger.info("skipping URL (external/non-gov): %s", url)
                continue
            except Exception as exc:
                logger.warning("failed to fetch list from url=%s error=%s", url, exc)
                continue
        return all_items

    def fetch_detail(self, item: Any) -> str:
        url = getattr(item, "url", "") or self.source.url
        if url.lower().split("?", 1)[0].endswith(".pdf"):
            return self.pdf_fetcher.fetch_pdf_text(url)
        return self.fetcher.fetch(url)

    def parse(self, raw_html_or_text: str, item: Any) -> DisasterEvent:
        raw = self.parser.parse_detail(raw_html_or_text, item, self.source.url)
        return self.normalize(raw)

    def normalize(self, event: dict[str, Any]) -> DisasterEvent:
        return normalize_event(self.source, event)

    def save(self, event: DisasterEvent) -> tuple[int, bool]:
        return self.store.upsert(event)

    def run(self, limit: int | None = None) -> dict[str, Any]:
        items = self.fetch_list()
        if limit:
            items = items[:limit]
        result: dict[str, Any] = {
            "source_id": self.source.source_id,
            "source_name": self.source.source_name,
            "total_items": len(items),
            "saved": 0,
            "new_events": 0,
            "skipped": [],
            "warnings": [],
            "errors": [],
        }
        for item in items:
            try:
                raw = self.fetch_detail(item)
                event = self.parse(raw, item)
                _, created = self.save(event)
                result["saved"] += 1
                if created:
                    result["new_events"] += 1
            except SkippedError as exc:
                logger.info("crawler item skipped source=%s title=%s reason=%s", self.source.source_id, getattr(item, "title", ""), exc)
                result["skipped"].append({
                    "title": getattr(item, "title", ""),
                    "url": getattr(item, "url", ""),
                    "reason": str(exc),
                })
            except Exception as exc:
                logger.exception("crawler item failed source=%s item=%s", self.source.source_id, item)
                result["errors"].append({
                    "title": getattr(item, "title", ""),
                    "url": getattr(item, "url", ""),
                    "error": str(exc),
                })
        # Collect fetcher warnings.
        if self.fetcher._warnings:
            result["warnings"] = self.fetcher._warnings[:]
            self.fetcher._warnings.clear()
        # Add diagnostics when total_items=0.
        if not items:
            result["diagnostics"] = self._diagnostics()
        return result

    def _diagnostics(self) -> dict[str, Any]:
        """Gather diagnostics when no items are found for a source."""
        import re

        import requests
        from app.crawlers.parsers.common import FOCUS_TERMS, extract_title, strip_html

        urls_to_test = self.source.urls if self.source.urls else [self.source.url]
        diagnostics: dict[str, Any] = {
            "source_id": self.source.source_id,
            "tested_urls": urls_to_test,
            "http_status": None,
            "html_title": "",
            "matched_links_count": 0,
            "keyword_matched_count": 0,
            "parser_name": self.source.parser_type,
            "possible_reason": "",
        }
        for url in urls_to_test:
            if not url:
                continue
            try:
                resp = requests.get(
                    url,
                    headers={
                        "User-Agent": "OpenGeoRiskCrawler/1.0",
                        "Accept": "text/html",
                        "Accept-Language": "zh-CN,zh;q=0.9",
                    },
                    timeout=15,
                )
                diagnostics["http_status"] = resp.status_code
                title = extract_title(resp.text, "")
                if title:
                    diagnostics["html_title"] = title
                links = re.findall(r'(?is)<a[^>]+href=["\'][^"\']+["\'][^>]*>(.*?)</a>', resp.text)
                diagnostics["matched_links_count"] += len(links)
                keyword_matched = sum(
                    1 for link_text in links if any(term in strip_html(link_text) for term in FOCUS_TERMS)
                )
                diagnostics["keyword_matched_count"] += keyword_matched
                if resp.status_code == 200 and keyword_matched > 0:
                    # This URL has matching content — don't try more URLs for diag.
                    break
            except Exception as exc:
                logger.warning("diagnostics request failed url=%s error=%s", url, exc)
                continue

        if diagnostics["http_status"] is None:
            diagnostics["possible_reason"] = "所有 URL 请求失败"
        elif diagnostics["http_status"] != 200:
            diagnostics["possible_reason"] = f"HTTP {diagnostics['http_status']}"
        elif diagnostics["keyword_matched_count"] == 0:
            diagnostics["possible_reason"] = (
                "页面链接中未匹配到地灾相关关键词，"
                "可能该栏目不包含地灾信息或页面结构为 JS 动态渲染"
            )
        else:
            diagnostics["possible_reason"] = (
                "页面有匹配关键词但 parser 未提取到条目，需检查 parser 逻辑"
            )
        return diagnostics
