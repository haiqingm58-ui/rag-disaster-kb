"""Extract structured knowledge from Clause content.

Rule-based extraction for:
  - Terms (from definitions in "术语和定义" chapters)
  - Requirements (shall/should/may sentences)
  - Indicators (numeric thresholds with units)
  - Methods (referenced methodologies)
  - StandardObjects (entities the standard applies to)

LLM-based extraction is reserved as an optional enhancement but rule-based
extraction is the primary and always-available path.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional, TYPE_CHECKING

from .models import (
    Clause, Term, Requirement, Indicator, Method, StandardObject,
    Obligation, RequirementType, ObjectType,
)
from ..common.utils import new_id, safe_float

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# ── Requirement patterns ─────────────────────────────────────────────────────

_SHALL_PATTERNS = [
    re.compile(r"应[当]?(?:严格)?(?!急|对|变|用|力|付|对)(?:[^。；\n]{2,80})"),
    re.compile(r"(?:必须|须)(?:[^。；\n]{2,80})"),
    re.compile(r"(?:不应|不得|禁止|严禁)(?:[^。；\n]{2,80})"),
]

_SHOULD_PATTERNS = [
    re.compile(r"宜(?!于)(?:[^。；\n]{2,80})"),
    re.compile(r"(?:宜[不未]|不宜)(?:[^。；\n]{2,80})"),
]

_MAY_PATTERNS = [
    re.compile(r"可[以]?(?!能|见|靠|行|信|用|选|按|参)(?:[^。；\n]{2,80})"),
]

# ── Indicator patterns ───────────────────────────────────────────────────────

_INDICATOR_PATTERNS = [
    # "不小于 0.75" / "大于 5m" / "不超过 24h" / "宜为 15mm"
    # NOTE: "为" removed from operators — too common as a Chinese character
    re.compile(
        r"(?P<name>[一-鿿\w]{2,30}?)\s*"
        r"(?P<op>不小于|不大于|大于等于|小于等于|不应小于|不应大于|不应超过|"
        r"不得小于|不得大于|不得超过|大于|小于|等于|不超过|不宜小于|"
        r"不宜大于|宜为|应为)\s*"
        r"(?P<value>\d+\.?\d*)\s*"
        r"(?P<unit>[一-鿿a-zA-Z%‰℃°万]+)?"
    ),
    # "≥ 0.75" / "≤ 5m" / "> 24h"
    re.compile(
        r"(?P<name>[一-鿿\w]{1,30}?)\s*"
        r"(?P<op>[≥≤><]=?)\s*"
        r"(?P<value>\d+\.?\d*)\s*"
        r"(?P<unit>[一-鿿a-zA-Z%‰℃°万]+)?"
    ),
]

# Words that should never be term names (chapter titles, generic labels)
_TERM_NAME_BLACKLIST = {
    "术语和定义", "术语与定义", "术语", "定义",
}

# Words that should never be indicator names (too short/generic)
_INDICATOR_NAME_BLACKLIST = {
    "且", "或", "和", "的", "了", "为", "人", "万元", "元", "个",
    "并", "不", "中", "上", "下", "大", "小", "多", "少",
    "例尺", "比例尺", "不宜", "不应", "不得", "并不", "及其",
    "以及", "及其", "可以", "可能", "需要", "必要", "一般",
}

# ── Term patterns ────────────────────────────────────────────────────────────

_TERM_DEF_PATTERNS = [
    # "3.1 地质灾害：指自然因素..."
    re.compile(r"(?:^|\n)(?:\d+(?:\.\d+)*\s+)?([一-鿿\w]{1,30})[：:]\s*(.{10,300}?)(?=\n(?:\d+\.)|$)"),
    # Markdown-style definition lists
    re.compile(r"(?:^|\n)\*\*([一-鿿\w]{1,30})\*\*[：:]\s*(.{10,300}?)(?=\n\*\*|$)"),
    # "3.1 中文术语 英文术语" — standard clause-title format
    # Match: heading number followed by Chinese term optionally followed by English
    re.compile(
        r"(?:^|\n)\d+(?:\.\d+)*\s+"
        r"([一-鿿\w]{1,30}(?:[一-鿿\w]{0,30}))"
        r"(?:\s+[a-zA-Z][a-zA-Z\s]{0,40})?"
        r"\n(.{10,400}?)(?=\n\d+(?:\.\d+)*\s|$)"
    ),
]

# Pattern for PDF-extracted terms: "term_name  english_name\n definition"
# e.g. content starts with "滑坡  landslide\n在重力作用下,..."
_TERM_PDF_PATTERN = re.compile(
    r"^([一-鿿\w]{1,30}(?:[一-鿿\w]{0,30}))"
    r"\s+([a-zA-Z][a-zA-Z\s]{0,50})"
    r"\n(.{10,500})",
    re.MULTILINE,
)

_TERM_PDF_SIMPLE_PATTERN = re.compile(
    r"^([一-鿿\w]{2,30}(?:[一-鿿\w]{0,30}))"
    r"\n(.{10,500})",
    re.MULTILINE,
)

# Pattern to detect if a clause title itself is a term definition heading
# e.g. "滑坡 landslide" from heading "3.1 滑坡 landslide"
_TERM_TITLE_PATTERN = re.compile(
    r"^([一-鿿\w]{1,30}(?:[一-鿿\w]{0,30}))"
    r"(?:\s+([a-zA-Z][a-zA-Z\s]{0,40}))?$"
)


# Pattern to detect term-like titles: Chinese + optional English, no clause number
_TERM_TITLE_LIKE = re.compile(
    r'^[一-鿿]{1,30}(?:[一-鿿]{0,30})$'
)


def _looks_like_term_title(title: str) -> bool:
    """Check if a clause title looks like a standalone term definition."""
    title = title.strip()
    if not title:
        return False
    # Skip if it starts with a clause number
    if re.match(r'^\d+(?:\.\d+)*\s', title):
        return False
    # Skip if it contains requirement keywords
    if re.search(r'[应必须不得禁止严禁宜可]', title):
        return False
    # Skip if title is just a generic chapter heading
    if title in ('范围', '规范性引用文件', '术语和定义', '目 次', '前 言', '引 言',
                 '附录', '参考文献'):
        return False
    # Chinese + optional English — typical term format
    if re.match(r'^[一-鿿]{1,30}[a-zA-Z\s]{0,60}$', title):
        return True
    if re.match(r'^[一-鿿]{1,30}\s+[a-zA-Z][a-zA-Z\s]{0,60}$', title):
        return True
    return False


def _looks_like_terminology_standard(clauses: list[Clause]) -> bool:
    """Detect if this standard is primarily a terminology/glossary standard.

    Heuristic: if more than 40% of clause titles look like term definitions,
    treat the entire standard (after chapter 1) as a terminology standard.
    """
    if len(clauses) < 10:
        return False
    term_like = sum(1 for cl in clauses if _looks_like_term_title(cl.title or ""))
    ratio = term_like / len(clauses) if clauses else 0
    return ratio > 0.3


def _is_term_definition_chapter(clause: Clause) -> bool:
    """Check if a clause likely belongs to a terminology/definitions chapter."""
    title = (clause.title or "").lower()
    content = (clause.content or "")[:200].lower()
    return (
        "术语" in title or "定义" in title or
        "术语和定义" in title or "术语与定义" in title
    )

# ── Method patterns ──────────────────────────────────────────────────────────

_METHOD_PATTERNS = [
    re.compile(r"(?:采用|使用|按[照]?)\s*(.{4,40}?(?:法|方法|技术|模型|分析|测试|检测))"),
    re.compile(r"((?:.{2,20}?(?:法|方法|模型|技术))\s*(?:参见|见|按|符合))"),
]

# ── Object patterns ──────────────────────────────────────────────────────────

_OBJECT_KEYWORDS = {
    "滑坡": ObjectType.PROCESS,
    "泥石流": ObjectType.PROCESS,
    "崩塌": ObjectType.PROCESS,
    "地面塌陷": ObjectType.PROCESS,
    "地裂缝": ObjectType.PROCESS,
    "地面沉降": ObjectType.PROCESS,
    "边坡": ObjectType.FACILITY,
    "挡土墙": ObjectType.FACILITY,
    "排水沟": ObjectType.FACILITY,
    "监测点": ObjectType.FACILITY,
    "锚杆": ObjectType.EQUIPMENT,
    "传感器": ObjectType.EQUIPMENT,
    "钻孔": ObjectType.PROCESS,
    "岩土体": ObjectType.MATERIAL,
    "混凝土": ObjectType.MATERIAL,
}


# ── Public API ────────────────────────────────────────────────────────────────

def extract_requirements(clause: Clause) -> list[Requirement]:
    """Extract normative requirements from a clause's content."""
    results: list[Requirement] = []
    seen_texts: set[str] = set()

    for patterns, obligation in [
        (_SHALL_PATTERNS, Obligation.SHALL),
        (_SHOULD_PATTERNS, Obligation.SHOULD),
        (_MAY_PATTERNS, Obligation.MAY),
    ]:
        for pat in patterns:
            for m in pat.finditer(clause.content):
                text = m.group(0).strip("，。；,.; ")
                if len(text) < 4 or text in seen_texts:
                    continue
                seen_texts.add(text)
                results.append(Requirement(
                    clause_id=clause.clause_id,
                    text=text,
                    obligation=obligation,
                    requirement_type=_classify_requirement_type(text),
                    confidence=0.85,
                ))

    return results


