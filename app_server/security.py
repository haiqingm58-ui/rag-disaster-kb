from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status

from app_server.services.account_service import verify_user_login
from app_server.settings import settings


@dataclass(frozen=True)
class CurrentUser:
    username: str
    role: str = "admin"


AUTH_COOKIE_NAME = "rag_access_token"
_CHAT_HITS: dict[str, deque[float]] = defaultdict(deque)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _json_b64(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _b64encode(raw)


def _sign(message: str) -> str:
    digest = hmac.new(settings.jwt_secret.encode("utf-8"), message.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def verify_login(username: str, password: str) -> bool:
    return authenticate_user(username, password) is not None


def authenticate_user(username: str, password: str) -> dict[str, str] | None:
    user = verify_user_login(username, password)
    if not user:
        return None
    return {
        "username": str(user.get("username") or username),
        "role": str(user.get("role") or "user"),
        "email": str(user.get("email") or ""),
    }


def create_access_token(username: str, role: str = "admin") -> tuple[str, int]:
    now = int(time.time())
    expires_at = now + settings.jwt_expire_seconds
    header = _json_b64({"alg": "HS256", "typ": "JWT"})
    payload = _json_b64({"sub": username, "role": role, "iat": now, "exp": expires_at})
    signing_input = f"{header}.{payload}"
    return f"{signing_input}.{_sign(signing_input)}", expires_at


def decode_access_token(token: str) -> CurrentUser:
    try:
        header_b64, payload_b64, signature = token.split(".", 2)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录凭证。") from exc

    signing_input = f"{header_b64}.{payload_b64}"
    expected = _sign(signing_input)
    if not secrets.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录凭证。")

    try:
        header = json.loads(_b64decode(header_b64).decode("utf-8"))
        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录凭证。") from exc

    if header.get("alg") != "HS256":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录凭证。")
    if int(payload.get("exp") or 0) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录。")

    username = str(payload.get("sub") or "")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录凭证。")
    return CurrentUser(username=username, role=str(payload.get("role") or "admin"))


def require_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录。")
    token = authorization.split(" ", 1)[1].strip()
    return decode_access_token(token)


def require_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    # Kept for future role expansion. The current deployment has a single admin account.
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限。")
    return user


def check_chat_rate_limit(request: Request) -> None:
    limit = max(settings.chat_rate_limit_per_minute, 1)
    now = time.time()
    window_seconds = 60
    client_host = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    key = forwarded or client_host
    hits = _CHAT_HITS[key]

    while hits and hits[0] <= now - window_seconds:
        hits.popleft()
    if len(hits) >= limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="请求过于频繁，请稍后再试。")
    hits.append(now)
