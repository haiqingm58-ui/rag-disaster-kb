from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from config import DATA_DIR
from app.models.disaster_event import DisasterEvent, now_text


EVENT_DB_PATH = DATA_DIR / "disaster_events.sqlite3"


EVENT_FIELDS = [
    "source_id",
    "source_name",
    "source_level",
    "source_url",
    "original_url",
    "title",
    "summary",
    "raw_text",
    "disaster_type",
    "warning_type",
    "warning_level",
    "province",
    "city",
    "county",
    "town",
    "address_text",
    "river_name",
    "station_name",
    "lat",
    "lng",
    "geo_precision",
    "start_time",
    "end_time",
    "published_at",
    "collected_at",
    "updated_at",
    "status",
    "confidence",
    "content_hash",
    "is_active",
]


def normalized_text(value: str) -> str:
    return " ".join((value or "").split())


def content_hash(source_id: str, title: str, published_at: str, text: str) -> str:
    raw = f"{source_id}|{title}|{published_at}|{normalized_text(text)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def event_key(event: DisasterEvent) -> str:
    raw = f"{event.source_id}|{event.title}|{event.published_at}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DisasterEventStore:
    def __init__(self, path: Path = EVENT_DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS disaster_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_key TEXT UNIQUE,
                  source_id TEXT NOT NULL,
                  source_name TEXT NOT NULL,
                  source_level TEXT,
                  source_url TEXT,
                  original_url TEXT,
                  title TEXT NOT NULL,
                  summary TEXT,
                  raw_text TEXT,
                  disaster_type TEXT,
                  warning_type TEXT,
                  warning_level TEXT,
                  province TEXT,
                  city TEXT,
                  county TEXT,
                  town TEXT,
                  address_text TEXT,
                  river_name TEXT,
                  station_name TEXT,
                  lat REAL,
                  lng REAL,
                  geo_precision TEXT,
                  start_time TEXT,
                  end_time TEXT,
                  published_at TEXT,
                  collected_at TEXT,
                  updated_at TEXT,
                  status TEXT,
                  confidence TEXT,
                  content_hash TEXT UNIQUE,
                  is_active INTEGER DEFAULT 1
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_disaster_events_source ON disaster_events(source_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_disaster_events_time ON disaster_events(published_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_disaster_events_type ON disaster_events(disaster_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_disaster_events_geo ON disaster_events(lat, lng)")

    def upsert(self, event: DisasterEvent) -> tuple[int, bool]:
        if not event.content_hash:
            event.content_hash = content_hash(event.source_id, event.title, event.published_at, event.raw_text or event.summary)
        key = event_key(event)
        event.updated_at = now_text()
        values = event.to_dict()
        values["is_active"] = 1 if event.is_active else 0
        columns = ", ".join(["event_key", *EVENT_FIELDS])
        placeholders = ", ".join([f":{name}" for name in ["event_key", *EVENT_FIELDS]])
        update_columns = [field for field in EVENT_FIELDS if field not in {"collected_at"}]
        updates = ", ".join([f"{field}=excluded.{field}" for field in update_columns])
        payload = {"event_key": key, **values}
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id, content_hash FROM disaster_events WHERE event_key = ? OR content_hash = ?",
                (key, event.content_hash),
            ).fetchone()
            if existing:
                set_clause = ", ".join([f"{field}=:{field}" for field in update_columns])
                conn.execute(
                    f"UPDATE disaster_events SET event_key=:event_key, {set_clause} WHERE id=:id",
                    {**payload, "id": existing["id"]},
                )
                row_id = int(existing["id"])
            else:
                conn.execute(f"INSERT INTO disaster_events ({columns}) VALUES ({placeholders})", payload)
                row_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        return row_id, existing is None

    def latest(self, **filters: Any) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if filters.get("type"):
            clauses.append("disaster_type = ?")
            params.append(filters["type"])
        if filters.get("level"):
            clauses.append("warning_level = ?")
            params.append(filters["level"])
        if filters.get("city"):
            clauses.append("city LIKE ?")
            params.append(f"%{filters['city']}%")
        if filters.get("county"):
            clauses.append("county LIKE ?")
            params.append(f"%{filters['county']}%")
        if filters.get("source_id"):
            clauses.append("source_id = ?")
            params.append(filters["source_id"])
        if filters.get("start_time"):
            clauses.append("published_at >= ?")
            params.append(filters["start_time"])
        if filters.get("end_time"):
            clauses.append("published_at <= ?")
            params.append(filters["end_time"])
        if filters.get("active_only"):
            clauses.append("is_active = 1")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit = min(max(int(filters.get("limit") or 100), 1), 500)
        query = f"SELECT * FROM disaster_events {where} ORDER BY published_at DESC, id DESC LIMIT ?"
        with self.connect() as conn:
            rows = conn.execute(query, (*params, limit)).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def count_by_source(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute("SELECT source_id, COUNT(*) AS count FROM disaster_events GROUP BY source_id").fetchall()
        return {str(row["source_id"]): int(row["count"]) for row in rows}

    def geojson(self, **filters: Any) -> dict[str, Any]:
        events = self.latest(**filters)
        features = []
        for event in events:
            if event.get("lat") is None or event.get("lng") is None:
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [event["lng"], event["lat"]]},
                "properties": {
                    "id": event["id"],
                    "title": event["title"],
                    "disaster_type": event["disaster_type"],
                    "warning_level": event["warning_level"],
                    "source_name": event["source_name"],
                    "source_id": event["source_id"],
                    "published_at": event["published_at"],
                    "summary": event["summary"],
                    "original_url": event["original_url"],
                    "geo_precision": event["geo_precision"],
                    "confidence": event["confidence"],
                },
            })
        return {"type": "FeatureCollection", "features": features}

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["is_active"] = bool(data.get("is_active"))
        return data


class CrawlerStatusStore:
    def __init__(self, path: Path | None = None) -> None:
        from config import CACHE_DIR

        self.path = path or CACHE_DIR / "official_disaster_source_status.json"

    def read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def update(self, source_id: str, status: dict[str, Any]) -> None:
        data = self.read()
        data[source_id] = {**data.get(source_id, {}), **status}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