def extract_indicators(clause: Clause) -> list[Indicator]:
    """Extract quantitative indicators from a clause's content."""
    results: list[Indicator] = []

    for pat in _INDICATOR_PATTERNS:
        for m in pat.finditer(clause.content):
            name = (m.group("name") or "").strip()
            op = (m.group("op") or "").strip()
            value = (m.group("value") or "").strip()
            unit = (m.group("unit") or "").strip()

            if not name or not value:
                continue
            # Filter noise: blacklisted single words, overly short fragments
            if name in _INDICATOR_NAME_BLACKLIST:
                continue
            if len(name) < 2 and not unit:
                continue

            results.append(Indicator(
                name=name,
                value=value,
                operator=op,
                unit=unit,
                description=m.group(0).strip(),
                source_clause_id=clause.clause_id,
            ))

    return results


def extract_terms_from_clause(clause: Clause, is_definition_section: bool = False) -> list[Term]:
    """Extract defined terms from a clause's content and title.

    Handles multiple formats:
      - Clause title as term (e.g. heading "3.1 滑坡 landslide")
      - PDF-extracted: content starts with "term  english\\ndefinition"
      - Traditional: "term：definition" inline
    """
    results: list[Term] = []
    content = (clause.content or "").strip()
    title = (clause.title or "").strip()

    # Pattern A: Clause title as term (e.g. heading "3.1 滑坡 landslide")
    if is_definition_section and title:
        m = _TERM_TITLE_PATTERN.match(title)
        if m:
            name = m.group(1).strip()
            english = (m.group(2) or "").strip()
            if len(name) >= 2 and name not in _TERM_NAME_BLACKLIST:
                definition = content[:500] if content else ""
                if english:
                    definition = f"[EN: {english}] {definition}"
                if definition:
                    results.append(Term(
                        name=name, definition=definition,
                        source_clause_id=clause.clause_id,
                    ))
                    return results

    # Pattern B: Clause title/format looks like a term (e.g., "岩溶塌陷karst collapse")
    # Detect even without is_definition_section flag
    if (is_definition_section or _looks_like_term_title(title)) and content:
        m = _TERM_PDF_PATTERN.match(content)
        if m:
            name = m.group(1).strip()
            english = m.group(2).strip()
            definition = m.group(3).strip()
            if len(name) >= 2 and len(definition) >= 10 and name not in _TERM_NAME_BLACKLIST:
                if english:
                    definition = f"[EN: {english}] {definition}"
                results.append(Term(
                    name=name, definition=definition,
                    source_clause_id=clause.clause_id,
                ))
                return results

        # Try simple pattern (no English, just "term\\ndefinition")
        m = _TERM_PDF_SIMPLE_PATTERN.match(content)
        if m:
            name = m.group(1).strip()
            definition = m.group(2).strip()
            if len(name) >= 2 and len(definition) >= 10 and name not in _TERM_NAME_BLACKLIST:
                results.append(Term(
                    name=name, definition=definition,
                    source_clause_id=clause.clause_id,
                ))
                return results

    # Pattern C: Content-based inline term definition (e.g. "滑坡：指...")
    for pat in _TERM_DEF_PATTERNS:
        for m in pat.finditer(content):
            name = m.group(1).strip()
            definition = m.group(2).strip()
            if len(name) < 2 or len(definition) < 5:
                continue
            results.append(Term(
                name=name, definition=definition,
                source_clause_id=clause.clause_id,
            ))

    return results


