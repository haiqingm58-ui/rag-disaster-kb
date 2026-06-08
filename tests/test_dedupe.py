from pathlib import Path

from app.crawlers.dedupe import DisasterEventStore, content_hash
from app.models.disaster_event import DisasterEvent


def event(title="长沙县山洪预警", text="长沙县发布山洪蓝色预警。"):
    hash_value = content_hash("test_source", title, "2026-06-08 10:00:00", text)
    return DisasterEvent(
        source_id="test_source",
        source_name="测试源",
        source_level="city",
        source_url="https://example.org",
        original_url="https://example.org/a",
        title=title,
        raw_text=text,
        disaster_type="mountain_flood",
        warning_level="blue",
        city="长沙市",
        county="长沙县",
        lat=28.246,
        lng=113.081,
        geo_precision="county",
        published_at="2026-06-08 10:00:00",
        content_hash=hash_value,
    )


def test_content_hash_is_stable():
    a = content_hash("s", "t", "2026-06-08", " 内容  A ")
    b = content_hash("s", "t", "2026-06-08", "内容 A")

    assert a == b


def test_store_upsert_updates_same_warning(tmp_path: Path):
    store = DisasterEventStore(tmp_path / "events.sqlite3")
    row_id, created = store.upsert(event())
    assert created

    updated = event(text="长沙县发布山洪蓝色预警，风险范围扩大。")
    row_id_2, created_2 = store.upsert(updated)

    rows = store.latest(limit=10)
    assert row_id_2 == row_id
    assert not created_2
    assert len(rows) == 1
    assert "扩大" in rows[0]["raw_text"]
