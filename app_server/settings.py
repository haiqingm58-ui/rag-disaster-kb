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

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

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
