"""NER predictor dispatcher: rule, bilstm_crf, or bert_bilstm_crf.

Always defaults to rule-based. Falls back to rule if model weights are
missing or torch/transformers are not installed.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from .label_schema import ExtractedEntity
from .rule_ner import extract_entities as rule_extract

logger = logging.getLogger(__name__)


class NERPredictor:
    """Unified NER predictor with automatic fallback to rule-based extraction.

    Usage:
        # Rule-based (default, always available)
        predictor = NERPredictor(model_type="rule")
        entities = predictor.predict("滑坡评估应采用定性与定量相结合的方法。")

        # Deep learning (falls back to rule if weights missing)
        predictor = NERPredictor(
            model_type="bert_bilstm_crf",
            model_path="models/ner/bert_bilstm_crf.pt",
        )
        entities = predictor.predict(text)
    """

    def __init__(
        self,
        model_type: str = "rule",
        model_path: Optional[str] = None,
    ):
        if model_type not in ("rule", "bilstm_crf", "bert_bilstm_crf"):
            logger.warning("Unknown model_type '%s', falling back to rule", model_type)
            model_type = "rule"

        self.model_type = model_type
        self.model_path = model_path
        self._model = None

        if model_type != "rule":
            self._init_model()

    def _init_model(self) -> None:
        """Try to load DL model; log warning and stay on rule if anything fails."""
        try:
            if self.model_type == "bilstm_crf":
                from .bilstm_crf import BiLSTMCRFModel, HAS_TORCH
                if not HAS_TORCH:
                    raise ImportError("torch not installed")
                self._model = BiLSTMCRFModel()
                if self.model_path and os.path.exists(self.model_path):
                    self._model = BiLSTMCRFModel.load(self.model_path)
                    logger.info("Loaded BiLSTMCRFModel from %s", self.model_path)
                else:
                    logger.warning(
                        "BiLSTMCRF model weights not found at '%s'; "
                        "using untrained model (will fall back to rule)",
                        self.model_path,
                    )
                    self.model_type = "rule"
                    self._model = None

            elif self.model_type == "bert_bilstm_crf":
                from .bert_bilstm_crf import BertBiLSTMCRFModel, HAS_TORCH, HAS_TRANSFORMERS
                if not HAS_TORCH:
                    raise ImportError("torch not installed")
                if not HAS_TRANSFORMERS:
                    raise ImportError("transformers not installed")
                self._model = BertBiLSTMCRFModel()
                if self.model_path and os.path.exists(self.model_path):
                    self._model = BertBiLSTMCRFModel.load(self.model_path)
                    logger.info("Loaded BertBiLSTMCRFModel from %s", self.model_path)
                else:
                    logger.warning(
                        "BertBiLSTMCRF model weights not found at '%s'; "
                        "using untrained model (will fall back to rule)",
                        self.model_path,
                    )
                    self.model_type = "rule"
                    self._model = None

        except (ImportError, Exception) as exc:
            logger.warning(
                "Failed to initialize %s model (%s); falling back to rule-based NER",
                self.model_type, exc,
            )
            self.model_type = "rule"
            self._model = None

    def predict(self, text: str) -> list[ExtractedEntity]:
        """Extract entities from text.

        Args:
            text: Input text string (sentence or paragraph).

        Returns:
            List of ExtractedEntity objects, sorted by character offset.
        """
        if self.model_type == "rule" or self._model is None:
            return rule_extract(text)

        # For DL models with valid weights, tokenize and decode
        try:
            return self._dl_predict(text)
        except Exception as exc:
            logger.warning("DL prediction failed (%s); falling back to rule", exc)
            return rule_extract(text)

    def _dl_predict(self, text: str) -> list[ExtractedEntity]:
        """Run deep learning prediction. Returns empty list on tokenization failure."""
        # This method is called only when self._model is valid.
        # It requires tokenization → forward → decode → BIO-to-entities.
        # Since we don't have a tokenizer bundled (it depends on the training
        # setup), we fall back to rule for now. Subclasses or future work
        # can implement a proper tokenizer + inference pipeline.
        logger.debug("DL prediction not yet implemented with tokenizer; using rule")
        return rule_extract(text)
