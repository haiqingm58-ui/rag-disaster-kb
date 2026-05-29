"""Tests for standard knowledge extractor (rule-based)."""

from unittest.mock import MagicMock

import pytest

from src.graph.standard.models import Clause, Obligation, RequirementType
from src.graph.standard.extractor import (
    extract_requirements,
    extract_indicators,
    extract_terms_from_clause,
    extract_methods,
    extract_objects,
    extract_from_clause,
    extract_from_standard,
    _classify_requirement_type,
    extract_from_clause_llm,
)


def make_clause(clause_id="cl-1", number="3.1.2", content="", chapter_id=None, standard_id="std-1"):
    return Clause(
        clause_id=clause_id, standard_id=standard_id,
        chapter_id=chapter_id, clause_number=number,
        content=content, level=3, order_index=0,
    )


class TestExtractRequirements:
    def test_shall_sentence(self):
        cl = make_clause(content="地质灾害评估应采用定性与定量相结合的方法。")
        reqs = extract_requirements(cl)
        assert len(reqs) >= 1
        assert reqs[0].obligation == Obligation.SHALL

    def test_must_sentence(self):
        cl = make_clause(content="必须进行现场调查。")
        reqs = extract_requirements(cl)
        assert len(reqs) >= 1

    def test_should_sentence(self):
        cl = make_clause(content="宜采用极限平衡法进行边坡稳定性分析。")
        reqs = extract_requirements(cl)
        should_reqs = [r for r in reqs if r.obligation == Obligation.SHOULD]
        assert len(should_reqs) >= 1

    def test_may_sentence(self):
        cl = make_clause(content="可采用数值模拟方法进行复核。")
        reqs = extract_requirements(cl)
        may_reqs = [r for r in reqs if r.obligation == Obligation.MAY]
        assert len(may_reqs) >= 1

    def test_no_duplicates(self):
        cl = make_clause(content="应采用定量方法。应采用定量方法。应采用定量方法。")
        reqs = extract_requirements(cl)
        # Should deduplicate
        texts = [r.text for r in reqs]
        assert len(texts) == len(set(texts))

    def test_multiple_requirements(self):
        cl = make_clause(content="应采用定量方法。宜进行现场验证。可参考附录A。")
        reqs = extract_requirements(cl)
        obligations = {r.obligation for r in reqs}
        assert Obligation.SHALL in obligations

    def test_no_requirements(self):
        cl = make_clause(content="本标准适用于地质灾害评估。")
        reqs = extract_requirements(cl)
        assert reqs == []


class TestExtractIndicators:
    def test_greater_than_or_equal(self):
        cl = make_clause(content="滑坡稳定性计算的安全系数不应小于1.15。")
        inds = extract_indicators(cl)
        assert len(inds) >= 1
        assert inds[0].value == "1.15"
        assert "1.15" in inds[0].value

    def test_with_unit(self):
        cl = make_clause(content="挡土墙高度不宜大于5m。")
        inds = extract_indicators(cl)
        assert len(inds) >= 1
        assert any(ind.unit == "m" for ind in inds)

    def test_symbolic_operator(self):
        cl = make_clause(content="监测频率 ≥ 1次/天。")
        inds = extract_indicators(cl)
        assert len(inds) >= 1

    def test_no_indicators(self):
        cl = make_clause(content="本标准规定了评估方法。")
        inds = extract_indicators(cl)
        assert inds == []


class TestExtractTerms:
    def test_term_definition(self):
        cl = make_clause(content="""2.1 地质灾害：指自然因素或人为活动引发的危害人民生命和财产安全的地质现象。""")
        terms = extract_terms_from_clause(cl)
        assert len(terms) >= 1
        assert terms[0].name == "地质灾害"
        assert len(terms[0].definition) > 10

    def test_no_terms(self):
        cl = make_clause(content="应采用定量方法进行评估。")
        terms = extract_terms_from_clause(cl)
        assert terms == []


class TestExtractMethods:
    def test_method_reference(self):
        cl = make_clause(content="采用极限平衡法进行边坡稳定性分析。")
        methods = extract_methods(cl)
        assert len(methods) >= 1
        assert "极限平衡法" in methods[0].name

    def test_no_methods(self):
        cl = make_clause(content="评估应遵循本规范的要求。")
        methods = extract_methods(cl)
        assert methods == []


class TestExtractObjects:
    def test_object_mentioned(self):
        cl = make_clause(content="滑坡评估应考虑降雨和地震等因素。")
        objs = extract_objects(cl)
        assert len(objs) >= 1
        assert any(obj.name == "滑坡" for obj in objs)

    def test_no_objects(self):
        cl = make_clause(content="应按规定执行。")
        objs = extract_objects(cl)
        assert objs == []


class TestExtractFromClause:
    def test_returns_all_keys(self):
        cl = make_clause(content="滑坡稳定性计算的安全系数不应小于1.15。应采用极限平衡法。")
        result = extract_from_clause(cl)
        for key in ["requirements", "indicators", "terms", "methods", "objects"]:
            assert key in result
            assert isinstance(result[key], list)


class TestExtractFromStandard:
    def test_aggregates_across_clauses(self):
        clauses = [
            make_clause(clause_id="cl-1", number="3.1", content="滑坡稳定性系数不应小于1.15。"),
            make_clause(clause_id="cl-2", number="3.2", content="应采用极限平衡法进行评估。"),
        ]
        result = extract_from_standard(clauses)
        assert len(result["requirements"]) >= 1
        assert len(result["indicators"]) >= 1
        assert len(result["methods"]) >= 1


class TestClassifyRequirementType:
    def test_safety(self):
        assert _classify_requirement_type("安全防护措施应到位") == RequirementType.SAFETY

    def test_technical(self):
        assert _classify_requirement_type("监测参数应定期校准") == RequirementType.TECHNICAL

    def test_management(self):
        assert _classify_requirement_type("应建立档案管理制度") == RequirementType.MANAGEMENT

    def test_environmental(self):
        assert _classify_requirement_type("应减少对生态环境的影响") == RequirementType.ENVIRONMENTAL

    def test_quality(self):
        assert _classify_requirement_type("应通过质量检验合格") == RequirementType.QUALITY


class TestLLMExtraction:
    def test_no_llm_falls_back(self):
        cl = make_clause(content="滑坡稳定性系数不应小于1.15。")
        result = extract_from_clause_llm(cl, llm=None)
        assert len(result["indicators"]) >= 1

    def test_llm_fails_falls_back(self):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("API error")
        cl = make_clause(content="滑坡稳定性系数不应小于1.15。")
        result = extract_from_clause_llm(cl, llm=mock_llm, fallback=True)
        assert len(result["indicators"]) >= 1

    def test_llm_fails_no_fallback(self):
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("API error")
        cl = make_clause(content="test")
        result = extract_from_clause_llm(cl, llm=mock_llm, fallback=False)
        assert "error" in result
