"""BiLSTM-CRF model for NER on industry standard documents.

This is an engineering skeleton — no pretrained weights are provided.
When torch is unavailable, import of this module does not crash the project;
the predictor falls back to rule-based NER.
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


class BiLSTMCRFModel:
    """BiLSTM + CRF for sequence labeling (BIO tags).

    Architecture:
        Embedding → BiLSTM → Linear → CRF

    Args:
        vocab_size: Size of input vocabulary.
        tagset_size: Number of BIO labels (default: len(BIO_LABELS)).
        embedding_dim: Dimension of token embeddings.
        hidden_dim: BiLSTM hidden dimension (each direction).
        num_layers: Number of BiLSTM layers.
        dropout: Dropout rate applied after embeddings and BiLSTM.
        pad_idx: Index of padding token.
    """

    def __init__(
        self,
        vocab_size: int = 5000,
        tagset_size: int = 23,  # 11 entities * 2 (B/I) + O
        embedding_dim: int = 128,
        hidden_dim: int = 256,
        num_layers: int = 2,
        dropout: float = 0.5,
        pad_idx: int = 0,
    ):
        if not HAS_TORCH:
            raise ImportError(
                "PyTorch is required for BiLSTMCRFModel. "
                "Install with: pip install torch"
            )

        self.vocab_size = vocab_size
        self.tagset_size = tagset_size
        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.dropout_rate = dropout
        self.pad_idx = pad_idx

        # Layers
        self.word_embeds = nn.Embedding(vocab_size, embedding_dim, padding_idx=pad_idx)
        self.dropout = nn.Dropout(dropout)
        self.lstm = nn.LSTM(
            embedding_dim, hidden_dim,
            num_layers=num_layers, bidirectional=True,
            batch_first=True, dropout=dropout if num_layers > 1 else 0,
        )
        self.hidden2tag = nn.Linear(hidden_dim * 2, tagset_size)
        self.crf = _SimpleCRF(tagset_size)

        # Placeholder for state
        self._device = torch.device("cpu")

    def to(self, device: Any) -> "BiLSTMCRFModel":
        self._device = device
        if HAS_TORCH:
            self.word_embeds.to(device)
            self.lstm.to(device)
            self.hidden2tag.to(device)
        return self

    def forward(self, token_ids: "torch.Tensor", mask: Optional["torch.Tensor"] = None
                ) -> "torch.Tensor":
        """Forward pass returning emission scores.

        Args:
            token_ids: LongTensor of shape (batch, seq_len).
            mask: BoolTensor of shape (batch, seq_len), True for valid tokens.

        Returns:
            Emission scores: (batch, seq_len, tagset_size).
        """
        if not HAS_TORCH:
            raise RuntimeError("torch not available")
        embeds = self.word_embeds(token_ids)
        embeds = self.dropout(embeds)
        lstm_out, _ = self.lstm(embeds)
        emissions = self.hidden2tag(lstm_out)
        return emissions

    def decode(self, emissions: "torch.Tensor", mask: Optional["torch.Tensor"] = None
               ) -> list[list[int]]:
        """Viterbi decode to best tag sequence.

        Args:
            emissions: (batch, seq_len, tagset_size).
            mask: (batch, seq_len) bool tensor.

        Returns:
            List of tag index sequences, one per batch item.
        """
        if not HAS_TORCH:
            raise RuntimeError("torch not available")
        return self.crf.decode(emissions, mask)

    def save(self, path: str) -> None:
        if not HAS_TORCH:
            return
        torch.save({
            "vocab_size": self.vocab_size,
            "tagset_size": self.tagset_size,
            "embedding_dim": self.embedding_dim,
            "hidden_dim": self.hidden_dim,
            "num_layers": self.num_layers,
            "state_dict": {
                "word_embeds": self.word_embeds.state_dict(),
                "lstm": self.lstm.state_dict(),
                "hidden2tag": self.hidden2tag.state_dict(),
            },
        }, path)
        logger.info("BiLSTMCRFModel saved to %s", path)

    @classmethod
    def load(cls, path: str) -> "BiLSTMCRFModel":
        if not HAS_TORCH:
            raise ImportError("torch required to load model")
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        model = cls(
            vocab_size=checkpoint["vocab_size"],
            tagset_size=checkpoint["tagset_size"],
            embedding_dim=checkpoint.get("embedding_dim", 128),
            hidden_dim=checkpoint.get("hidden_dim", 256),
            num_layers=checkpoint.get("num_layers", 2),
        )
        model.word_embeds.load_state_dict(checkpoint["state_dict"]["word_embeds"])
        model.lstm.load_state_dict(checkpoint["state_dict"]["lstm"])
        model.hidden2tag.load_state_dict(checkpoint["state_dict"]["hidden2tag"])
        return model


class _SimpleCRF(nn.Module if HAS_TORCH else object):
    """Minimal linear-chain CRF for Viterbi decoding."""

    def __init__(self, num_tags: int):
        if HAS_TORCH:
            super().__init__()
        self.num_tags = num_tags
        if HAS_TORCH:
            self.transitions = nn.Parameter(torch.randn(num_tags, num_tags))
            # START_TAG and STOP_TAG constraints
            self.transitions.data[:, 0] = -10000.0  # cannot transition to O from anything
            self.transitions.data[-1, :] = -10000.0

    def decode(self, emissions: "torch.Tensor", mask: Optional["torch.Tensor"] = None
               ) -> list[list[int]]:
        """Viterbi decoding."""
        if not HAS_TORCH:
            return []

        batch_size, seq_len, num_tags = emissions.shape
        if mask is None:
            mask = emissions.new_ones(batch_size, seq_len, dtype=torch.bool)

        best_paths: list[list[int]] = []

        for b in range(batch_size):
            seq_len_b = int(mask[b].sum().item())
            if seq_len_b == 0:
                best_paths.append([])
                continue

            # Forward Viterbi
            score = emissions[b, 0]  # (num_tags,)
            backpointers: list["torch.Tensor"] = []

            for t in range(1, seq_len_b):
                broadcast_score = score.unsqueeze(0)  # (1, num_tags)
                broadcast_emission = emissions[b, t].unsqueeze(1)  # (num_tags, 1)
                next_score = broadcast_score + self.transitions + broadcast_emission
                next_score, indices = next_score.max(dim=1)  # best over prev tags
                score = next_score
                backpointers.append(indices)

            # Backtrack
            best_tag = int(score.argmax().item())
            path = [best_tag]
            for bp in reversed(backpointers):
                best_tag = int(bp[best_tag].item())
                path.append(best_tag)
            path.reverse()
            best_paths.append(path)

        return best_paths
