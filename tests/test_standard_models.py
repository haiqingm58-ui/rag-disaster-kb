"""Tests for standard graph data models."""

from datetime import date

import pytest

from src.graph.standard.models import (
    StandardDocument, Chapter, Clause, Term, Requirement,
    Indicator, Method, StandardObject,
    StandardStatus, Obligation, RequirementType, ObjectType,
)


class TestStandardDocument:
    def test_minimal(self):
        doc = StandardDocument(code="DZ/T 0286-2015", title="测试标准", industry="geological")
        assert doc.standard_id.startswith("std-")
        assert doc.status == StandardStatus.CURRENT

    def test_full_creation(self):
        doc = StandardDocument(
            code="GB/T 12345-2020", title="测试", industry="construction",
            status="current", publish_date=date(2020, 6, 1),
            effective_date=date(2021, 1, 1),
            issuing_body="住建部", source_file="test.md", summary="摘要",
        )
        assert doc.code == "GB/T 12345-2020"
        assert doc.publish_date == date(2020, 6, 1)

    def test_to_dict_from_dict(self):
        doc = StandardDocument(
            standard_id="std-test", code="DZ/T 0001", title="测试",
            industry="geo", status="draft", publish_date=date(2020, 1, 1),
            issuing_body="自然资源部",
        )
        d = doc.to_dict()
        assert d["standard_id"] == "std-test"
        assert d["status"] == "draft"
        assert d["publish_date"] == "2020-01-01"

        doc2 = StandardDocument.from_dict(d)
        assert doc2.code == doc.code
        assert doc2.status == doc.status
        assert doc2.publish_date == doc.publish_date


class TestChapter:
    def test_creation(self):
        ch = Chapter(standard_id="std-1", chapter_number="3", title="基本规定")
        assert ch.chapter_id.startswith("ch-")
        assert ch.level == 1

    def test_to_dict_from_dict(self):
        ch = Chapter(chapter_id="ch-test", standard_id="std-1",
                     chapter_number="3.1", title="一般规定", level=2, order_index=5)
        ch2 = Chapter.from_dict(ch.to_dict())
        assert ch2.chapter_number == "3.1"
        assert ch2.level == 2
        assert ch2.order_index == 5


class TestClause:
    def test_creation(self):
        cl = Clause(standard_id="std-1", clause_number="3.1.2", content="评估应采用定性与定量相结合的方法。")
        assert cl.clause_id.startswith("cl-")

    def test_to_dict_from_dict(self):
        cl = Clause(clause_id="cl-test", standard_id="std-1", chapter_id="ch-1",
                    clause_number="3.1.2", title="评估方法", content="测试内容",
                    level=3, order_index=2)
        cl2 = Clause.from_dict(cl.to_dict())
        assert cl2.clause_number == "3.1.2"
        assert cl2.content == "测试内容"


class TestTerm:
    def test_creation(self):
        t = Term(name="地质灾害", definition="自然因素引发的...")
        assert t.term_id.startswith("term-")

    def test_to_dict_from_dict(self):
        t = Term(term_id="term-x", name="滑坡", definition="定义", source_clause_id="cl-1")
        t2 = Term.from_dict(t.to_dict())
        assert t2.name == "滑坡"
        assert t2.definition == "定义"


class TestRequirement:
    def test_creation(self):
        r = Requirement(clause_id="cl-1", text="应采用定量方法。", obligation="shall")
        assert r.obligation == Obligation.SHALL

    def test_confidence_clamped(self):
        r = Requirement(clause_id="cl-1", text="test", confidence=1.5)
        assert r.confidence == 1.0

    def test_to_dict_from_dict(self):
        r = Requirement(requirement_id="req-x", clause_id="cl-1", text="应测试",
                        obligation="should", requirement_type="technical", confidence=0.9)
        r2 = Requirement.from_dict(r.to_dict())
        assert r2.obligation == Obligation.SHOULD
        assert r2.requirement_type == RequirementType.TECHNICAL


class TestIndicator:
    def test_creation(self):
        ind = Indicator(name="稳定系数", value="1.15", operator=">=", unit="无量纲")
        assert ind.indicator_id.startswith("ind-")

    def test_to_dict_from_dict(self):
        ind = Indicator(indicator_id="ind-x", name="厚度", value="200", operator=">=",
                        unit="mm", description="不小于200mm", source_clause_id="cl-1")
        ind2 = Indicator.from_dict(ind.to_dict())
        assert ind2.value == "200"
        assert ind2.operator == ">="


class TestMethod:
    def test_creation(self):
        m = Method(name="极限平衡法", description="边坡稳定性分析方法")
        assert m.method_id.startswith("meth-")

    def test_to_dict_from_dict(self):
        m = Method(method_id="meth-x", name="有限元法", description="数值方法", source_clause_id="cl-1")
        m2 = Method.from_dict(m.to_dict())
        assert m2.name == "有限元法"


class TestStandardObject:
    def test_creation(self):
        obj = StandardObject(name="滑坡", object_type="process")
        assert obj.object_id.startswith("obj-")
        assert obj.object_type == ObjectType.PROCESS

    def test_to_dict_from_dict(self):
        obj = StandardObject(object_id="obj-x", name="锚杆", object_type="equipment",
                             description="支护设备")
        obj2 = StandardObject.from_dict(obj.to_dict())
        assert obj2.name == "锚杆"
        assert obj2.object_type == ObjectType.EQUIPMENT


class TestEnums:
    def test_standard_status(self):
        assert len(StandardStatus) == 4

    def test_obligation(self):
        assert len(Obligation) == 3

    def test_requirement_type(self):
        assert len(RequirementType) == 6

    def test_object_type(self):
        assert len(ObjectType) == 7