def extract_methods(clause: Clause) -> list[Method]:
    """Extract referenced methods from a clause's content."""
    results: list[Method] = []
    seen: set[str] = set()

    for pat in _METHOD_PATTERNS:
        for m in pat.finditer(clause.content):
            name = m.group(1).strip()
            if name in seen or len(name) < 3:
                continue
            seen.add(name)
            results.append(Method(
                name=name,
                description=m.group(0).strip(),
                source_clause_id=clause.clause_id,
            ))

    return results


def extract_objects(clause: Clause) -> list[StandardObject]:
    """Extract entities the standard applies to from clause content."""
    results: list[StandardObject] = []
    seen: set[str] = set()

    for keyword, obj_type in _OBJECT_KEYWORDS.items():
        if keyword in clause.content and keyword not in seen:
            seen.add(keyword)
            results.append(StandardObject(
                name=keyword,
                object_type=obj_type,
                description=f"从条款 {clause.clause_number} 提及",
            ))

    return results


def extract_from_clause(clause: Clause, is_definition_section: bool = False) -> dict:
    """Run all rule-based extractors on a single clause.

    Returns dict with keys: requirements, indicators, terms, methods, objects.
    """
    return {
        "requirements": extract_requirements(clause),
        "indicators": extract_indicators(clause),
        "terms": extract_terms_from_clause(clause, is_definition_section),
        "methods": extract_methods(clause),
        "objects": extract_objects(clause),
    }


