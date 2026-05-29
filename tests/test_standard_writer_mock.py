"""Tests for standard writer — all Neo4j calls are mocked (no real DB)."""

from unittest.mock import MagicMock, patch

import pytest

from src.graph.standard.models import (
    StandardDocument, Chapter, Clause, Term, Requirement,
    Indicator, Method, StandardObject,
)
from src.graph.standard import queries as q
from src.graph.standard.writer import init_schema, write_standard_graph


@pytest.fixture
def mock_session():
    """Mock a Neo4j session that records run() calls."""
    session = MagicMock()
    session.run.return_value = MagicMock()
    return session


@pytest.fixture
def sample_doc():
    return StandardDocument(
        standard_id="std-test", code="DZ/T 0001", title="测试标准",
        industry="geo", issuing_body="测试机构",
    )


@pytest.fixture
def sample_chapters(sample_doc):
    return [
        Chapter(chapter_id="ch-1", standard_id=sample_doc.standard_id,
                chapter_number="1", title="总则", level=1, order_index=0),
        Chapter(chapter_id="ch-2", standard_id=sample_doc.standard_id,
                chapter_number="2", title="术语", level=1, order_index=1),
    ]


@pytest.fixture
def sample_clauses(sample_doc):
    return [
        Clause(clause_id="cl-1", standard_id=sample_doc.standard_id,
               chapter_id="ch-2", clause_number="2.1", title="术语一",
               content="定义内容", level=2, order_index=0),
        Clause(clause_id="cl-2", standard_id=sample_doc.standard_id,
               chapter_id=None, clause_number="2.2", title="术语二",
               content="定义内容二", level=2, order_index=1),
    ]


@pytest.fixture
def sample_extraction(sample_clauses):
    return {
        "requirements": [
            Requirement(requirement_id="req-1", clause_id="cl-1",
                        text="应采用定量方法", obligation="shall"),
        ],
        "indicators": [
            Indicator(indicator_id="ind-1", name="稳定系数", value="1.15",
                      operator=">=", source_clause_id="cl-2"),
        ],
        "terms": [
            Term(term_id="term-1", name="地质灾害", definition="定义",
                 source_clause_id="cl-1"),
        ],
        "methods": [
            Method(method_id="meth-1", name="极限平衡法",
                   source_clause_id="cl-2"),
        ],
        "objects": [
            StandardObject(object_id="obj-1", name="滑坡", object_type="process"),
        ],
    }


class TestInitSchema:
    def test_runs_constraints_and_indexes(self, mock_session):
        with patch("src.graph.standard.writer.get_session") as mock_get:
            mock_get.return_value.__enter__.return_value = mock_session
            init_schema(database="testdb")
            # Should have run constraints + indexes
            total_statements = len(q.CREATE_CONSTRAINTS) + len(q.CREATE_INDEXES)
            assert mock_session.run.call_count == total_statements


class TestWriteStandardGraph:
    def test_writes_all_nodes_and_relationships(
        self, mock_session, sample_doc, sample_chapters, sample_clauses, sample_extraction,
    ):
        with patch("src.graph.standard.writer.get_session") as mock_get:
            mock_get.return_value.__enter__.return_value = mock_session
            stats = write_standard_graph(
                doc=sample_doc,
                chapters=sample_chapters,
                clauses=sample_clauses,
                terms=sample_extraction["terms"],
                requirements=sample_extraction["requirements"],
                indicators=sample_extraction["indicators"],
                methods=sample_extraction["methods"],
                objects=sample_extraction["objects"],
                database="testdb",
            )
            assert stats["standard"] == 1
            assert stats["chapters"] == 2
            assert stats["clauses"] == 2
            assert stats["terms"] == 1
            assert stats["requirements"] == 1
            assert stats["indicators"] == 1
            assert stats["methods"] == 1
            assert stats["objects"] == 1
            assert stats["relationships"] > 0

    def test_empty_extraction_no_error(
        self, mock_session, sample_doc, sample_chapters, sample_clauses,
    ):
        with patch("src.graph.standard.writer.get_session") as mock_get:
            mock_get.return_value.__enter__.return_value = mock_session
            stats = write_standard_graph(
                doc=sample_doc, chapters=sample_chapters, clauses=sample_clauses,
                database="testdb",
            )
            assert stats["terms"] == 0
            assert stats["requirements"] == 0

    def test_idempotent_write(
        self, mock_session, sample_doc, sample_chapters, sample_clauses, sample_extraction,
    ):
        """Calling write twice should succeed (MERGE is idempotent)."""
        with patch("src.graph.standard.writer.get_session") as mock_get:
            mock_get.return_value.__enter__.return_value = mock_session
            stats1 = write_standard_graph(
                doc=sample_doc, chapters=sample_chapters, clauses=sample_clauses,
                terms=sample_extraction["terms"],
                requirements=sample_extraction["requirements"],
                indicators=sample_extraction["indicators"],
                methods=sample_extraction["methods"],
                objects=sample_extraction["objects"],
                database="testdb",
            )
            stats2 = write_standard_graph(
                doc=sample_doc, chapters=sample_chapters, clauses=sample_clauses,
                terms=sample_extraction["terms"],
                requirements=sample_extraction["requirements"],
                indicators=sample_extraction["indicators"],
                methods=sample_extraction["methods"],
                objects=sample_extraction["objects"],
                database="testdb",
            )
            assert stats1 == stats2


class TestParamBuilders:
    def test_standard_params(self):
        doc = StandardDocument(standard_id="std-p", code="TEST", title="T", industry="I")
        params = q.standard_params(doc)
        assert params["standard_id"] == "std-p"
        assert params["code"] == "TEST"
        assert "standard_id" in params

    def test_chapter_params(self):
        ch = Chapter(chapter_id="ch-p", standard_id="std-p", chapter_number="1", title="T")
        params = q.chapter_params(ch)
        assert params["chapter_id"] == "ch-p"

    def test_clause_params(self):
        cl = Clause(clause_id="cl-p", standard_id="std-p", clause_number="1.1", content="C")
        params = q.clause_params(cl)
        assert params["clause_id"] == "cl-p"
        assert params["content"] == "C"

    def test_requirement_params(self):
        r = Requirement(requirement_id="req-p", clause_id="cl-p", text="T", obligation="shall")
        params = q.requirement_params(r)
        assert params["obligation"] == "shall"

    def test_indicator_params(self):
        ind = Indicator(indicator_id="ind-p", name="N", value="1.0", operator=">=")
        params = q.indicator_params(ind)
        assert params["value"] == "1.0"

    def test_term_params(self):
        t = Term(term_id="term-p", name="N", definition="D")
        params = q.term_params(t)
        assert params["name"] == "N"

    def test_method_params(self):
        m = Method(method_id="meth-p", name="M", description="D")
        params = q.method_params(m)
        assert params["name"] == "M"

    def test_object_params(self):
        o = StandardObject(object_id="obj-p", name="O", object_type="facility")
        params = q.standard_object_params(o)
        assert params["object_type"] == "facility"
