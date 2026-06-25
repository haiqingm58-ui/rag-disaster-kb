from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UserDataPayload(BaseModel):
    conversations: list[dict[str, Any]] = Field(default_factory=list)
    active_conversation_id: str | None = None


class UserDataResponse(UserDataPayload):
    username: str
