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


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _int_from_value(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _bool_from_value(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    auth_username: str = os.getenv("AUTH_USERNAME", "admin")
    auth_password: str = os.getenv("AUTH_PASSWORD", "admin123")
    jwt_secret: str = os.getenv("JWT_SECRET", "change-this-dev-secret")
    jwt_expire_minutes: int = _int_env("JWT_EXPIRE_MINUTES", 480)
    registration_invite_codes_raw: str = _first_env("REGISTRATION_INVITE_CODES", "INVITE_CODES")
    registration_default_role: str = os.getenv("REGISTRATION_DEFAULT_ROLE", "admin").lower()
    registration_code_expire_minutes: int = _int_env("REGISTRATION_CODE_EXPIRE_MINUTES", 10)
    registration_code_send_interval_seconds: int = _int_env("REGISTRATION_CODE_SEND_INTERVAL_SECONDS", 60)
    smtp_host: str = _first_env("SMTP_HOST", "SMTP_SERVER", "MAIL_HOST", "EMAIL_HOST")
    smtp_port: int = _int_from_value(_first_env("SMTP_PORT", "MAIL_PORT", "EMAIL_PORT", default="587"), 587)
    smtp_username: str = _first_env("SMTP_USERNAME", "SMTP_USER", "MAIL_USERNAME", "EMAIL_HOST_USER", "SENDER_EMAIL")
    smtp_password: str = _first_env("SMTP_PASSWORD", "SMTP_PASS", "MAIL_PASSWORD", "EMAIL_HOST_PASSWORD", "SENDER_PASSWORD")
    smtp_from: str = _first_env("SMTP_FROM", "MAIL_FROM", "EMAIL_FROM", "SENDER_EMAIL")
    smtp_use_tls_raw: str = _first_env("SMTP_USE_TLS", "MAIL_USE_TLS", "EMAIL_USE_TLS")
    smtp_use_ssl_raw: str = _first_env("SMTP_USE_SSL", "MAIL_USE_SSL", "EMAIL_USE_SSL")
    smtp_timeout_seconds: int = _int_env("SMTP_TIMEOUT_SECONDS", 12)
    chat_rate_limit_per_minute: int = _int_env("CHAT_RATE_LIMIT_PER_MINUTE", 30)
    web_search_enabled: bool = _bool_env("WEB_SEARCH_ENABLED", True)
    web_search_timeout_seconds: int = _int_env("WEB_SEARCH_TIMEOUT_SECONDS", 4)
    firecrawl_api_key: str = os.getenv("FIRECRAWL_API_KEY", "")
    firecrawl_base_url: str = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev")
    firecrawl_timeout_seconds: int = _int_env("FIRECRAWL_TIMEOUT_SECONDS", 20)
    firecrawl_search_limit: int = _int_env("FIRECRAWL_SEARCH_LIMIT", 4)
    firecrawl_cache_ttl_seconds: int = _int_env("FIRECRAWL_CACHE_TTL_SECONDS", 1800)
    disaster_scheduler_enabled: bool = _bool_env("DISASTER_SCHEDULER_ENABLED", False)
    disaster_scheduler_interval_minutes: int = _int_env("DISASTER_SCHEDULER_INTERVAL_MINUTES", 60)
    disaster_scheduler_startup_delay_seconds: int = _int_env("DISASTER_SCHEDULER_STARTUP_DELAY_SECONDS", 30)
    disaster_scheduler_run_on_start: bool = _bool_env("DISASTER_SCHEDULER_RUN_ON_START", False)
    rag_context_char_budget: int = _int_env("RAG_CONTEXT_CHAR_BUDGET", 6500)
    rag_context_item_char_limit: int = _int_env("RAG_CONTEXT_ITEM_CHAR_LIMIT", 900)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def jwt_expire_seconds(self) -> int:
        return self.jwt_expire_minutes * 60

    @property
    def registration_invite_codes(self) -> list[str]:
        return [item.strip() for item in self.registration_invite_codes_raw.split(",") if item.strip()]

    @property
    def registration_code_expire_seconds(self) -> int:
        return max(self.registration_code_expire_minutes, 1) * 60

    @property
    def registered_user_role(self) -> str:
        return self.registration_default_role if self.registration_default_role in {"admin", "user"} else "user"

    @property
    def smtp_use_ssl(self) -> bool:
        return _bool_from_value(self.smtp_use_ssl_raw, self.smtp_port == 465)

    @property
    def smtp_use_tls(self) -> bool:
        return _bool_from_value(self.smtp_use_tls_raw, not self.smtp_use_ssl)

    @property
    def smtp_sender(self) -> str:
        return self.smtp_from or self.smtp_username

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_sender)

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
    def logs_dir(self) -> Path:
        return Path("logs")


settings = AppSettings()