def extract_from_standard(clauses: list[Clause]) -> dict:
    """Run all rule-based extractors on all clauses of a standard.

    Deduplicates StandardObjects by name within the standard.
    Returns dict with keys: requirements, indicators, terms, methods, objects.
    """
    all_requirements: list[Requirement] = []
    all_indicators: list[Indicator] = []
    all_terms: list[Term] = []
    all_methods: list[Method] = []
    all_objects: list[StandardObject] = []
    seen_objects: dict[str, StandardObject] = {}

    # Get the standard_id from the first clause
    standard_id = clauses[0].standard_id if clauses else ""

    # Detect which clauses are in the terminology/definitions section
    term_chapter_numbers: set[str] = set()
    for clause in clauses:
        if _is_term_definition_chapter(clause):
            term_chapter_numbers.add(clause.clause_number.split(".")[0])

    # Detect if this is a pure terminology standard
    is_terminology_standard = _looks_like_terminology_standard(clauses)

    for clause in clauses:
        # Direct prefix check + terminology standard heuristic
        prefix = clause.clause_number.split(".")[0]
        in_term_section = (
            prefix in term_chapter_numbers
            or (is_terminology_standard and prefix not in ("", "1"))
            or _looks_like_term_title(clause.title or "")
        )

        result = extract_from_clause(clause, is_definition_section=in_term_section)
        all_requirements.extend(result["requirements"])
        all_indicators.extend(result["indicators"])
        all_terms.extend(result["terms"])
        all_methods.extend(result["methods"])

        # Deduplicate objects by name
        for obj in result["objects"]:
            if obj.name not in seen_objects:
                seen_objects[obj.name] = obj
                all_objects.append(obj)

    # Set standard_id on all extracted nodes
    for r in all_requirements:
        r.standard_id = standard_id
    for i in all_indicators:
        i.standard_id = standard_id
    for t in all_terms:
        t.standard_id = standard_id
    for m in all_methods:
        m.standard_id = standard_id
    for o in all_objects:
        o.standard_id = standard_id

    return {
        "requirements": all_requirements,
        "indicators": all_indicators,
        "terms": all_terms,
        "methods": all_methods,
        "objects": all_objects,
    }


