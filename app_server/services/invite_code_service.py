from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.8+ normally has zoneinfo.
    ZoneInfo = None


INVITE_PREFIX = "opengeorisk"
INVITE_TIMEZONE_NAME = "Asia/Shanghai"


def current_invite_code(today: date | None = None) -> str:
    """Return today's registration invite code.

    Current rule:
    opengeorisk + Beijing date in YYYYMMDD format.

    Future rule changes should be made here so API code stays stable.
    """
    target_day = today or _beijing_today()
    return f"{INVITE_PREFIX}{target_day:%Y%m%d}"


def validate_registration_invite(invite_code: str, today: date | None = None) -> bool:
    candidate = (invite_code or "").strip().lower()
    expected = current_invite_code(today)
    return bool(candidate) and secrets.compare_digest(candidate, expected)


def _beijing_today() -> date:
    tz = ZoneInfo(INVITE_TIMEZONE_NAME) if ZoneInfo else timezone(timedelta(hours=8))
    return datetime.now(tz).date()
