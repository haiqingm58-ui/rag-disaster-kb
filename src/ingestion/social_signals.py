"""Compliant public social/news signal adapters.

This module intentionally avoids login bypassing, anti-scraping workarounds,
captcha handling, bulk downloads, and private content collection.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import CACHE_DIR, YOUTUBE_API_KEY

SOCIAL_CACHE_FILE = CACHE_DIR / "social_signals.json"
DEFAULT_KEYWORDS = ["地震", "震感", "洪水", "暴雨", "山体滑坡", "泥石流", "台风", "山火", "森林火灾"]


def _save_signals(signals: list[dict]) -> None:
    SOCIAL_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SOCIAL_CACHE_FILE.write_text(json.dumps(signals, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cached_signals() -> list[dict]:
    try:
        return json.loads(SOCIAL_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def search_youtube_public_metadata(keyword: str, max_results: int = 5) -> list[dict]:
    if not YOUTUBE_API_KEY:
        raise ValueError("未配置 YOUTUBE_API_KEY，无法使用 YouTube Data API。")

    resp = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "maxResults": max_results,
            "order": "date",
            "key": YOUTUBE_API_KEY,
        },
        timeout=12,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    signals = []
    for item in items:
        snippet = item.get("snippet", {})
        video_id = item.get("id", {}).get("videoId", "")
        signals.append({
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "published_at": snippet.get("publishedAt", ""),
            "platform": "YouTube",
            "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
            "channel": snippet.get("channelTitle", ""),
            "keyword": keyword,
            "confidence_level": "unverified",
            "verification_status": "未核验",
            "location_text": "",
            "source_type": "public_video_metadata",
            "cached_at": datetime.now(timezone.utc).isoformat(),
        })
    return signals


def search_public_signals(keywords: list[str] | None = None, max_results: int = 5) -> list[dict]:
    """Search public metadata using configured official APIs only."""
    keywords = keywords or DEFAULT_KEYWORDS
    all_signals: list[dict] = []
    for keyword in keywords:
        all_signals.extend(search_youtube_public_metadata(keyword, max_results=max_results))
    _save_signals(all_signals)
    return all_signals
