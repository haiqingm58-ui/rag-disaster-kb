"""Tests for model fallback: ensure no crash without torch/transformers/weights."""

import pytest


class TestNERPredictorFallback:
    def test_default_is_rule(self):
        from src.graph.standard.ner.predictor import NERPredictor
        p = NERPredictor()
        assert p.model_type == "rule"

    def test_unknown_type_falls_back(self):
        from src.graph.standard.ner.predictor import NERPredictor
        p = NERPredictor(model_type="nonexistent_model")
        assert p.model_type == "rule"

    def test_bilstm_without_weights_falls_back(self):
        from src.graph.standard.ner.predictor import NERPredictor
        p = NERPredictor(
            model_type="bilstm_crf",
            model_path="/nonexistent/path/model.pt",
        )
        assert p.model_type == "rule"
        assert p._model is None

    def test_bert_bilstm_without_weights_falls_back(self):
        from src.graph.standard.ner.predictor import NERPredictor
        p = NERPredictor(
            model_type="bert_bilstm_crf",
            model_path="/nonexistent/path/model.pt",
        )
        assert p.model_type == "rule"
        assert p._model is None

    def test_rule_predict_works(self):
        from src.graph.standard.ner.predictor import NERPredictor
        p = NERPredictor(model_type="rule")
        entities = p.predict("滑坡稳定性系数不应小于1.15。")
        assert len(entities) > 0

    def test_fallback_predict_works(self):
        """Even when DL model init fails, predict() should still work via rule."""
        from src.graph.standard.ner.predictor import NERPredictor
        p = NERPredictor(
            model_type="bilstm_crf",
            model_path="/nonexistent/model.pt",
        )
        entities = p.predict("滑坡稳定性系数不应小于1.15。")
        assert len(entities) > 0


class TestRelationPredictorFallback:
    def test_default_is_rule(self):
        from src.graph.standard.re.predictor import RelationPredictor
        p = RelationPredictor()
        assert p.model_type == "rule"

    def test_unknown_type_falls_back(self):
        from src.graph.standard.re.predictor import RelationPredictor
        p = RelationPredictor(model_type="nonexistent")
        assert p.model_type == "rule"

    def test_casrel_without_weights_falls_back(self):
        from src.graph.standard.re.predictor import RelationPredictor
        p = RelationPredictor(
            model_type="casrel",
            model_path="/nonexistent/model.pt",
        )
        assert p.model_type == "rule"

    def test_prgc_without_weights_falls_back(self):
        from src.graph.standard.re.predictor import RelationPredictor
        p = RelationPredictor(
            model_type="prgc",
            model_path="/nonexistent/model.pt",
        )
        assert p.model_type == "rule"

    def test_rule_predict_works(self):
        from src.graph.standard.re.predictor import RelationPredictor
        p = RelationPredictor(model_type="rule")
        rels = p.predict_from_clause("滑坡稳定性系数不应小于1.15。", "3.1.2")
        assert len(rels) > 0

    def test_fallback_predict_works(self):
        from src.graph.standard.re.predictor import RelationPredictor
        p = RelationPredictor(model_type="prgc", model_path="/nonexistent/model.pt")
        rels = p.predict_from_clause("滑坡稳定性系数不应小于1.15。", "3.1.2")
        assert len(rels) > 0

    def test_structural_relations(self):
        from src.graph.standard.re.predictor import RelationPredictor
        p = RelationPredictor()
        rels = p.predict_structural(
            "std-1",
            [("1", "ch-1")],
            [("1.1", "cl-11", "ch-1")],
        )
        assert len(rels) > 0


class TestStandardGraphExtractorFallback:
    def test_default_rule(self):
        from src.graph.standard.extractor import StandardGraphExtractor
        from src.graph.standard.models import Clause
        ext = StandardGraphExtractor()
        cl = Clause(standard_id="std-1", clause_number="3.1",
                    content="滑坡稳定性系数不应小于1.15。")
        result = ext.extract_from_clause(cl)
        assert "requirements" in result
        assert len(result["requirements"]) >= 1

    def test_dl_types_fallback_to_rule(self):
        from src.graph.standard.extractor import StandardGraphExtractor
        from src.graph.standard.models import Clause
        ext = StandardGraphExtractor(
            ner_model_type="bert_bilstm_crf",
            ner_model_path="/nonexistent.pt",
            re_model_type="casrel",
            re_model_path="/nonexistent.pt",
        )
        cl = Clause(standard_id="std-1", clause_number="3.1",
                    content="滑坡稳定性系数不应小于1.15。")
        result = ext.extract_from_clause(cl)
        # Should still return rule-based results
        assert "requirements" in result
        assert len(result["requirements"]) >= 1
        assert "indicators" in result
