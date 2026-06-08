from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from app_server.services.email_service import EmailServiceError, send_password_reset_code, send_registration_code
from app_server.services.invite_code_service import validate_registration_invite
from app_server.settings import settings


ACCOUNT_DATA_DIR = Path("data/accounts")
USERS_FILE = ACCOUNT_DATA_DIR / "users.json"
VERIFICATION_FILE = ACCOUNT_DATA_DIR / "registration_codes.json"
PASSWORD_ITERATIONS = 260_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{2,40}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,20}$")
VERIFICATION_PURPOSE_REGISTER = "register"
VERIFICATION_PURPOSE_RESET = "password_reset"


def verify_user_login(username: str, password: str) -> dict[str, Any] | None:
    username = username.strip()
    if secrets.compare_digest(username, settings.auth_username) and secrets.compare_digest(password, settings.auth_password):
        return {"username": settings.auth_username, "email": "", "role": "admin", "source": "env"}

    user = get_user(username)
    if not user:
        return None
    if not _verify_password(password, str(user.get("password_hash") or "")):
        return None
    return _public_user(user)


def get_user(username: str) -> dict[str, Any] | None:
    username = username.strip()
    if username == settings.auth_username:
        return {"username": settings.auth_username, "email": "", "role": "admin", "source": "env"}
    return _load_users().get(username)


def send_registration_verification(email: str, invite_code: str) -> dict[str, Any]:
    email = _normalize_email(email)
    _require_valid_invite(invite_code)
    _validate_email(email)
    if _email_exists(email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册，请直接登录。")

    _send_verification_code(email, VERIFICATION_PURPOSE_REGISTER, send_registration_code)
    return {"ok": True, "expires_in": settings.registration_code_expire_seconds}


def register_user(username: str, password: str, email: str, invite_code: str, verification_code: str) -> dict[str, Any]:
    username = username.strip()
    email = _normalize_email(email)
    _require_valid_invite(invite_code)
    _validate_username(username)
    _validate_password(password)
    _validate_email(email)
    _verify_email_code(email, verification_code, VERIFICATION_PURPOSE_REGISTER)

    users = _load_users()
    if username == settings.auth_username or username in users:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该用户名已存在，请更换用户名。")
    if _email_exists(email, users):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已注册，请直接登录。")

    now = int(time.time())
    user = {
        "username": username,
        "email": email,
        "role": settings.registered_user_role,
        "password_hash": _hash_password(password),
        "created_at": now,
        "updated_at": now,
    }
    users[username] = user
    _save_json(USERS_FILE, users)
    _consume_email_code(email, VERIFICATION_PURPOSE_REGISTER)
    return _public_user(user)


def send_password_reset_verification(email: str) -> dict[str, Any]:
    email = _normalize_email(email)
    _validate_email(email)
    _, user = _find_user_by_email(email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该邮箱未注册。")
    _send_verification_code(email, VERIFICATION_PURPOSE_RESET, send_password_reset_code)
    return {"ok": True, "expires_in": settings.registration_code_expire_seconds}


def reset_user_password(email: str, verification_code: str, new_password: str) -> dict[str, Any]:
    email = _normalize_email(email)
    _validate_email(email)
    _validate_password(new_password)
    username, user = _find_user_by_email(email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该邮箱未注册。")
    _verify_email_code(email, verification_code, VERIFICATION_PURPOSE_RESET)

    users = _load_users()
    current = users.get(username)
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该邮箱未注册。")
    current["password_hash"] = _hash_password(new_password)
    current["updated_at"] = int(time.time())
    users[username] = current
    _save_json(USERS_FILE, users)
    _consume_email_code(email, VERIFICATION_PURPOSE_RESET)
    return _public_user(current)


def _load_users() -> dict[str, dict[str, Any]]:
    data = _load_json(USERS_FILE, {})
    if isinstance(data, dict) and isinstance(data.get("users"), dict):
        data = data["users"]
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def _load_codes() -> dict[str, dict[str, Any]]:
    data = _load_json(VERIFICATION_FILE, {})
    if not isinstance(data, dict):
        return {}
    now = int(time.time())
    return {
        str(email): value
        for email, value in data.items()
        if isinstance(value, dict) and int(value.get("expires_at") or 0) >= now
    }


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations_raw, salt, digest_hex = stored.split("$", 3)
        iterations = int(iterations_raw)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return secrets.compare_digest(digest, digest_hex)


def _code_hash(email: str, code: str) -> str:
    return hmac.new(settings.jwt_secret.encode("utf-8"), f"{email}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def _verification_key(email: str, purpose: str) -> str:
    return f"{purpose}:{email}"


def _send_verification_code(email: str, purpose: str, sender) -> None:
    codes = _load_codes()
    key = _verification_key(email, purpose)
    existing = codes.get(key)
    now = int(time.time())
    if existing and now - int(existing.get("sent_at") or 0) < settings.registration_code_send_interval_seconds:
        wait = settings.registration_code_send_interval_seconds - (now - int(existing.get("sent_at") or 0))
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"验证码发送过于频繁，请 {wait} 秒后再试。")

    code = f"{secrets.randbelow(1_000_000):06d}"
    try:
        sender(email, code)
    except EmailServiceError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    codes[key] = {
        "code_hash": _code_hash(email, code),
        "expires_at": now + settings.registration_code_expire_seconds,
        "sent_at": now,
        "attempts": 0,
        "purpose": purpose,
    }
    _save_json(VERIFICATION_FILE, codes)


def _verify_email_code(email: str, code: str, purpose: str) -> None:
    code = (code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入 6 位邮箱验证码。")

    codes = _load_codes()
    key = _verification_key(email, purpose)
    record = codes.get(key)
    if not record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码无效或已过期，请重新获取。")

    attempts = int(record.get("attempts") or 0)
    if attempts >= 5:
        codes.pop(key, None)
        _save_json(VERIFICATION_FILE, codes)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误次数过多，请重新获取。")

    if not secrets.compare_digest(str(record.get("code_hash") or ""), _code_hash(email, code)):
        record["attempts"] = attempts + 1
        codes[key] = record
        _save_json(VERIFICATION_FILE, codes)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误，请重新输入。")


def _consume_email_code(email: str, purpose: str) -> None:
    codes = _load_codes()
    codes.pop(_verification_key(email, purpose), None)
    _save_json(VERIFICATION_FILE, codes)


def _require_valid_invite(invite_code: str) -> None:
    if not (invite_code or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请码不能为空。")
    if not validate_registration_invite(invite_code):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="邀请码无效，请填写当天有效邀请码。")


def _validate_username(username: str) -> None:
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名需为 2-40 位字母、数字、下划线、点或短横线。")


def _validate_password(password: str) -> None:
    if len(password) < 8 or len(password) > 128:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码需为 8-128 位字符。")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码必须包含小写英文字母。")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码必须包含大写英文字母。")
    if not re.search(r"\d", password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码必须包含数字。")


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _validate_email(email: str) -> None:
    if not EMAIL_RE.fullmatch(email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱格式不正确。")


def _email_exists(email: str, users: dict[str, dict[str, Any]] | None = None) -> bool:
    users = users if users is not None else _load_users()
    return any(str(user.get("email") or "").lower() == email for user in users.values())


def _find_user_by_email(email: str) -> tuple[str, dict[str, Any] | None]:
    for username, user in _load_users().items():
        if str(user.get("email") or "").lower() == email:
            return username, user
    return "", None


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": str(user.get("username") or ""),
        "email": str(user.get("email") or ""),
        "role": str(user.get("role") or "user"),
    }
