"""长沙市自然资源和规划局 parser.

Enhances the common parser with broader link patterns and Changsha-specific
keywords to handle sites that may have sparse or JS-light content.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urljoin

from .common import FOCUS_TERMS, RawItem, extract_title, parse_detail, strip_html


# Extended keyword set for Changsha natural resources — includes common
# government-site terms that may co-occur with geohazard articles.
CHANGSHA_EXTRA_TERMS = (
    "地灾",
    "隐患",
    "排查",
    "防治",
    "群测群防",
    "避让",
    "应急演练",
    "监测",
    "工程治理",
    "搬迁",
    "切坡建房",
    "矿山",
    "地质环境",
    "恢复治理",
)

ALL_TERMS = FOCUS_TERMS + CHANGSHA_EXTRA_TERMS


def parse_list(raw_html: str, base_url: str, limit: int = 20) -> list[RawItem]:
    items: list[RawItem] = []
    seen: set[str] = set()

    # Try multiple link patterns — government sites use various markup styles.
    link_patterns = [
        # Standard <a href> with inner text.
        r'(?is)<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<title>.*?)</a>',
        # <a> with title attribute (image links, etc.).
        r'(?is)<a[^>]+title=["\'](?P<title>[^"\']{4,})["\'][^>]*href=["\'](?P<href>[^"\']+)["\']',
        # <a> where text is in child span/div.
        r'(?is)<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>\s*<(?:span|div|p|em|strong)[^>]*>(?P<title>.*?)</(?:span|div|p|em|strong)>',
    ]

    for pattern in link_patterns:
        for match in re.finditer(pattern, raw_html or ""):
            title = strip_html(match.group("title"))
            if len(title) < 4:
                continue
            if not any(term in title for term in ALL_TERMS):
                continue
            url = urljoin(base_url, html.unescape(match.group("href")).strip())
            if url in seen:
                continue
            seen.add(url)
            items.append(RawItem(title=title[:120], url=url))
            if len(items) >= limit:
                break
        if items:
            break

    # Fallback: search for any linked text matching core disaster terms.
    if not items:
        for match in re.finditer(
            r'(?is)<a[^>]+href=["\'](?P<href>[^"\']{4,})["\'][^>]*>(?P<title>.*?)</a>',
            raw_html or "",
        ):
            title = strip_html(match.group("title"))
            if len(title) < 6:
                continue
            if not any(term in title for term in FOCUS_TERMS):
                continue
            url = urljoin(base_url, html.unescape(match.group("href")).strip())
            if url in seen:
                continue
            seen.add(url)
            items.append(RawItem(title=title[:120], url=url))
            if len(items) >= limit:
                break

    # Last resort: if page text itself contains disaster keywords, create one item.
    if not items:
        text = strip_html(raw_html)
        if any(term in text for term in ALL_TERMS):
            items.append(RawItem(title=extract_title(raw_html, base_url), url=base_url, summary=text[:240]))

    return items


# Re-export parse_detail from common.
__all__ = ["RawItem", "parse_detail", "parse_list"]
