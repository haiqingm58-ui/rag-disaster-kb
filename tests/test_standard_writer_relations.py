"""Tests for _merge_rel and all link_* functions — ensure property NAMES are
separate from property VALUES, and real IDs are passed as values."""

from unittest.mock import MagicMock, patch

import pytest

from src.graph.standard import writer as w


def _capture_rel_params():
    """Create a mock Neo4j session that captures the Cypher params."""
    captured = {}
    mock_sess = MagicMock()

    def _fake_run(stmt, params):
        captured["stmt"] = stmt
        captured["params"] = params
        return MagicMock()

    mock_sess.run = _fake_run
    return mock_sess, captured


class TestMergeRel:
    @patch.object(w, "get_session")
    def test_standard_to_chapter_params(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess

        w.link_standard_to_chapter("std-001", "ch-001")
        assert captured["params"]["a_id"] == "std-001", \
            f"a_id should be 'std-001', got {captured['params']['a_id']!r}"
        assert captured["params"]["b_id"] == "ch-001", \
            f"b_id should be 'ch-001', got {captured['params']['b_id']!r}"

    @patch.object(w, "get_session")
    def test_standard_to_clause_params(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess

        w.link_standard_to_clause("std-abc", "cl-xyz")
        assert captured["params"]["a_id"] == "std-abc"
        assert captured["params"]["b_id"] == "cl-xyz"

    @patch.object(w, "get_session")
    def test_chapter_to_clause_params(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess

        w.link_chapter_to_clause("ch-1", "cl-1")
        assert captured["params"]["a_id"] == "ch-1"
        assert captured["params"]["b_id"] == "cl-1"

    @patch.object(w, "get_session")
    def test_sub_clause_params(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess

        w.link_clause_to_sub_clause("cl-parent", "cl-child")
        assert captured["params"]["a_id"] == "cl-parent"
        assert captured["params"]["b_id"] == "cl-child"

    @patch.object(w, "get_session")
    def test_defines_term_params(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess

        w.link_standard_defines_term("std-1", "term-1")
        assert captured["params"]["a_id"] == "std-1"
        assert captured["params"]["b_id"] == "term-1"

    @patch.object(w, "get_session")
    def test_requirement_params(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess

        w.link_requirement_to_clause("req-1", "cl-1")
        assert captured["params"]["a_id"] == "cl-1", \
            f"a_id should be clause_id 'cl-1', got {captured['params']['a_id']!r}"
        assert captured["params"]["b_id"] == "req-1", \
            f"b_id should be requirement_id 'req-1', got {captured['params']['b_id']!r}"

    @patch.object(w, "get_session")
    def test_indicator_params(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess

        w.link_indicator_to_clause("ind-1", "cl-1")
        assert captured["params"]["a_id"] == "cl-1"
        assert captured["params"]["b_id"] == "ind-1"

    @patch.object(w, "get_session")
    def test_method_params(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess

        w.link_method_to_clause("meth-1", "cl-1")
        assert captured["params"]["a_id"] == "cl-1"
        assert captured["params"]["b_id"] == "meth-1"

    @patch.object(w, "get_session")
    def test_applies_to_params(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess

        w.link_clause_applies_to("cl-1", "obj-1")
        assert captured["params"]["a_id"] == "cl-1"
        assert captured["params"]["b_id"] == "obj-1"

    @patch.object(w, "get_session")
    def test_reference_params(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess

        w.link_standard_reference("std-a", "std-b")
        assert captured["params"]["a_id"] == "std-a"
        assert captured["params"]["b_id"] == "std-b"


class TestRegressionNoLiteralStrings:
    """Ensure params never equal property name strings."""

    FORBIDDEN_VALUES = {
        "standard_id", "chapter_id", "clause_id", "term_id",
        "requirement_id", "indicator_id", "method_id", "object_id",
    }

    @patch.object(w, "get_session")
    def test_chapter_link_no_literal(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess
        w.link_standard_to_chapter("std-real", "ch-real")
        for key in ["a_id", "b_id"]:
            assert captured["params"][key] not in self.FORBIDDEN_VALUES, \
                f"param {key} = {captured['params'][key]!r} should not be a property name"

    @patch.object(w, "get_session")
    def test_clause_link_no_literal(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess
        w.link_standard_to_clause("s1", "c1")
        for key in ["a_id", "b_id"]:
            assert captured["params"][key] not in self.FORBIDDEN_VALUES

    @patch.object(w, "get_session")
    def test_requirement_link_no_literal(self, mock_get_session):
        mock_sess, captured = _capture_rel_params()
        mock_get_session.return_value.__enter__.return_value = mock_sess
        w.link_requirement_to_clause("r99", "c99")
        for key in ["a_id", "b_id"]:
            assert captured["params"][key] not in self.FORBIDDEN_VALUES
