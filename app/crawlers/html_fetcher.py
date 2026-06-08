from __future__ import annotations

import logging
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from requests.exceptions import ChunkedEncodingError, ConnectionError, ReadTimeout, Timeout

try:
    from urllib3.exceptions import IncompleteRead as IncompleteReadError
except ImportError:
    try:
        from http.client import IncompleteRead as IncompleteReadError
    except ImportError:
        IncompleteReadError = Exception  # fallback

# Exception types that are worth retrying (transient network issues).
RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    IncompleteReadError,
    ChunkedEncodingError,
    ConnectionError,
    ReadTimeout,
    Timeout,
    OSError,
)


logger = logging.getLogger(__name__)


DEFAULT_USER_AGENT = "OpenGeoRiskCrawler/1.0 (+https://georisklab.com.cn; public disaster information monitor)"


# Domains that are external links and should be silently skipped.
SKIP_DOMAINS: tuple[str, ...] = (
    "mp.weixin.qq.com",
    "weixin.qq.com",
)

# Domain suffixes that indicate non-government external links.
SKIP_SUFFIXES: tuple[str, ...] = (
    ".weibo.com",
    ".weibo.cn",
    ".tieba.baidu.com",
    ".zhihu.com",
    ".douyin.com",
    ".kuaishou.com",
    ".bilibili.com",
    ".xiaohongshu.com",
)

# Known government domain suffixes (Chinese government sites).
GOV_SUFFIXES: tuple[str, ...] = (
    ".gov.cn",
    ".gov.cn/",
    ".mwr.cn",
    ".nmc.cn",
    ".cigem.cn",
    ".cgs.gov.cn",
    ".ndrcc.org.cn",
    ".emerinfo.cn",
    ".cma.cn",
    ".cma.gov.cn",
)


class SkippedError(RuntimeError):
    """Raised when a URL should be silently skipped rather than treated as an error."""


def _hostname_matches(url: str, domains: tuple[str, ...]) -> bool:
    host = urlparse(url).hostname or ""
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _hostname_ends_with(url: str, suffixes: tuple[str, ...]) -> bool:
    host = urlparse(url).hostname or ""
    return any(host.endswith(suffix) for suffix in suffixes)


def is_skippable_url(url: str) -> tuple[bool, str]:
    """Check whether a URL should be silently skipped (external / non-government).

    Returns (should_skip, reason).
    """
    host = (urlparse(url).hostname or "").lower()

    if _hostname_matches(url, SKIP_DOMAINS):
        return True, "微信外链自动跳过"

    if _hostname_ends_with(url, SKIP_SUFFIXES):
        return True, f"社交媒体外链自动跳过: {host}"

    # If the URL is clearly not a government site, flag it.
    if not _hostname_ends_with(url, GOV_SUFFIXES) and host:
        # Allow gov.cn subdomains that aren't in GOV_SUFFIXES.
        if host.endswith(".gov.cn") or host in {"gov.cn", "www.gov.cn"}:
            return False, ""
        return True, f"非政府外链自动跳过: {host}"

    return False, ""


@dataclass
class FetchOptions:
    timeout: int = 15
    retries: int = 3
    delay_seconds: float = 1.0
    user_agent: str = DEFAULT_USER_AGENT
    respect_robots: bool = True


class HtmlFetcher:
    def __init__(self, options: FetchOptions | None = None) -> None:
        self.options = options or FetchOptions()
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._warnings: list[str] = []

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
        # Check skip-first: if the URL is an external/non-government link, skip silently.
        should_skip, skip_reason = is_skippable_url(url)
        if should_skip:
            raise SkippedError(skip_reason)

        if not self.can_fetch(url):
            raise SkippedError(f"robots.txt 不允许采集: {url}")

        headers = {
            "User-Agent": self.options.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "close",
            "Accept-Encoding": "identity",
        }

        last_error: Exception | None = None
        for attempt in range(self.options.retries + 1):
            if attempt:
                backoff = self.options.delay_seconds * (2 ** (attempt - 1))
                time.sleep(backoff)
            try:
                response = requests.get(url, headers=headers, timeout=self.options.timeout)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or response.encoding
                time.sleep(self.options.delay_seconds)
                if attempt > 0:
                    self._warnings.append(f"fetch retry succeeded on attempt={attempt + 1} url={url}")
                return response.text
            except RETRYABLE_EXCEPTIONS as exc:
                last_error = exc
                logger.warning("fetch transient error attempt=%s/%s url=%s error=%s", attempt + 1, self.options.retries + 1, url, exc)
            except RuntimeError:
                # SkippedError: re-raise immediately, no retry.
                raise
            except Exception as exc:
                # Non-retryable errors (HTTP 4xx, etc.): don't retry.
                raise RuntimeError(f"公开网页采集失败: {url}; {exc}") from exc

        raise RuntimeError(f"公开网页采集失败: {url}; {last_error}")
