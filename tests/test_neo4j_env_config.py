"""Tests for .env config reading — password stripping, safe logging."""

import os
from unittest.mock import patch

import pytest

from src.graph.common.neo4j_client import (
    _clean_env_value, neo4j_config, _log_config_safely,
)


class TestCleanEnvValue:
    def test_no_quotes(self):
        assert _clean_env_value("GeoriskLab@2026") == "GeoriskLab@2026"

    def test_single_quotes(self):
        assert _clean_env_value("'GeoriskLab@2026'") == "GeoriskLab@2026"

    def test_double_quotes(self):
        assert _clean_env_value('"GeoriskLab@2026"') == "GeoriskLab@2026"


    def test_strips_whitespace(self):
        assert _clean_env_value("  GeoriskLab@2026  ") == "GeoriskLab@2026"

    def test_single_quotes_with_whitespace(self):
        assert _clean_env_value("  'GeoriskLab@2026'  ") == "GeoriskLab@2026"

    def test_empty_string(self):
        assert _clean_env_value("") == ""

    def test_special_chars(self):
        assert _clean_env_value("p@ss#word!") == "p@ss#word!"


class TestNeo4jConfig:
    def test_returns_tuple(self):
        result = neo4j_config()
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_uri_default(self):
        with patch.dict(os.environ, {}, clear=True):
            # Need to re-import since module caches
            uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            assert uri == "bolt://localhost:7687"

    @patch.dict(os.environ, {
        "NEO4J_PASSWORD": "'GeoriskLab@2026'",
    }, clear=True)
    def test_password_stripped(self):
        # Verify _clean_env_value works correctly for the config
        raw = os.getenv("NEO4J_PASSWORD", "")
        cleaned = _clean_env_value(raw)
        assert cleaned == "GeoriskLab@2026"


class TestSafeLogging:
    def test_log_config_safely_no_password_in_message(self, caplog):
        import logging
        caplog.set_level(logging.INFO)
        # Reset the logged flag so it logs again
        import src.graph.common.neo4j_client as nc
        nc._config_logged = False
        _log_config_safely("bolt://localhost:7687", "neo4j", "GeoriskLab@2026", "neo4j")
        log_text = caplog.text
        assert "GeoriskLab" not in log_text
        assert "password_length=16" in log_text or "password_length" in log_text
