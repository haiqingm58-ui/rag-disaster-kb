"""CasRel (Cascade Binary Tagging) model for relation extraction.

Reference: "A Novel Cascade Binary Tagging Framework for Relational Triple Extraction"
(Wei et al., ACL 2020).

Architecture:
    BERT encoder → Subject tagger → Relation-specific object taggers

When torch/transformers are unavailable, import does not crash;
the predictor falls back to rule-based RE.
"""

from __future__ import annotations

import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    from transformers import AutoModel, AutoConfig
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False


class CasRelModel:
    """CasRel: Cascade Binary Tagging for Relation Extraction.

    Stage 1: Subject tagger — predicts (start, end) spans for subjects.
    Stage 2: For each detected subject and each relation type,
             predict object (start, end) spans.

    Args:
        bert_model_name: HuggingFace model ID (e.g. 'bert-base-chinese').
        num_relations: Number of relation types.
    """

    def __init__(
        self,
        bert_model_name: str = "bert-base-chinese",
        num_relations: int = 11,
    ):
        if not HAS_TORCH:
            raise ImportError("PyTorch is required. Install with: pip install torch")
        if not HAS_TRANSFORMERS:
            raise ImportError("transformers is required: pip install transformers")

        self.bert_model_name = bert_model_name
        self.num_relations = num_relations

        config = AutoConfig.from_pretrained(bert_model_name)
        self.bert = AutoModel.from_config(config)
        bert_hidden = config.hidden_size

        # Subject taggers: two binary classifiers for start/end
        self.subject_start = nn.Linear(bert_hidden, 1)
        self.subject_end = nn.Linear(bert_hidden, 1)

        # Object taggers: per-relation start/end classifiers
        self.object_start = nn.Linear(bert_hidden, num_relations)
        self.object_end = nn.Linear(bert_hidden, num_relations)

        self._device = torch.device("cpu")

    def to(self, device: Any) -> "CasRelModel":
        self._device = device
        if HAS_TORCH:
            self.bert.to(device)
            self.subject_start.to(device)
            self.subject_end.to(device)
            self.object_start.to(device)
            self.object_end.to(device)
        return self

    def forward(self, input_ids: "torch.Tensor", attention_mask: "torch.Tensor"
                ) -> dict:
        """Forward pass returning all logits.

        Returns dict with keys:
            subject_start_logits, subject_end_logits,
            object_start_logits, object_end_logits
        """
        if not HAS_TORCH:
            raise RuntimeError("torch not available")

        hidden = self.bert(input_ids, attention_mask=attention_mask).last_hidden_state

        sub_start = self.subject_start(hidden).squeeze(-1)   # (B, L)
        sub_end = self.subject_end(hidden).squeeze(-1)        # (B, L)
        obj_start = self.object_start(hidden)                  # (B, L, R)
        obj_end = self.object_end(hidden)                      # (B, L, R)

        return {
            "subject_start_logits": sub_start,
            "subject_end_logits": sub_end,
            "object_start_logits": obj_start,
            "object_end_logits": obj_end,
        }

    def extract_subjects(self, hidden: "torch.Tensor", seq_len: int,
                         threshold: float = 0.5) -> list[tuple[int, int]]:
        """Extract subject spans from encoded sequence.

        Args:
            hidden: (seq_len, hidden_dim) from BERT.
            seq_len: Effective sequence length.
            threshold: Confidence threshold for binary tagging.

        Returns:
            List of (start, end) character offset tuples.
        """
        if not HAS_TORCH:
            return []

        sub_start_logits = self.subject_start(hidden).squeeze(-1)
        sub_end_logits = self.subject_end(hidden).squeeze(-1)
        sub_start_prob = torch.sigmoid(sub_start_logits)
        sub_end_prob = torch.sigmoid(sub_end_logits)

        subjects: list[tuple[int, int]] = []
        start_candidates = torch.where(sub_start_prob > threshold)[0]

        for s in start_candidates:
            s = int(s.item())
            end_candidates = torch.where(sub_end_prob[s:] > threshold)[0]
            for e in end_candidates:
                e = s + int(e.item())
                if e >= s:
                    subjects.append((s, e))
                    break  # take the nearest end for each start

        return subjects

    def extract_objects(self, hidden: "torch.Tensor", subject_span: tuple[int, int],
                        relation_id: int, seq_len: int,
                        threshold: float = 0.5) -> list[tuple[int, int]]:
        """Extract object spans for a given subject and relation type.

        Args:
            hidden: (seq_len, hidden_dim).
            subject_span: (start, end) of subject.
            relation_id: Index of relation type.
            seq_len: Sequence length.

        Returns:
            List of (start, end) tuples for objects.
        """
        if not HAS_TORCH:
            return []

        obj_start_logits = self.object_start(hidden)[:, relation_id]
        obj_end_logits = self.object_end(hidden)[:, relation_id]
        obj_start_prob = torch.sigmoid(obj_start_logits)
        obj_end_prob = torch.sigmoid(obj_end_logits)

        objects: list[tuple[int, int]] = []
        start_candidates = torch.where(obj_start_prob > threshold)[0]

        for s in start_candidates:
            s = int(s.item())
            end_candidates = torch.where(obj_end_prob[s:] > threshold)[0]
            for e in end_candidates:
                e = s + int(e.item())
                if e >= s:
                    objects.append((s, e))
                    break

        return objects

    def predict(self, input_ids: "torch.Tensor", attention_mask: "torch.Tensor"
                ) -> list[dict]:
        """Inference: extract all (subject, relation, object) triples.

        Returns list of {"subject": "...", "predicate": "REL_NAME",
                          "object": "...", "confidence": float}.
        """
        # Placeholder — requires tokenizer + id2relation + span-to-text logic
        logger.debug("CasRel predict not yet implemented with tokenizer")
        return []

    def save(self, path: str) -> None:
        if not HAS_TORCH:
            return
        torch.save({
            "bert_model_name": self.bert_model_name,
            "num_relations": self.num_relations,
            "state_dict": {
                "subject_start": self.subject_start.state_dict(),
                "subject_end": self.subject_end.state_dict(),
                "object_start": self.object_start.state_dict(),
                "object_end": self.object_end.state_dict(),
            },
        }, path)
        logger.info("CasRelModel saved to %s", path)

    @classmethod
    def load(cls, path: str, bert_model_name: Optional[str] = None) -> "CasRelModel":
        if not HAS_TORCH:
            raise ImportError("torch required")
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        model = cls(
            bert_model_name=bert_model_name or checkpoint["bert_model_name"],
            num_relations=checkpoint["num_relations"],
        )
        model.subject_start.load_state_dict(checkpoint["state_dict"]["subject_start"])
        model.subject_end.load_state_dict(checkpoint["state_dict"]["subject_end"])
        model.object_start.load_state_dict(checkpoint["state_dict"]["object_start"])
        model.object_end.load_state_dict(checkpoint["state_dict"]["object_end"])
        return model