# ── LLM-based extraction (reserved, not primary) ──────────────────────────────

def extract_from_clause_llm(
    clause: Clause,
    llm: Optional["ChatOpenAI"] = None,
    fallback: bool = True,
) -> dict:
    """LLM-based extraction with rule-based fallback.

    This is an optional enhancement. Rule-based extraction is the primary path.
    LLM is only used when explicitly called and available.
    """
    if llm is None:
        logger.info("No LLM provided, using rule-based extraction")
        return extract_from_clause(clause)

    try:
        from langchain_openai import ChatOpenAI

        prompt = _build_llm_prompt(clause)
        response = llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        data = json.loads(_clean_json(raw))
        return _parse_llm_result(data, clause)
    except Exception as exc:
        logger.warning("LLM extraction failed, falling back to rules: %s", exc)
        if fallback:
            return extract_from_clause(clause)
        return {
            "requirements": [], "indicators": [], "terms": [],
            "methods": [], "objects": [], "error": str(exc),
        }


def _build_llm_prompt(clause: Clause) -> list:
    return [
        ("system", _LLM_EXTRACTION_PROMPT),
        ("user", f"条款 {clause.clause_number}: {clause.content}"),
    ]


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1:]
        else:
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _parse_llm_result(data: dict, clause: Clause) -> dict:
    """Parse LLM JSON output into model objects (with fallback-friendly defaults)."""
    result: dict = {
        "requirements": [], "indicators": [], "terms": [],
        "methods": [], "objects": [],
    }
    for r in data.get("requirements", []):
        if r.get("text"):
            result["requirements"].append(Requirement(
                clause_id=clause.clause_id, text=r["text"],
                obligation=Obligation(r.get("obligation", "shall")),
                confidence=0.8,
            ))
    for i in data.get("indicators", []):
        if i.get("name"):
            result["indicators"].append(Indicator(
                name=i["name"], value=str(i.get("value", "")),
                operator=i.get("operator", ""), unit=i.get("unit", ""),
                source_clause_id=clause.clause_id,
            ))
    for t in data.get("terms", []):
        if t.get("name") and t.get("definition"):
            result["terms"].append(Term(
                name=t["name"], definition=t["definition"],
                source_clause_id=clause.clause_id,
            ))
    return result


