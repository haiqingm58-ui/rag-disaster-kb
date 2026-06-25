from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppSettings:
    version: str = "0.1.0"
    app_env: str = os.getenv("APP_ENV", "development").lower()
    host: str = os.getenv("APP_HOST", "0.0.0.0")
    port: int = _int_env("APP_PORT", 8000)
    max_upload_mb: int = _int_env("MAX_UPLOAD_MB", 30)
    graph_top_k: int = _int_env("GRAPH_TOP_K", 80)
    disaster_cache_ttl_seconds: int = _int_env("DISASTER_CACHE_TTL_SECONDS", 600)
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_to_file: bool = _bool_env("LOG_TO_FILE", True)
    cors_origins_raw: str = os.getenv("CORS_ORIGINS", "")
    trusted_hosts_raw: str = os.getenv("TRUSTED_HOSTS", "")
    auth_username: str = os.getenv("AUTH_USERNAME", "admin")
    auth_password: str = os.getenv("AUTH_PASSWORD", "admin123")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-this-dev-secret")
    jwt_expire_minutes: int = _int_env("JWT_EXPIRE_MINUTES", 480)
    chat_rate_limit_per_minute: int = _int_env("CHAT_RATE_LIMIT_PER_MINUTE", 30)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def jwt_expire_seconds(self) -> int:
        return self.jwt_expire_minutes * 60

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origins(self) -> list[str]:
        if self.cors_origins_raw.strip():
            return [item.strip() for item in self.cors_origins_raw.split(",") if item.strip()]
        if self.is_production:
            return []
        return ["http://127.0.0.1:8000", "http://localhost:8000"]

    @property
    def trusted_hosts(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts_raw.split(",") if item.strip()]

    @property
    def logs_dir(self) -> Path:
        return Path("logs")


settings = AppSettings()


_INSECURE_PASSWORDS = {"admin123", "password", "changeme", ""}


def assert_production_safety(current: AppSettings = settings) -> None:
    """Fail fast if production .env still carries insecure defaults.

    Called once at FastAPI startup. Skipped when APP_ENV != production so
    tests and local dev keep working with the shipped defaults.
    """
    if not current.is_production:
        return

    errors: list[str] = []
    if "change-this" in current.jwt_secret.lower() or len(current.jwt_secret) < 32:
        errors.append(
            "JWT_SECRET 太短或仍是默认占位符。请运行 python scripts/gen_secrets.py 生成 32 字节以上的随机值。"
        )
    if current.auth_password in _INSECURE_PASSWORDS:
        errors.append("AUTH_PASSWORD 仍是弱默认值。请运行 python scripts/gen_secrets.py 替换。")
    if not current.cors_origins_raw.strip():
        errors.append("生产环境必须显式配置 CORS_ORIGINS，例如 https://georisklab.com.cn。")

    if errors:
        bullet = "\n  - ".join(errors)
        raise RuntimeError(f"生产环境配置不安全，启动中止：\n  - {bullet}")
