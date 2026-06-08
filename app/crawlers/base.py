from __future__ import annotations

import importlib
import logging
from types import ModuleType
from typing import Any

from app.crawlers.dedupe import DisasterEventStore
from app.crawlers.html_fetcher import HtmlFetcher
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
        html = self.fetcher.fetch(self.source.url)
        return self.parser.parse_list(html, self.source.url)

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
        result = {
            "source_id": self.source.source_id,
            "source_name": self.source.source_name,
            "total_items": len(items),
            "saved": 0,
            "new_events": 0,
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
            except Exception as exc:
                logger.exception("crawler item failed source=%s item=%s", self.source.source_id, item)
                result["errors"].append({"title": getattr(item, "title", ""), "url": getattr(item, "url", ""), "error": str(exc)})
        return result
