"""User-submitted disaster clues stored separately from official events."""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from config import REPORTS_DIR

REPORTS_FILE = REPORTS_DIR / "reports.jsonl"
IMAGES_DIR = REPORTS_DIR / "images"


def save_report(report: dict, image_file=None) -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    report_id = f"user_report_{uuid.uuid4().hex}"
    image_path = ""
    if image_file is not None:
        suffix = Path(image_file.name).suffix or ".jpg"
        image_path = str(IMAGES_DIR / f"{report_id}{suffix}")
        with open(image_path, "wb") as f:
            f.write(image_file.getbuffer())

    item = {
        "report_id": report_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "event_type": report.get("event_type", ""),
        "location": report.get("location", ""),
        "latitude": report.get("latitude"),
        "longitude": report.get("longitude"),
        "event_time": report.get("event_time", ""),
        "description": report.get("description", ""),
        "contact": report.get("contact", ""),
        "image_path": image_path,
        "verification_status": "未核验",
        "confidence_level": "unverified",
        "source_type": "user_report",
    }
    with REPORTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def load_reports() -> list[dict]:
    if not REPORTS_FILE.exists():
        return []
    reports = []
    for line in REPORTS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            reports.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return reports


def reports_to_csv_bytes(reports: list[dict]) -> bytes:
    if not reports:
        return b""
    import io

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=sorted({k for r in reports for k in r.keys()}))
    writer.writeheader()
    writer.writerows(reports)
    return output.getvalue().encode("utf-8-sig")
