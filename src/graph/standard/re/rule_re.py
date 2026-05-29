"""Rule-based relation extraction for industry standard documents.

Serves as the always-available fallback when no deep learning model is loaded.
Extracts relations based on structural parsing and regex patterns.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .relation_schema import ExtractedRelation, RELATION_TYPES

logger = logging.getLogger(__name__)

# ── Requirement relation patterns ────────────────────────────────────────────

_REQUIREMENT_PATTERN = re.compile(
    r"(?P<req>(?:应[当]?|须|必须|不应|不得|禁止|严禁|宜[^于]?|可[以]?)[^。；\n]{4,120})"
)

_INDICATOR_PATTERN = re.compile(
    r"(?P<name>[^\s。；，,]{1,20}?)\s*"
    r"(?P<op>不小于|不大于|大于等于|小于等于|不应小于|不应大于|不应超过|"
    r"不得小于|不得大于|不得超过|大于|小于|等于|不超过|不小于|不宜小于|"
    r"不宜大于|宜为|应为|为|[≥≤><]=?)\s*"
    r"(?P<value>\d+\.?\d*)\s*(?P<unit>[^\s。；，,]{0,6})?"
)

_TERM_DEF_PATTERN = re.compile(
    r"(?:^|\n|。|；)\s*(?P<name>[^\s。；：:]{1,30})[：:]\s*(?P<def>.{10,200}?)(?=[。\n]|$)"
)

_METHOD_KEYWORDS = [
    "现场踏勘", "遥感解译", "工程地质测绘", "地质测绘", "无人机航拍",
    "InSAR", "LiDAR", "物探", "钻探", "槽探", "原位测试", "室内试验",
    "数值模拟", "有限元", "有限差分", "极限平衡", "统计分析",
    "监测", "检测", "测试", "勘探", "测绘", "调查", "评估", "勘察",
    "定性分析", "定量分析", "综合分析",
]

_OBJECT_KEYWORDS = [
    ("滑坡", "process"), ("崩塌", "process"), ("泥石流", "process"),
    ("地面塌陷", "process"), ("地裂缝", "process"), ("地面沉降", "process"),
    ("不稳定斜坡", "process"), ("边坡", "facility"), ("挡土墙", "facility"),
    ("排水沟", "facility"), ("锚杆", "equipment"), ("监测点", "facility"),
    ("危岩", "process"), ("滚石", "process"),
]

# ── Public API ───────────────────────────────────────────────────────────────

def extract_relations_from_clause(
    clause_text: str,
    clause_number: str = "",
) -> list[ExtractedRelation]:
    """Extract all relations from a single clause's text.

    Args:
        clause_text: The full text content of a clause.
        clause_number: The clause number (e.g. '3.1.2'), used as subject.

    Returns:
        List of ExtractedRelation objects.
    """
    relations: list[ExtractedRelation] = []
    subject = clause_number if clause_number else clause_text[:40]

    # 1. HAS_REQUIREMENT
    for m in _REQUIREMENT_PATTERN.finditer(clause_text):
        req_text = m.group("req").strip("，。；,.; ")
        if len(req_text) > 4:
            relations.append(ExtractedRelation(
                subject=subject, predicate="HAS_REQUIREMENT",
                object=req_text, confidence=0.85,
                subject_type="Clause", object_type="Requirement",
            ))

    # 2. HAS_INDICATOR
    for m in _INDICATOR_PATTERN.finditer(clause_text):
        relations.append(ExtractedRelation(
            subject=subject, predicate="HAS_INDICATOR",
            object=m.group(0).strip(), confidence=0.90,
            subject_type="Clause", object_type="Indicator",
        ))

    # 3. DEFINES (Term)
    for m in _TERM_DEF_PATTERN.finditer(clause_text):
        name = m.group("name").strip()
        if len(name) >= 2:
            relations.append(ExtractedRelation(
                subject=subject, predicate="DEFINES",
                object=name, confidence=0.80,
                subject_type="Clause", object_type="Term",
            ))

    # 4. USES_METHOD
    seen_methods: set[str] = set()
    for kw in _METHOD_KEYWORDS:
        if kw in clause_text and kw not in seen_methods:
            seen_methods.add(kw)
            relations.append(ExtractedRelation(
                subject=subject, predicate="USES_METHOD",
                object=kw, confidence=0.85,
                subject_type="Clause", object_type="Method",
            ))

    # 5. APPLIES_TO
    for obj_name, obj_type in _OBJECT_KEYWORDS:
        if obj_name in clause_text:
            relations.append(ExtractedRelation(
                subject=subject, predicate="APPLIES_TO",
                object=obj_name, confidence=0.80,
                subject_type="Clause", object_type="StandardObject",
            ))

    return relations


def extract_structural_relations(
    standard_id: str,
    chapter_mapping: list[tuple[str, str]],  # (chapter_number, chapter_id)
    clause_mapping: list[tuple[str, str, Optional[str]]],
    # (clause_number, clause_id, chapter_number)
) -> list[ExtractedRelation]:
    """Extract structural relations from parsed document hierarchy.

    Args:
        standard_id: The standard's ID.
        chapter_mapping: List of (chapter_number, chapter_id).
        clause_mapping: List of (clause_number, clause_id, parent_chapter_number).

    Returns:
        List of structural ExtractedRelation objects.
    """
    relations: list[ExtractedRelation] = []

    for ch_num, ch_id in chapter_mapping:
        relations.append(ExtractedRelation(
            subject=standard_id, predicate="HAS_CHAPTER",
            object=ch_id, confidence=0.99,
            subject_type="StandardDocument", object_type="Chapter",
        ))

    for cl_num, cl_id, parent_ch in clause_mapping:
        # HAS_CLAUSE from standard
        relations.append(ExtractedRelation(
            subject=standard_id, predicate="HAS_CLAUSE",
            object=cl_id, confidence=0.99,
            subject_type="StandardDocument", object_type="Clause",
        ))
        # HAS_CLAUSE from chapter
        if parent_ch:
            relations.append(ExtractedRelation(
                subject=parent_ch, predicate="HAS_CLAUSE",
                object=cl_id, confidence=0.99,
                subject_type="Chapter", object_type="Clause",
            ))

    # HAS_SUB_CLAUSE based on numbering hierarchy
    # e.g. 3.1 → 3.1.1,  3.1.1 → 3.1.1.1
    for cl_num, cl_id, _ in clause_mapping:
        parts = cl_num.rsplit(".", 1)
        if len(parts) == 2:
            parent_num = parts[0]
            for p_num, p_id, _ in clause_mapping:
                if p_num == parent_num:
                    relations.append(ExtractedRelation(
                        subject=p_id, predicate="HAS_SUB_CLAUSE",
                        object=cl_id, confidence=0.99,
                        subject_type="Clause", object_type="Clause",
                    ))
                    break

    return relations
