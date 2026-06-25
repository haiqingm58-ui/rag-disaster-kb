from app.crawlers.normalize import detect_disaster_type, detect_warning_level, normalize_event
from app.crawlers.source_config import DisasterSource


def source():
    return DisasterSource(
        source_id="hunan_natural_resource",
        source_name="湖南省自然资源厅",
        level="province",
        disaster_types=["geological_disaster"],
        url="https://example.org",
        enabled=True,
        fetch_interval_minutes=60,
        parser_type="generic_html",
    )


def test_detect_disaster_type_and_warning_level():
    text = "长沙县发布地质灾害气象风险黄色预警，需关注滑坡、泥石流。"

    assert detect_disaster_type(text) == "debris_flow"
    assert detect_warning_level(text) == "yellow"


def test_normalize_event_adds_geo_and_hash():
    event = normalize_event(
        source(),
        {
            "title": "湖南省地质灾害气象风险黄色预警",
            "raw_text": "2026年6月8日，长沙县、浏阳市有滑坡和泥石流风险。",
            "original_url": "https://example.org/a.html",
        },
    )

    assert event.source_id == "hunan_natural_resource"
    assert event.warning_level == "yellow"
    assert event.city == "长沙市"
    assert event.content_hash
    assert event.original_url.endswith("a.html")
