from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from app_server.settings import settings


def setup_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_rag_fastapi_configured", False):
        return

    level = getattr(logging, settings.log_level, logging.INFO)
    root.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(level)
    root.addHandler(console)

    if settings.log_to_file:
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            settings.logs_dir / "app.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)

    root._rag_fastapi_configured = True