_LLM_EXTRACTION_PROMPT = """你是一个行业标准知识抽取专家。从给定的标准条款中抽取结构化知识。

返回严格的 JSON：
{
  "requirements": [
    {"text": "要求条文原文", "obligation": "shall|should|may"}
  ],
  "indicators": [
    {"name": "指标名", "value": "数值", "operator": ">=|<=|>|<|=", "unit": "单位"}
  ],
  "terms": [
    {"name": "术语名", "definition": "定义原文"}
  ]
}

注意：只抽取原文明确出现的内容，不要编造。只返回 JSON。"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _classify_requirement_type(text: str) -> RequirementType:
    if any(w in text for w in ["安全", "危害", "危险", "防护", "事故"]):
        return RequirementType.SAFETY
    if any(w in text for w in ["管理", "制度", "组织", "培训", "档案"]):
        return RequirementType.MANAGEMENT
    if any(w in text for w in ["环境", "生态", "水土", "排放"]):
        return RequirementType.ENVIRONMENTAL
    if any(w in text for w in ["质量", "合格", "检验", "验收"]):
        return RequirementType.QUALITY
    if any(w in text for w in ["计算", "测量", "监测", "评估", "系数", "参数", "指标"]):
        return RequirementType.TECHNICAL
    return RequirementType.OTHER


# ── Unified extractor with optional NER/RE models ────────────────────────────

class StandardGraphExtractor:
    """Unified knowledge extractor for industry standard documents.

    Wraps rule-based extraction and optionally integrates NER and RE
    deep learning models. Defaults to rule-based — no model weights needed.

    Usage:
        # Pure rule-based (default)
        extractor = StandardGraphExtractor()
        result = extractor.extract_from_clauses(clauses)

        # With deep learning models (falls back to rule if unavailable)
        extractor = StandardGraphExtractor(
            ner_model_type="bert_bilstm_crf",
            ner_model_path="models/ner/bert_bilstm_crf.pt",
            re_model_type="casrel",
            re_model_path="models/re/casrel.pt",
        )
        result = extractor.extract_from_clauses(clauses)
    """

    def __init__(
        self,
        ner_model_type: str = "rule",
        ner_model_path: Optional[str] = None,
        re_model_type: str = "rule",
        re_model_path: Optional[str] = None,
    ):
        self.ner_model_type = ner_model_type
        self.ner_model_path = ner_model_path
        self.re_model_type = re_model_type
        self.re_model_path = re_model_path

        self._ner_predictor = None
        self._re_predictor = None

        try:
            from .ner.predictor import NERPredictor
            self._ner_predictor = NERPredictor(
                model_type=ner_model_type,
                model_path=ner_model_path,
            )
        except Exception as exc:
            logger.warning("Failed to init NERPredictor (%s); NER disabled", exc)

        try:
            from .re.predictor import RelationPredictor
            self._re_predictor = RelationPredictor(
                model_type=re_model_type,
                model_path=re_model_path,
            )
        except Exception as exc:
            logger.warning("Failed to init RelationPredictor (%s); RE disabled", exc)

    def extract_from_clause(self, clause: Clause) -> dict:
        """Extract knowledge from a single clause.

        Uses NER predictor if available, otherwise falls back to rule extraction.
        """
        # Get rule-based extraction as baseline
        result = extract_from_clause(clause)

        # NER: augment with entity extraction (does not replace rule extraction)
        if self._ner_predictor is not None:
            try:
                entities = self._ner_predictor.predict(clause.content)
                # Store extracted entities in result for reference
                result["_ner_entities"] = entities
            except Exception as exc:
                logger.debug("NER prediction failed for clause %s: %s", clause.clause_id, exc)

        # RE: augment with relation extraction
        if self._re_predictor is not None:
            try:
                relations = self._re_predictor.predict_from_clause(
                    clause.content, clause.clause_number,
                )
                result["_re_relations"] = relations
            except Exception as exc:
                logger.debug("RE prediction failed for clause %s: %s", clause.clause_id, exc)

        return result

    def extract_from_standard(self, clauses: list[Clause]) -> dict:
        """Extract knowledge from all clauses of a standard."""
        all_results = extract_from_standard(clauses)

        # Augment with structural relations from RE predictor
        if self._re_predictor is not None and clauses:
            try:
                std_id = clauses[0].standard_id
                ch_map = sorted(set(
                    (cl.chapter_id or "", cl.chapter_id or "")
                    for cl in clauses if cl.chapter_id
                ))
                cl_map = [(cl.clause_number, cl.clause_id, cl.chapter_id)
                          for cl in clauses]
                struct_rels = self._re_predictor.predict_structural(
                    std_id, ch_map, cl_map,
                )
                all_results["_re_structural_relations"] = struct_rels
            except Exception as exc:
                logger.debug("Structural RE failed: %s", exc)

        return all_results
