from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


USER_DATA_DIR = Path("data/user_data")


def _safe_username(username: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", username.strip())
    return cleaned.strip("._-") or "user"


def _user_data_path(username: str) -> Path:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return USER_DATA_DIR / f"{_safe_username(username)}.json"


def load_user_data(username: str) -> dict[str, Any]:
    path = _user_data_path(username)
    if not path.exists():
        return {"username": username, "conversations": [], "active_conversation_id": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"username": username, "conversations": [], "active_conversation_id": None}
    conversations = data.get("conversations")
    if not isinstance(conversations, list):
        conversations = []
    active_conversation_id = data.get("active_conversation_id")
    return {
        "username": username,
        "conversations": conversations[:30],
        "active_conversation_id": active_conversation_id if isinstance(active_conversation_id, str) else None,
    }


def save_user_data(username: str, payload: dict[str, Any]) -> dict[str, Any]:
    conversations = payload.get("conversations")
    if not isinstance(conversations, list):
        conversations = []
    data = {
        "username": username,
        "conversations": conversations[:30],
        "active_conversation_id": payload.get("active_conversation_id") or None,
    }
    path = _user_data_path(username)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return data
