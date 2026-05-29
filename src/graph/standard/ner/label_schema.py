"""NER label schema for industry standard documents.

Defines entity types, BIO label system, and bidirectional mappings.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Entity types ─────────────────────────────────────────────────────────────

ENTITY_TYPES = [
    "STANDARD",      # 标准编号
    "CHAPTER",       # 章节引用
    "CLAUSE",        # 条款
    "TERM",          # 术语
    "REQUIREMENT",   # 规范要求
    "INDICATOR",     # 指标参数
    "METHOD",        # 方法/技术
    "OBJECT",        # 适用对象
    "ORGANIZATION",  # 机构组织
    "LOCATION",      # 地点
    "DISASTER_TYPE", # 灾害类型
]

# ── BIO labels ───────────────────────────────────────────────────────────────

BIO_LABELS: list[str] = ["O"]
for etype in ENTITY_TYPES:
    BIO_LABELS.append(f"B-{etype}")
    BIO_LABELS.append(f"I-{etype}")

# ── Mappings ─────────────────────────────────────────────────────────────────

label_to_id: dict[str, int] = {label: i for i, label in enumerate(BIO_LABELS)}
id_to_label: dict[int, str] = {i: label for label, i in label_to_id.items()}

# ── Output struct ────────────────────────────────────────────────────────────

@dataclass
class ExtractedEntity:
    """A single extracted entity from NER."""
    text: str
    entity_type: str
    start_char: int
    end_char: int
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "entity_type": self.entity_type,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "confidence": self.confidence,
        }


def bio_tags_to_entities(tokens: list[str], tags: list[str]) -> list[ExtractedEntity]:
    """Convert token-level BIO tags back to entity spans.

    Args:
        tokens: list of token strings.
        tags: list of BIO tags, same length as tokens.

    Returns:
        list of ExtractedEntity objects.
    """
    if len(tokens) != len(tags):
        raise ValueError(f"Token/tag length mismatch: {len(tokens)} vs {len(tags)}")

    entities: list[ExtractedEntity] = []
    current_tokens: list[str] = []
    current_type: str = ""

    for i, (token, tag) in enumerate(zip(tokens, tags)):
        if tag.startswith("B-"):
            # End previous entity
            if current_tokens:
                entities.append(ExtractedEntity(
                    text="".join(current_tokens),
                    entity_type=current_type,
                    start_char=i - len(current_tokens),
                    end_char=i,
                ))
            current_tokens = [token]
            current_type = tag[2:]
        elif tag.startswith("I-") and current_type == tag[2:]:
            current_tokens.append(token)
        else:
            if current_tokens:
                entities.append(ExtractedEntity(
                    text="".join(current_tokens),
                    entity_type=current_type,
                    start_char=i - len(current_tokens),
                    end_char=i,
                ))
            current_tokens = []
            current_type = ""

    # Don't forget the last one
    if current_tokens:
        entities.append(ExtractedEntity(
            text="".join(current_tokens),
            entity_type=current_type,
            start_char=len(tokens) - len(current_tokens),
            end_char=len(tokens),
        ))

    return entities
