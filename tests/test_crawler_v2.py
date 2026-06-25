"""Tests for crawler improvements: skip handling, retry, diagnostics, geo, stats."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.crawlers.base import BaseDisasterCrawler
from app.crawlers.dedupe import DisasterEventStore
from app.crawlers.geo_extract import extract_geo
from app.crawlers.html_fetcher import FetchOptions, HtmlFetcher, SkippedError, is_skippable_url
from app.crawlers.parsers.changsha_natural_resource import parse_list as changsha_parse_list
from app.crawlers.parsers.common import RawItem
from app.crawlers.scheduler import compute_stats
from app.crawlers.source_config import DisasterSource
from app.models.disaster_event import DisasterEvent


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_source(source_id="test_source", url="https://example.org", urls=None):
    return DisasterSource(
        source_id=source_id,
        source_name="测试源",
        level="city",
        disaster_types=["flood"],
        url=url,
        enabled=True,
        fetch_interval_minutes=60,
        parser_type="generic_html",
        urls=urls or [],
    )


# ---------------------------------------------------------------------------
# 1. WeChat / external URL → skipped, not error
# ---------------------------------------------------------------------------

class TestSkipExternalUrls:
    def test_weixin_mp_is_skippable(self):
        should, reason = is_skippable_url("https://mp.weixin.qq.com/s/Fa3er_uChXvBQmAHygvg1A")
        assert should
        assert "微信" in reason

    def test_weixin_qq_is_skippable(self):
        should, reason = is_skippable_url("https://weixin.qq.com/something")
        assert should
        assert "微信" in reason

    def test_gov_cn_is_not_skippable(self):
        should, _ = is_skippable_url("http://slt.hunan.gov.cn/xxx")
        assert not should

    def test_gov_cn_subdomain_is_not_skippable(self):
        should, _ = is_skippable_url("http://zygh.changsha.gov.cn/xxx")
        assert not should

    def test_non_gov_is_skippable(self):
        should, reason = is_skippable_url("https://www.example.com/news")
        assert should
        assert "非政府外链" in reason

    def test_fetcher_raises_skipped_error_for_weixin(self):
        fetcher = HtmlFetcher(FetchOptions(respect_robots=False))
        with pytest.raises(SkippedError):
            fetcher.fetch("https://mp.weixin.qq.com/s/abc123")


# ---------------------------------------------------------------------------
# 2. robots.txt disallow → skipped (not crash)
# ---------------------------------------------------------------------------

class TestRobotsSkip:
    def test_robots_disallow_becomes_skipped(self, tmp_path: Path):
        """When can_fetch returns False, fetch raises SkippedError."""
        fetcher = HtmlFetcher(FetchOptions(respect_robots=True))
        # Use a .gov.cn URL so the skip-domain classifier doesn't interfere.
        with patch.object(fetcher, "can_fetch", return_value=False):
            with pytest.raises(SkippedError, match="robots.txt"):
                fetcher.fetch("http://test.hunan.gov.cn/disallowed")

    def test_robots_disallowed_item_goes_to_skipped_in_run(self, tmp_path: Path):
        """Verify that a disallowed URL goes to skipped[], not errors[]. """
        from app.crawlers.html_fetcher import HtmlFetcher as HF

        store = DisasterEventStore(tmp_path / "events.sqlite3")
        source = _make_source(url="http://test.hunan.gov.cn")

        # Use a custom fetcher instance that skips the detail URL.
        fetcher = HtmlFetcher(FetchOptions(respect_robots=False))
        call_count = [0]

        def side_effect(url):
            call_count[0] += 1
            if call_count[0] == 1:
                # fetch_list: return HTML with a disaster-related link.
                return '<html><a href="http://test.hunan.gov.cn/test">防汛通知</a></html>'
            # fetch_detail: simulate robots disallow.
            raise SkippedError("robots.txt 不允许采集: http://test.hunan.gov.cn/test")

        fetcher.fetch = MagicMock(side_effect=side_effect)

        crawler = BaseDisasterCrawler(source, fetcher=fetcher, store=store)
        result = crawler.run()
        assert len(result["skipped"]) == 1, f"Expected 1 skipped, got {result['skipped']}, errors={result['errors']}"
        assert "robots.txt" in result["skipped"][0]["reason"]
        assert len(result["errors"]) == 0


# ---------------------------------------------------------------------------
# 3. IncompleteRead retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:
    def test_fetcher_retries_on_transient_errors(self):
        """Fetcher retries on transient errors, then succeeds."""
        from requests.exceptions import ConnectionError

        fetcher = HtmlFetcher(FetchOptions(retries=2, delay_seconds=0.01, respect_robots=False))
        call_count = [0]

        def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("transient failure")
            resp = MagicMock()
            resp.text = "<html>ok</html>"
            resp.encoding = "utf-8"
            resp.apparent_encoding = "utf-8"
            resp.raise_for_status = MagicMock()
            return resp

        # Use .gov.cn URL so the skip-domain classifier doesn't fire.
        with patch("requests.get", side_effect=mock_get):
            result = fetcher.fetch("http://test.hunan.gov.cn/page")
            assert result == "<html>ok</html>"
            assert call_count[0] == 3

    def test_fetcher_gives_up_after_max_retries(self):
        """Fetcher raises RuntimeError after exhausting retries."""
        from requests.exceptions import Timeout

        fetcher = HtmlFetcher(FetchOptions(retries=1, delay_seconds=0.01, respect_robots=False))

        with patch("requests.get", side_effect=Timeout("timeout")):
            with pytest.raises(RuntimeError, match="公开网页采集失败"):
                fetcher.fetch("http://test.hunan.gov.cn/page")


# ---------------------------------------------------------------------------
# 4. Changsha natural resource parser with sample HTML
# ---------------------------------------------------------------------------

class TestChangshaParser:
    def test_parse_sample_html_finds_disaster_links(self):
        html = """
        <html><body>
          <ul>
            <li><a href="/zwgk/dzzh/2026/001.html">长沙市地质灾害气象风险预警通知</a></li>
            <li><a href="/tzgg/2026/002.html">关于开展汛前地质灾害排查工作的通知</a></li>
            <li><a href="/xwzx/2026/003.html">我局召开地质灾害防治工作部署会</a></li>
            <li><a href="/other/2026/004.html">规划公告</a></li>
        </body></html>
        """
        items = changsha_parse_list(html, "http://zygh.changsha.gov.cn")
        assert len(items) >= 3, f"Expected at least 3 disaster links, got {len(items)}"

    def test_parse_sample_html_no_disaster_links_returns_empty(self):
        html = """
        <html><body>
          <ul>
            <li><a href="/gh/001.html">城市规划公示</a></li>
            <li><a href="/td/002.html">土地出让公告</a></li>
        </body></html>
        """
        items = changsha_parse_list(html, "http://zygh.changsha.gov.cn")
        assert len(items) == 0

    def test_parse_changsha_extra_keywords(self):
        """Verify Changsha-specific keywords like 切坡建房 match."""
        html = """
        <html><body>
          <a href="/zwgk/001.html">关于切坡建房风险排查整治工作的通知</a>
          <a href="/zwgk/002.html">矿山地质环境恢复治理验收公示</a>
        </body></html>
        """
        items = changsha_parse_list(html, "http://zygh.changsha.gov.cn")
        assert len(items) == 2


# ---------------------------------------------------------------------------
# 5. Diagnostics when total_items=0
# ---------------------------------------------------------------------------

class TestDiagnostics:
    def test_empty_source_produces_diagnostics(self, tmp_path: Path):
        store = DisasterEventStore(tmp_path / "events.sqlite3")
        source = _make_source(url="https://example.org/empty")

        fetcher = HtmlFetcher(FetchOptions(respect_robots=False))
        # Simulate a page with no disaster links.
        fetcher.fetch = MagicMock(return_value="<html><body><a href='/a'>普通新闻</a></body></html>")

        parser = MagicMock()
        parser.parse_list.return_value = []

        crawler = BaseDisasterCrawler(source, fetcher=fetcher, store=store)
        crawler.parser = parser

        result = crawler.run()
        assert result["total_items"] == 0
        assert "diagnostics" in result
        assert result["diagnostics"]["source_id"] == "test_source"
        assert "tested_urls" in result["diagnostics"]


# ---------------------------------------------------------------------------
# 6. GeoJSON excludes features without coordinates
# ---------------------------------------------------------------------------

class TestGeojsonNoCoord:
    def test_geojson_excludes_null_coordinates(self, tmp_path: Path):
        store = DisasterEventStore(tmp_path / "events.sqlite3")
        store.upsert(DisasterEvent(
            source_id="test", source_name="测试", source_level="city",
            source_url="https://x", original_url="https://x/a",
            title="有坐标的灾害", disaster_type="flood",
            lat=28.2282, lng=112.9388, geo_precision="city",
            published_at="2026-06-08 10:00:00", content_hash="abc",
        ))
        store.upsert(DisasterEvent(
            source_id="test", source_name="测试", source_level="city",
            source_url="https://x", original_url="https://x/b",
            title="无坐标的灾害", disaster_type="flood",
            lat=None, lng=None, geo_precision="unknown",
            published_at="2026-06-08 11:00:00", content_hash="def",
        ))

        data = store.geojson(limit=10)
        assert len(data["features"]) == 1
        assert data["features"][0]["properties"]["title"] == "有坐标的灾害"

    def test_geojson_includes_geo_precision(self, tmp_path: Path):
        store = DisasterEventStore(tmp_path / "events.sqlite3")
        store.upsert(DisasterEvent(
            source_id="test", source_name="测试", source_level="city",
            source_url="https://x", original_url="https://x/a",
            title="灾害", disaster_type="flood",
            lat=28.2282, lng=112.9388, geo_precision="county",
            published_at="2026-06-08 10:00:00", content_hash="ghi",
        ))

        data = store.geojson(limit=10)
        assert data["features"][0]["properties"]["geo_precision"] == "county"


# ---------------------------------------------------------------------------
# 7. geo_precision field after fix (unknown instead of default)
# ---------------------------------------------------------------------------

class TestGeoPrecision:
    def test_unknown_location_returns_none_coords(self):
        geo = extract_geo("某地发生了一起地质灾害事件，但未提及具体位置信息。")
        assert geo["lat"] is None
        assert geo["lng"] is None
        assert geo["geo_precision"] == "unknown"

    def test_changsha_text_returns_city_coords(self):
        geo = extract_geo("长沙市发布地质灾害气象风险预警。")
        assert geo["lat"] is not None
        assert geo["lng"] is not None
        assert geo["geo_precision"] == "city"
        assert geo["city"] == "长沙市"


# ---------------------------------------------------------------------------
# 8. --stats command runs and produces expected structure
# ---------------------------------------------------------------------------

class TestStatsCommand:
    def test_stats_returns_expected_keys(self, tmp_path: Path):
        db_path = tmp_path / "events.sqlite3"
        store = DisasterEventStore(db_path)
        store.upsert(DisasterEvent(
            source_id="test_source", source_name="测试", source_level="city",
            source_url="https://x", original_url="https://x/a",
            title="长沙市洪水预警", disaster_type="flood", warning_level="orange",
            city="长沙市", lat=28.2282, lng=112.9388, geo_precision="city",
            published_at="2026-06-08 12:00:00", content_hash="xyz",
        ))

        # Override the store to use our temp db — must set row_factory for dict access.
        def _connect(self):
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            return conn

        with patch.object(DisasterEventStore, "connect", _connect):
            stats = compute_stats()
            assert "total_events" in stats
            assert "by_source_id" in stats
            assert "by_disaster_type" in stats
            assert "by_warning_level" in stats
            assert "with_lat_lng" in stats
            assert "geo_precision_distribution" in stats
            assert "recent_24h" in stats
            assert "recent_7d" in stats
            assert "anomalies" in stats
            assert stats["total_events"] > 0

    def test_stats_detects_anomalies(self, tmp_path: Path):
        db_path = tmp_path / "events.sqlite3"
        store = DisasterEventStore(db_path)
        store.upsert(DisasterEvent(
            source_id="test_source", source_name="测试", source_level="city",
            source_url="https://x", original_url="",
            title="", disaster_type="invalid_type", warning_level="pink",
            lat=None, lng=None, geo_precision="exact_point",
            published_at="2026-06-08 12:00:00", content_hash="anom",
        ))

        def _connect(self):
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            return conn

        with patch.object(DisasterEventStore, "connect", _connect):
            stats = compute_stats()
            anomaly_types = {a["type"] for a in stats["anomalies"]}
            assert "empty_title" in anomaly_types
            assert "empty_original_url" in anomaly_types
            assert "null_geo_exact_point" in anomaly_types
            assert "invalid_warning_level" in anomaly_types
            assert "invalid_disaster_type" in anomaly_types

    def test_stats_handles_empty_db(self):
        """Stats should not crash on empty database."""
        stats = compute_stats()
        assert stats["total_events"] >= 0
        assert isinstance(stats["by_source_id"], dict)


# ---------------------------------------------------------------------------
# 9. CLI --source with skipped items in output
# ---------------------------------------------------------------------------

class TestCliSkippedOutput:
    def test_run_result_includes_skipped_field(self, tmp_path: Path):
        store = DisasterEventStore(tmp_path / "events.sqlite3")
        source = _make_source()

        fetcher = HtmlFetcher(FetchOptions(respect_robots=False))
        fetcher.fetch = MagicMock(side_effect=[
            # First call (fetch_list) succeeds
            "<html><a href='/test'>防汛通知</a></html>",
            # Second call (fetch_detail) gets skipped
            SkippedError("微信外链自动跳过"),
        ])

        parser = MagicMock()
        parser.parse_list.return_value = [RawItem(title="防汛通知", url="https://mp.weixin.qq.com/s/test")]

        crawler = BaseDisasterCrawler(source, fetcher=fetcher, store=store)
        crawler.parser = parser

        result = crawler.run()
        assert "skipped" in result
        assert len(result["skipped"]) == 1
        assert result["skipped"][0]["reason"] == "微信外链自动跳过"


# ---------------------------------------------------------------------------
# 10. to_realtime_event includes geo_precision and confidence
# ---------------------------------------------------------------------------

class TestRealtimeEvent:
    def test_realtime_event_includes_geo_fields(self):
        event = DisasterEvent(
            source_id="test", source_name="测试", source_level="city",
            source_url="https://x", original_url="https://x/a",
            title="测试", disaster_type="flood",
            lat=28.2282, lng=112.9388, geo_precision="city",
            confidence="official_news",
            published_at="2026-06-08 10:00:00", content_hash="test",
        )
        rt = event.to_realtime_event()
        assert rt["geo_precision"] == "city"
        assert rt["confidence"] == "official_news"
