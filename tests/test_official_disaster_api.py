from app.crawlers.dedupe import DisasterEventStore
from app.models.disaster_event import DisasterEvent
from app_server.main import app
from fastapi.testclient import TestClient


def test_geojson_output_format(tmp_path):
    store = DisasterEventStore(tmp_path / "events.sqlite3")
    store.upsert(
        DisasterEvent(
            source_id="hunan_water",
            source_name="湖南省水利厅",
            source_level="province",
            source_url="https://example.org",
            original_url="https://example.org/a",
            title="长沙市洪水预警",
            disaster_type="flood",
            warning_level="orange",
            city="长沙市",
            lat=28.2282,
            lng=112.9388,
            geo_precision="city",
            published_at="2026-06-08 12:00:00",
            content_hash="abc",
        )
    )

    data = store.geojson(limit=10)

    assert data["type"] == "FeatureCollection"
    assert data["features"][0]["geometry"]["coordinates"] == [112.9388, 28.2282]
    assert data["features"][0]["properties"]["warning_level"] == "orange"


def test_latest_api_returns_expected_fields(monkeypatch):
    from app_server.api import disaster_events

    monkeypatch.setattr(
        disaster_events,
        "latest_official_events",
        lambda **kwargs: [{"id": 1, "title": "长沙市洪水预警", "source_id": "hunan_water"}],
    )

    response = TestClient(app).get("/api/disaster-events/latest")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["events"][0]["source_id"] == "hunan_water"


def test_geojson_api_returns_feature_collection(monkeypatch):
    from app_server.api import disaster_events

    monkeypatch.setattr(disaster_events, "official_events_geojson", lambda **kwargs: {"type": "FeatureCollection", "features": []})

    response = TestClient(app).get("/api/disaster-events/geojson")

    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"
