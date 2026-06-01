from __future__ import annotations

from pydantic import BaseModel


class DisasterEventsResponse(BaseModel):
    events: list[dict]
    count: int
    statuses: dict
