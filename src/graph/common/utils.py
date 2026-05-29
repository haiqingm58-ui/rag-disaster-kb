"""Shared utilities for the knowledge graph modules."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional


def new_id(prefix: str) -> str:
    """Generate a unique ID like 'evt-a1b2c3d4e5f6'."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def safe_float(value, default: float = 0.0) -> float:
    """Parse float safely, returning default on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default: int = 0) -> int:
    """Parse int safely, returning default on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def dt_iso(value: Optional[datetime]) -> Optional[str]:
    """Convert datetime to ISO 8601 string, returning None for falsy values."""
    return value.isoformat() if value else None


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 string to datetime, returning None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
