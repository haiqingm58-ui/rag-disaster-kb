from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urljoin


FOCUS_TERMS = (
    "洪水",
    "山洪",
    "暴雨",
    "内涝",
    "水位",
    "雨量",
    "水库",
    "滑坡",
    "泥石流",
    "崩塌",
    "地质灾害",
    "风险预警",
    "防汛",
)


@dataclass
class RawItem:
    title: str
    url: str
    published_at: str = ""
    summary: str = ""


def strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw or "")
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def extract_title(raw: str, fallback: str = "") -> str:
    for pattern in (r"(?is)<h1[^>]*>(.*?)</h1>", r"(?is)<title[^>]*>(.*?)</title>"):
        match = re.search(pattern, raw or "")
        if match:
            title = strip_html(match.group(1))
            if title:
                return title
    return fallback or "未命名灾害信息"


def parse_list(raw_html: str, base_url: str, limit: int = 20) -> list[RawItem]:
    items: list[RawItem] = []
    seen: set[str] = set()
    for match in re.finditer(r'(?is)<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<title>.*?)</a>', raw_html or ""):
        title = strip_html(match.group("title"))
        if len(title) < 4 or not any(term in title for term in FOCUS_TERMS):
            continue
        url = urljoin(base_url, html.unescape(match.group("href")).strip())
        if url in seen:
            continue
        seen.add(url)
        items.append(RawItem(title=title[:120], url=url))
        if len(items) >= limit:
            break
    if not items:
        text = strip_html(raw_html)
        if any(term in text for term in FOCUS_TERMS):
            items.append(RawItem(title=extract_title(raw_html), url=base_url, summary=text[:240]))
    return items


def parse_detail(raw: str, item: RawItem, source_url: str) -> dict:
    text = strip_html(raw)
    title = extract_title(raw, item.title)
    return {
        "title": title,
        "summary": item.summary or text[:240],
        "raw_text": text,
        "published_at": item.published_at,
        "original_url": item.url or source_url,
        "confidence": "official_news",
    }
