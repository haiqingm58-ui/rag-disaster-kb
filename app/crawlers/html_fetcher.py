from __future__ import annotations

import logging
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

import requests


logger = logging.getLogger(__name__)


DEFAULT_USER_AGENT = "OpenGeoRiskCrawler/1.0 (+https://georisklab.com.cn; public disaster information monitor)"


@dataclass
class FetchOptions:
    timeout: int = 15
    retries: int = 2
    delay_seconds: float = 1.0
    user_agent: str = DEFAULT_USER_AGENT
    respect_robots: bool = True


class HtmlFetcher:
    def __init__(self, options: FetchOptions | None = None) -> None:
        self.options = options or FetchOptions()
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    def can_fetch(self, url: str) -> bool:
        if not self.options.respect_robots:
            return True
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        robots = self._robots_cache.get(base)
        if robots is None:
            robots = urllib.robotparser.RobotFileParser(f"{base}/robots.txt")
            try:
                robots.read()
            except Exception as exc:
                logger.info("robots unavailable url=%s error=%s", base, exc)
            self._robots_cache[base] = robots
        try:
            return robots.can_fetch(self.options.user_agent, url)
        except Exception:
            return True

    def fetch(self, url: str) -> str:
        if not self.can_fetch(url):
            raise RuntimeError(f"robots.txt 不允许采集: {url}")
        headers = {"User-Agent": self.options.user_agent}
        last_error: Exception | None = None
        for attempt in range(self.options.retries + 1):
            if attempt:
                time.sleep(self.options.delay_seconds * (2 ** (attempt - 1)))
            try:
                response = requests.get(url, headers=headers, timeout=self.options.timeout)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or response.encoding
                time.sleep(self.options.delay_seconds)
                return response.text
            except Exception as exc:
                last_error = exc
                logger.warning("fetch failed attempt=%s url=%s error=%s", attempt + 1, url, exc)
        raise RuntimeError(f"公开网页采集失败: {url}; {last_error}")
