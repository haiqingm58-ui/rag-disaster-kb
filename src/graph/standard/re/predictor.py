"""RE predictor dispatcher: rule, casrel, or prgc.

Always defaults to rule-based. Falls back to rule if model weights are
missing or torch/transformers are not installed.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from .relation_schema import ExtractedRelation
from .rule_re import extract_relations_from_clause, extract_structural_relations

logger = logging.getLogger(__name__)


class RelationPredictor:
    """Unified RE predictor with automatic fallback to rule-based extraction.

    Usage:
        # Rule-based (default, always available)
        predictor = RelationPredictor(model_type="rule")
        relations = predictor.predict_from_clause("滑坡稳定性系数不应小于1.15。")

        # Deep learning (falls back to rule if weights missing)
        predictor = RelationPredictor(
            model_type="casrel",
            model_path="models/re/casrel.pt",
        )
        relations = predictor.predict_from_clause(text)
    """

    def __init__(
        self,
        model_type: str = "rule",
        model_path: Optional[str] = None,
    ):
        if model_type not in ("rule", "casrel", "prgc"):
            logger.warning("Unknown model_type '%s', falling back to rule", model_type)
            model_type = "rule"

        self.model_type = model_type
        self.model_path = model_path
        self._model = None

        if model_type != "rule":
            self._init_model()

    def _init_model(self) -> None:
        """Try to load DL model; fall back to rule on any failure."""
        try:
            if self.model_type == "casrel":
                from .casrel import CasRelModel, HAS_TORCH, HAS_TRANSFORMERS
                if not HAS_TORCH:
                    raise ImportError("torch not installed")
                if not HAS_TRANSFORMERS:
                    raise ImportError("transformers not installed")
                self._model = CasRelModel()
                if self.model_path and os.path.exists(self.model_path):
                    self._model = CasRelModel.load(self.model_path)
                    logger.info("Loaded CasRelModel from %s", self.model_path)
                else:
                    logger.warning(
                        "CasRel weights not found at '%s'; falling back to rule",
                        self.model_path,
                    )
                    self.model_type = "rule"
                    self._model = None

            elif self.model_type == "prgc":
                from .prgc import PRGCModel, HAS_TORCH, HAS_TRANSFORMERS
                if not HAS_TORCH:
                    raise ImportError("torch not installed")
                if not HAS_TRANSFORMERS:
                    raise ImportError("transformers not installed")
                self._model = PRGCModel()
                if self.model_path and os.path.exists(self.model_path):
                    self._model = PRGCModel.load(self.model_path)
                    logger.info("Loaded PRGCModel from %s", self.model_path)
                else:
                    logger.warning(
                        "PRGC weights not found at '%s'; falling back to rule",
                        self.model_path,
                    )
                    self.model_type = "rule"
                    self._model = None

        except (ImportError, Exception) as exc:
            logger.warning(
                "Failed to initialize %s model (%s); falling back to rule-based RE",
                self.model_type, exc,
            )
            self.model_type = "rule"
            self._model = None

    def predict_from_clause(
        self, clause_text: str, clause_number: str = ""
    ) -> list[ExtractedRelation]:
        """Extract relations from a clause's text.

        Args:
            clause_text: Text content of the clause.
            clause_number: Clause number string (e.g. '3.1.2').

        Returns:
            List of ExtractedRelation objects.
        """
        if self.model_type == "rule" or self._model is None:
            return extract_relations_from_clause(clause_text, clause_number)

        try:
            result = self._model.predict(None, None)  # Placeholder
            if not result:
                logger.debug("DL RE returned empty; using rule fallback")
                return extract_relations_from_clause(clause_text, clause_number)
            return [
                ExtractedRelation(
                    subject=r.get("subject", ""),
                    predicate=r.get("predicate", ""),
                    object=r.get("object", ""),
                    confidence=r.get("confidence", 0.8),
                )
                for r in result
            ]
        except Exception as exc:
            logger.warning("DL RE failed (%s); falling back to rule", exc)
            return extract_relations_from_clause(clause_text, clause_number)

    def predict_structural(
        self,
        standard_id: str,
        chapter_mapping: list[tuple[str, str]],
        clause_mapping: list[tuple[str, str, Optional[str]]],
    ) -> list[ExtractedRelation]:
        """Extract structural relations from document hierarchy.

        Args:
            standard_id: Standard document ID.
            chapter_mapping: (chapter_number, chapter_id) pairs.
            clause_mapping: (clause_number, clause_id, chapter_number) tuples.

        Returns:
            List of structural ExtractedRelation objects.
        """
        return extract_structural_relations(
            standard_id, chapter_mapping, clause_mapping,
        )
