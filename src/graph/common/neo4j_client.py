"""Shared Neo4j connection management for all graph modules.

Provides a singleton driver, session context manager, connection health check,
and configuration from environment variables.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

logger = logging.getLogger(__name__)

_driver = None
_config_logged = False


def _find_project_root() -> Path:
    """Walk up from this file to find the project root (where .env lives)."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / ".env").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    return Path.cwd()


def _load_dotenv_once() -> None:
    """Ensure .env is loaded from project root."""
    try:
        from dotenv import load_dotenv
        root = _find_project_root()
        env_path = root / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
    except ImportError:
        pass


def _clean_env_value(value: str) -> str:
    """Strip whitespace and surrounding quotes from an env var value."""
    value = value.strip()
    # Strip single quotes
    if value.startswith("'") and value.endswith("'"):
        value = value[1:-1]
    # Strip double quotes
    elif value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return value


def neo4j_config() -> tuple:
    """Return (uri, user, password, database) from environment.

    Loads .env from project root. Strips quotes from password values.
    """
    _load_dotenv_once()

    uri = _clean_env_value(os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    user = _clean_env_value(os.getenv("NEO4J_USER", "neo4j"))
    password = _clean_env_value(os.getenv("NEO4J_PASSWORD", "neo4j"))
    database = _clean_env_value(os.getenv("NEO4J_DATABASE", "neo4j"))

    _log_config_safely(uri, user, password, database)
    return uri, user, password, database


def _log_config_safely(uri: str, user: str, password: str, database: str) -> None:
    """Log Neo4j config without exposing the password."""
    global _config_logged
    if _config_logged:
        return
    _config_logged = True
    logger.info(
        "Neo4j config: uri=%s user=%s database=%s password_length=%d",
        uri, user, database, len(password),
    )


def get_driver():
    """Return the global Neo4j driver, creating it lazily if needed."""
    global _driver
    if _driver is None:
        uri, user, password, _ = neo4j_config()
        _driver = GraphDatabase.driver(uri, auth=(user, password))
    return _driver


@contextmanager
def get_session(database: Optional[str] = None):
    """Yield a Neo4j session for the given database. Auto-closes."""
    db = database or neo4j_config()[3]
    driver = get_driver()
    session = driver.session(database=db)
    try:
        yield session
    finally:
        session.close()


def check_connection(database: Optional[str] = None) -> dict:
    """Verify Neo4j connectivity.

    Returns {"ok": True, "uri": ..., "database": ...} or
            {"ok": False, "error": "<中文错误信息>"}.
    """
    db = database or neo4j_config()[3]
    uri, user, _, _ = neo4j_config()

    try:
        driver = get_driver()
        with driver.session(database=db) as session:
            result = session.run("RETURN 1 AS n").single()
            if result and result["n"] == 1:
                logger.info("Neo4j connected: %s@%s/%s", user, uri, db)
                return {"ok": True, "uri": uri, "database": db}
    except ServiceUnavailable:
        msg = (
            f"Neo4j 连接失败：无法连接到 {uri}。"
            "请确认 Neo4j 数据库已启动，且 NEO4J_URI 配置正确。"
        )
        logger.error(msg)
        return {"ok": False, "error": msg}
    except AuthError:
        msg = (
            f"Neo4j 认证失败：用户 '{user}' 密码错误。"
            "请检查 NEO4J_USER 和 NEO4J_PASSWORD 环境变量。"
        )
        logger.error(msg)
        return {"ok": False, "error": msg}
    except Exception as exc:
        msg = f"Neo4j 连接异常：{exc}"
        logger.error(msg)
        return {"ok": False, "error": msg}

    return {"ok": False, "error": "Unknown connection error"}


def close_driver() -> None:
    """Close the global Neo4j driver."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")
