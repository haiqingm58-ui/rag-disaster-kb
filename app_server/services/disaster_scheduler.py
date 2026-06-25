from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app_server.settings import settings
from config import CACHE_DIR
from src.ingestion.disaster_api import sync_current_events


logger = logging.getLogger(__name__)

SCHEDULER_STATUS_FILE = CACHE_DIR / "disaster_scheduler_status.json"


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_status(status: dict[str, Any]) -> None:
    SCHEDULER_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULER_STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_status() -> dict[str, Any]:
    try:
        return json.loads(SCHEDULER_STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_disaster_sync(force_refresh: bool = True, reason: str = "manual") -> dict[str, Any]:
    started = _now_text()
    try:
        result = sync_current_events(force_refresh=force_refresh)
        status = {
            "enabled": settings.disaster_scheduler_enabled,
            "running": False,
            "reason": reason,
            "last_run_started_at": started,
            "last_run_finished_at": _now_text(),
            "last_run_success": True,
            "last_result": result,
            "error": "",
        }
        _write_status(status)
        return status
    except Exception as exc:
        logger.exception("disaster sync failed reason=%s", reason)
        status = {
            "enabled": settings.disaster_scheduler_enabled,
            "running": False,
            "reason": reason,
            "last_run_started_at": started,
            "last_run_finished_at": _now_text(),
            "last_run_success": False,
            "last_result": {},
            "error": str(exc),
        }
        _write_status(status)
        return status


class DisasterScheduler:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._running = False

    def start(self) -> None:
        if not settings.disaster_scheduler_enabled:
            self._write_runtime_status(running=False)
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="disaster-sync-scheduler", daemon=True)
        self._thread.start()
        logger.info(
            "disaster scheduler started interval_minutes=%s run_on_start=%s",
            settings.disaster_scheduler_interval_minutes,
            settings.disaster_scheduler_run_on_start,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._write_runtime_status(running=False)

    def trigger(self, force_refresh: bool = True, reason: str = "manual") -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            status = self.status()
            status.update({"running": True, "error": "已有灾害同步任务正在运行。"})
            return status
        self._running = True
        self._write_runtime_status(running=True, reason=reason)
        try:
            return run_disaster_sync(force_refresh=force_refresh, reason=reason)
        finally:
            self._running = False
            self._lock.release()

    def status(self) -> dict[str, Any]:
        status = _read_status()
        status.update({
            "enabled": settings.disaster_scheduler_enabled,
            "running": self._running,
            "interval_minutes": settings.disaster_scheduler_interval_minutes,
            "firecrawl_configured": bool(settings.firecrawl_api_key.strip()),
        })
        return status

    def _loop(self) -> None:
        if settings.disaster_scheduler_run_on_start:
            delay = max(settings.disaster_scheduler_startup_delay_seconds, 0)
            if self._stop_event.wait(delay):
                return
            self.trigger(force_refresh=True, reason="startup")

        interval_seconds = max(settings.disaster_scheduler_interval_minutes, 1) * 60
        while not self._stop_event.wait(interval_seconds):
            self.trigger(force_refresh=True, reason="scheduled")

    def _write_runtime_status(self, running: bool, reason: str = "scheduler") -> None:
        status = _read_status()
        status.update({
            "enabled": settings.disaster_scheduler_enabled,
            "running": running,
            "reason": reason,
            "interval_minutes": settings.disaster_scheduler_interval_minutes,
            "firecrawl_configured": bool(settings.firecrawl_api_key.strip()),
        })
        _write_status(status)


disaster_scheduler = DisasterScheduler()
