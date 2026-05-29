"""Rule-based NER for industry standard documents.

Serves as the always-available fallback when no deep learning model is loaded.
Detects entities via regex and keyword matching.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .label_schema import ExtractedEntity

logger = logging.getLogger(__name__)

# ── Patterns ─────────────────────────────────────────────────────────────────

_REQUIREMENT_SHALL_PATTERN = re.compile(
    r"(应[当]?|必须|须|不应|不得|禁止|严禁)([^。；\n]{4,80})"
)
_REQUIREMENT_SHOULD_PATTERN = re.compile(r"(宜)([^。；\n]{4,80})")
_REQUIREMENT_MAY_PATTERN = re.compile(r"(可[以]?)([^。；\n]{4,80})")

_INDICATOR_PATTERN = re.compile(
    r"([^\s。；，,]{1,20}?)\s*"
    r"(不小于|不大于|大于等于|小于等于|不应小于|不应大于|不应超过|"
    r"不得小于|不得大于|不得超过|大于|小于|等于|不超过|不小于|不宜小于|"
    r"不宜大于|宜为|应为|为|[≥≤><]=?)\s*"
    r"(\d+\.?\d*)\s*"
    r"([^\s。；，,]{0,6})?"
)

_TERM_DEF_PATTERN = re.compile(
    r"(?:^|\n|。|；)\s*([^\s。；：:]{1,30})[：:]\s*(.{10,200}?)(?=[。\n]|$)"
)

_METHOD_PATTERNS = [
    re.compile(r"(现场踏勘|遥感解译|工程地质测绘|地质测绘|无人机航拍|InSAR|LiDAR|物探|钻探|槽探|"
                r"原位测试|室内试验|数值模拟|有限元|有限差分|极限平衡|统计分析|"
                r"监测|检测|测试|勘探|测绘|调查|评估|勘察)"),
]

_DISASTER_TYPE_PATTERNS = [
    re.compile(r"(滑坡|崩塌|泥石流|地面塌陷|地裂缝|地面沉降|"
                r"地震|洪水|台风|山火|森林火灾|干旱|火山|海啸|"
                r"不稳定斜坡|危岩|滚石|碎屑流|堰塞湖)"),
]

_ORGANIZATION_PATTERNS = [
    re.compile(r"(中国地质调查局|自然资源部|应急管理部|住房和城乡建设部|交通运输部|"
                r"水利部|生态环境部|国家标准化管理委员会|"
                r"[一-鿿]{2,10}(?:局|院|所|中心|委员会|协会|公司))"),
]

_STANDARD_CODE_PATTERN = re.compile(
    r"((?:GB|DZ|SL|JT|TB|YB|HJ|CJJ|JGJ|DL|NB|SH|SY)/(?:T|Z)?\s*\d+(?:[\.-]\d+)?)"
)


def extract_entities(text: str) -> list[ExtractedEntity]:
    """Rule-based entity extraction from a text string.

    Returns a list of ExtractedEntity objects with start/end character offsets.
    """
    entities: list[ExtractedEntity] = []
    covered: set[tuple[int, int]] = set()

    def _add(entity_type: str, match_text: str, start: int, end: int,
             confidence: float = 0.85):
        span = (start, end)
        if span in covered or not match_text.strip():
            return
        covered.add(span)
        entities.append(ExtractedEntity(
            text=match_text, entity_type=entity_type,
            start_char=start, end_char=end, confidence=confidence,
        ))

    # 1. Standard codes
    for m in _STANDARD_CODE_PATTERN.finditer(text):
        _add("STANDARD", m.group(0), m.start(), m.end(), 0.95)

    # 2. Requirements (shall/should/may)
    for pat, conf in [(_REQUIREMENT_SHALL_PATTERN, 0.90),
                       (_REQUIREMENT_SHOULD_PATTERN, 0.80),
                       (_REQUIREMENT_MAY_PATTERN, 0.75)]:
        for m in pat.finditer(text):
            full_text = m.group(0)
            _add("REQUIREMENT", full_text, m.start(), m.end(), conf)

    # 3. Indicators
    for m in _INDICATOR_PATTERN.finditer(text):
        full_text = m.group(0).strip("，。；,.; ")
        _add("INDICATOR", full_text, m.start(), m.end(), 0.90)

    # 4. Terms
    for m in _TERM_DEF_PATTERN.finditer(text):
        name = m.group(1)
        if len(name) >= 2:
            _add("TERM", name, m.start(1), m.end(1), 0.85)

    # 5. Methods
    for pat in _METHOD_PATTERNS:
        for m in pat.finditer(text):
            _add("METHOD", m.group(0), m.start(), m.end(), 0.85)

    # 6. Disaster types
    for pat in _DISASTER_TYPE_PATTERNS:
        for m in pat.finditer(text):
            _add("DISASTER_TYPE", m.group(0), m.start(), m.end(), 0.90)

    # 7. Organizations
    for pat in _ORGANIZATION_PATTERNS:
        for m in pat.finditer(text):
            _add("ORGANIZATION", m.group(0), m.start(), m.end(), 0.80)

    return sorted(entities, key=lambda e: e.start_char)
