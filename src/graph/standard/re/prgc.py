"""PRGC (Potential Relation and Global Correspondence) model for relation extraction.

Reference: "PRGC: Potential Relation and Global Correspondence Based
Joint Relational Triple Extraction" (Zheng et al., ACL 2021).

Architecture:
    BERT encoder → Potential Relation Judgment → Subject-Object Alignment →
    Global Correspondence

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


class PRGCModel:
    """PRGC: Potential Relation and Global Correspondence.

    Three components:
    1. Potential Relation Judgment — which relations exist for this sentence.
    2. Subject-Object Alignment — extract (subject, object) spans per relation.
    3. Global Correspondence — global scoring to prune invalid triples.

    Args:
        bert_model_name: HuggingFace model ID.
        num_relations: Number of relation types.
        max_seq_len: Maximum sequence length for global correspondence.
    """

    def __init__(
        self,
        bert_model_name: str = "bert-base-chinese",
        num_relations: int = 11,
        max_seq_len: int = 256,
    ):
        if not HAS_TORCH:
            raise ImportError("PyTorch is required. Install with: pip install torch")
        if not HAS_TRANSFORMERS:
            raise ImportError("transformers is required: pip install transformers")

        self.bert_model_name = bert_model_name
        self.num_relations = num_relations
        self.max_seq_len = max_seq_len

        config = AutoConfig.from_pretrained(bert_model_name)
        self.bert = AutoModel.from_config(config)
        bert_hidden = config.hidden_size

        # 1. Potential Relation Judgment
        self.relation_judgment = nn.Linear(bert_hidden, num_relations)

        # 2. Subject-Object Alignment — entity extraction per relation
        self.subject_extractor = nn.Linear(bert_hidden, num_relations * 2)  # start/end
        self.object_extractor = nn.Linear(bert_hidden, num_relations * 2)

        # 3. Global Correspondence
        self.global_corres = nn.Linear(bert_hidden * 2, 1)

        self._device = torch.device("cpu")

    def to(self, device: Any) -> "PRGCModel":
        self._device = device
        if HAS_TORCH:
            self.bert.to(device)
            self.relation_judgment.to(device)
            self.subject_extractor.to(device)
            self.object_extractor.to(device)
            self.global_corres.to(device)
        return self

    def forward(self, input_ids: "torch.Tensor", attention_mask: "torch.Tensor"
                ) -> dict:
        """Forward pass.

        Returns dict with keys:
            relation_logits, subject_logits, object_logits, global_corres_logits
        """
        if not HAS_TORCH:
            raise RuntimeError("torch not available")

        hidden = self.bert(input_ids, attention_mask=attention_mask).last_hidden_state
        # (B, L, H)

        # 1. Relation judgment — pool over sequence
        rel_logits = self.relation_judgment(hidden[:, 0, :])  # (B, R) using [CLS]

        # 2. Entity extraction per relation
        sub_logits = self.subject_extractor(hidden)   # (B, L, R*2)
        obj_logits = self.object_extractor(hidden)    # (B, L, R*2)

        # 3. Global correspondence (not fully implemented in skeleton)
        gc_logits_list: list["torch.Tensor"] = []

        return {
            "relation_logits": rel_logits,
            "subject_logits": sub_logits,
            "object_logits": obj_logits,
            "global_corres_logits": gc_logits_list,
        }

    def judge_relations(self, hidden_cls: "torch.Tensor",
                        threshold: float = 0.5) -> list[int]:
        """Determine which relations are present in the sentence.

        Args:
            hidden_cls: (hidden_dim,) vector at [CLS] position.
            threshold: Confidence threshold.

        Returns:
            List of relation indices predicted as present.
        """
        if not HAS_TORCH:
            return []

        logits = self.relation_judgment(hidden_cls)  # (R,)
        probs = torch.sigmoid(logits)
        return [int(i) for i in torch.where(probs > threshold)[0]]

    def predict(self, input_ids: "torch.Tensor", attention_mask: "torch.Tensor"
                ) -> list[dict]:
        """Inference: extract all triples.

        Returns list of {"subject": "...", "predicate": "REL_NAME",
                          "object": "...", "confidence": float}.
        """
        logger.debug("PRGC predict not yet implemented with tokenizer")
        return []

    def save(self, path: str) -> None:
        if not HAS_TORCH:
            return
        torch.save({
            "bert_model_name": self.bert_model_name,
            "num_relations": self.num_relations,
            "state_dict": {
                "relation_judgment": self.relation_judgment.state_dict(),
                "subject_extractor": self.subject_extractor.state_dict(),
                "object_extractor": self.object_extractor.state_dict(),
                "global_corres": self.global_corres.state_dict(),
            },
        }, path)
        logger.info("PRGCModel saved to %s", path)

    @classmethod
    def load(cls, path: str, bert_model_name: Optional[str] = None) -> "PRGCModel":
        if not HAS_TORCH:
            raise ImportError("torch required")
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        model = cls(
            bert_model_name=bert_model_name or checkpoint["bert_model_name"],
            num_relations=checkpoint["num_relations"],
        )
        model.relation_judgment.load_state_dict(
            checkpoint["state_dict"]["relation_judgment"])
        model.subject_extractor.load_state_dict(
            checkpoint["state_dict"]["subject_extractor"])
        model.object_extractor.load_state_dict(
            checkpoint["state_dict"]["object_extractor"])
        return model
