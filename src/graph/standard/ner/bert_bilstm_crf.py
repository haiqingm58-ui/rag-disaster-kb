"""BERT-BiLSTM-CRF model for NER on industry standard documents.

Architecture: BERT encoder → BiLSTM → Linear → CRF.

This is an engineering skeleton. Requires transformers + torch.
When unavailable, import does not crash; predictor falls back to rule NER.
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


class BertBiLSTMCRFModel:
    """BERT encoder + BiLSTM + CRF for Chinese NER.

    Args:
        bert_model_name: HuggingFace model identifier (e.g. 'bert-base-chinese').
        tagset_size: Number of BIO labels.
        lstm_hidden_dim: BiLSTM hidden dimension (per direction).
        num_lstm_layers: Number of BiLSTM layers.
        dropout: Dropout probability.
    """

    def __init__(
        self,
        bert_model_name: str = "bert-base-chinese",
        tagset_size: int = 23,
        lstm_hidden_dim: int = 256,
        num_lstm_layers: int = 2,
        dropout: float = 0.5,
    ):
        if not HAS_TORCH:
            raise ImportError("PyTorch is required. Install with: pip install torch")
        if not HAS_TRANSFORMERS:
            raise ImportError(
                "transformers is required. Install with: pip install transformers"
            )

        self.bert_model_name = bert_model_name
        self.tagset_size = tagset_size
        self.lstm_hidden_dim = lstm_hidden_dim
        self.num_lstm_layers = num_lstm_layers
        self.dropout_rate = dropout

        # BERT encoder
        config = AutoConfig.from_pretrained(bert_model_name)
        self.bert = AutoModel.from_config(config)
        bert_hidden = config.hidden_size

        # BiLSTM
        self.dropout = nn.Dropout(dropout)
        self.lstm = nn.LSTM(
            bert_hidden, lstm_hidden_dim,
            num_layers=num_lstm_layers, bidirectional=True,
            batch_first=True, dropout=dropout if num_lstm_layers > 1 else 0,
        )

        # CRF
        self.hidden2tag = nn.Linear(lstm_hidden_dim * 2, tagset_size)
        from .bilstm_crf import _SimpleCRF
        self.crf = _SimpleCRF(tagset_size)

        self._device = torch.device("cpu")

    def to(self, device: Any) -> "BertBiLSTMCRFModel":
        self._device = device
        if HAS_TORCH:
            self.bert.to(device)
            self.lstm.to(device)
            self.hidden2tag.to(device)
            self.crf.to(device)
        return self

    def forward(self, input_ids: "torch.Tensor", attention_mask: "torch.Tensor"
                ) -> "torch.Tensor":
        """Forward pass returning emission scores.

        Args:
            input_ids: (batch, seq_len) token IDs from BERT tokenizer.
            attention_mask: (batch, seq_len).

        Returns:
            Emission scores: (batch, seq_len, tagset_size).
        """
        if not HAS_TORCH:
            raise RuntimeError("torch not available")

        bert_out = self.bert(input_ids, attention_mask=attention_mask)
        sequence_output = bert_out.last_hidden_state  # (batch, seq_len, bert_hidden)
        sequence_output = self.dropout(sequence_output)
        lstm_out, _ = self.lstm(sequence_output)
        emissions = self.hidden2tag(lstm_out)
        return emissions

    def decode(self, emissions: "torch.Tensor", mask: Optional["torch.Tensor"] = None
               ) -> list[list[int]]:
        """Viterbi decode to best tag sequence."""
        if not HAS_TORCH:
            return []
        return self.crf.decode(emissions, mask)

    def save(self, path: str) -> None:
        if not HAS_TORCH:
            return
        torch.save({
            "bert_model_name": self.bert_model_name,
            "tagset_size": self.tagset_size,
            "lstm_hidden_dim": self.lstm_hidden_dim,
            "num_lstm_layers": self.num_lstm_layers,
            "state_dict": {
                "lstm": self.lstm.state_dict(),
                "hidden2tag": self.hidden2tag.state_dict(),
                "crf": self.crf.state_dict(),
            },
        }, path)
        logger.info("BertBiLSTMCRFModel saved to %s", path)

    @classmethod
    def load(cls, path: str, bert_model_name: Optional[str] = None) -> "BertBiLSTMCRFModel":
        if not HAS_TORCH:
            raise ImportError("torch required")
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        model = cls(
            bert_model_name=bert_model_name or checkpoint["bert_model_name"],
            tagset_size=checkpoint["tagset_size"],
            lstm_hidden_dim=checkpoint.get("lstm_hidden_dim", 256),
            num_lstm_layers=checkpoint.get("num_lstm_layers", 2),
        )
        model.lstm.load_state_dict(checkpoint["state_dict"]["lstm"])
        model.hidden2tag.load_state_dict(checkpoint["state_dict"]["hidden2tag"])
        return model
