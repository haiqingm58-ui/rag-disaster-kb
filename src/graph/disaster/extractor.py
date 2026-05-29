"""LLM-based extraction of DisasterEvent and Attribute from news text.

Uses the project's existing LLM infrastructure (DeepSeek or local) to extract
structured disaster event data from unstructured Chinese news articles.
Includes a rule-based regex fallback for when the LLM is unavailable or fails.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Optional

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

from .models import (
    DisasterEvent,
    Attribute,
    Location,
    SourceDocument,
    DisasterType,
    EventStatus,
    AttrCategory,
    DataType,
    _new_id,
)

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """你是一个灾害信息抽取专家。你的任务是从新闻文本中精确抽取灾害事件的结构化信息。

请从以下新闻文本中抽取信息，并以严格的 JSON 格式返回。如果某个字段无法从文本中确定，使用 null。

返回的 JSON 结构如下：
```json
{
  "event": {
    "name": "灾害事件简短名称（如：云南漾濞5.2级地震）",
    "disaster_type": "earthquake|flood|landslide|mudflow|typhoon|wildfire|drought|volcano|tsunami|other",
    "start_time": "ISO 8601 格式时间，如 2026-05-20T08:30:00",
    "end_time": "ISO 8601 或 null",
    "status": "ongoing|concluded|unconfirmed",
    "summary": "对事件的1-3句简要总结",
    "confidence": 0.0-1.0 之间的数值，表示抽取的可信度
  },
  "attributes": [
    {
      "key": "属性名（英文下划线命名，如 magnitude, casualties_death, affected_area_km2）",
      "value": "属性值",
      "unit": "单位（如 Mw, 人, km2, 万元）或 null",
      "category": "magnitude|casualties|economic_loss|evacuation|rescue|environment|warning|other",
      "data_type": "string|number|boolean|datetime"
    }
  ],
  "location": {
    "name": "具体地点名称",
    "latitude": 数值或 null,
    "longitude": 数值或 null,
    "address": "详细地址或 null",
    "country": "国家或 null"
  },
  "source_document": {
    "title": "文档标题（可从新闻标题提取）",
    "url": null,
    "source_type": "news|report|social_media|other",
    "publish_time": "ISO 8601 或 null",
    "content_snippet": "原文中与灾害相关的关键句段摘录（限制200字）"
  }
}
```

注意事项：
- 只抽取真实出现在文本中的信息，不要编造
- 震级 magnitude 使用 Mw 震级标度
- 伤亡人数分为 casualties_death（死亡）和 casualties_injured（受伤）
- 如果同一类属性有多个（如同时有死亡和受伤人数），分别创建多个 attribute
- 时间统一使用 ISO 8601 格式
- confidence 根据信息完整度和明确程度判断：明确数字 0.9+，模糊描述 0.6-0.8，推断 0.3-0.5"""

EXTRACTION_USER_PROMPT = """请从以下新闻文本中抽取灾害事件信息：

---
{text}
---

请只返回 JSON，不要加任何解释或 markdown 代码块标记。"""


# ── Rule-based extraction patterns (fallback) ──────────────────────────────────

_MAGNITUDE_PATTERNS = [
    re.compile(r"(\d+\.?\d*)\s*级"),                       # 5.2级
    re.compile(r"[面里]氏\s*(\d+\.?\d*)"),                   # 里氏5.2
    re.compile(r"[震震]级[约为]?\s*(\d+\.?\d*)"),            # 震级5.2
    re.compile(r"[Mm][wWsS]?\s*(\d+\.?\d*)"),              # Mw5.2, Ms5.2
    re.compile(r"magnitude\s*(\d+\.?\d*)", re.IGNORECASE),
]

_CASUALTY_DEATH_PATTERNS = [
    re.compile(r"(\d+)\s*人\s*死[死亡亡]"),
    re.compile(r"死亡\s*(\d+)\s*人"),
    re.compile(r"遇难\s*(\d+)\s*人"),
    re.compile(r"(\d+)\s*人\s*遇难"),
    re.compile(r"(\d+)\s*人\s*罹难"),
]

_CASUALTY_INJURED_PATTERNS = [
    re.compile(r"(\d+)\s*人\s*受[伤傷]"),
    re.compile(r"受[伤傷]\s*(\d+)\s*人"),
    re.compile(r"(\d+)\s*[名位]?\s*伤[者員]"),
]

_EVACUATION_PATTERNS = [
    re.compile(r"(?:转移安置|紧急转移|疏散|转移)\s*(\d+\.?\d*)\s*[万]?\s*人"),
    re.compile(r"(\d+\.?\d*)\s*[万]?\s*人\s*(?:被)?\s*(?:紧急)?\s*(?:转移|疏散)"),
]

_DISASTER_TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("earthquake", ["地震", "震源", "震中", "余震", "震感", "里氏", "震级"]),
    ("flood", ["洪水", "洪涝", "洪灾", "暴雨", "水灾", "溃堤", "决口"]),
    ("landslide", ["滑坡", "山体滑坡", "塌方", "崩塌"]),
    ("mudflow", ["泥石流"]),
    ("typhoon", ["台风", "飓风", "热带风暴", "气旋"]),
    ("wildfire", ["山火", "森林火灾", "林火", "草原火灾"]),
    ("drought", ["干旱", "旱灾", "旱情", "缺水"]),
    ("volcano", ["火山", "火山喷发", "岩浆"]),
    ("tsunami", ["海啸", "津浪"]),
]

_TIME_PATTERNS = [
    re.compile(r"(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})[日]?\s*(\d{1,2})?[：:]*(\d{1,2})?[：:]*(\d{1,2})?"),
    re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?)"),
]

_LOCATION_CHINESE = re.compile(
    r"[一-鿿]{2,10}(?:省|市|自治区|自治州|县|区|镇|乡|村)"
)


def _try_match_number(patterns: list[re.Pattern], text: str) -> Optional[float]:
    for pat in patterns:
        m = pat.search(text)
        if m:
            return float(m.group(1))
    return None


def _classify_disaster_type(text: str) -> str:
    """Classify disaster type by keyword matching."""
    for dtype, keywords in _DISASTER_TYPE_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return dtype
    return "other"


def _extract_time(text: str) -> Optional[str]:
    """Extract the first datetime from text, returning ISO 8601 string or None."""
    # Try ISO format first
    for pat in _TIME_PATTERNS:
        m = pat.search(text)
        if m:
            groups = m.groups()
            if len(groups) >= 3:
                year = int(groups[0])
                month = int(groups[1])
                day = int(groups[2])
                hour = int(groups[3]) if len(groups) > 3 and groups[3] else 0
                minute = int(groups[4]) if len(groups) > 4 and groups[4] else 0
                second = int(groups[5]) if len(groups) > 5 and groups[5] else 0
                try:
                    return datetime(year, month, day, hour, minute, second).isoformat()
                except ValueError:
                    pass
    return None


def _extract_location_name(text: str) -> Optional[str]:
    m = _LOCATION_CHINESE.search(text)
    return m.group(0) if m else None


def _rule_extract(text: str) -> dict:
    """Rule-based extraction fallback when LLM is unavailable.

    Uses regex patterns to extract magnitude, casualties, evacuation counts,
    location, time, and disaster type from Chinese disaster news text.
    """
    result: dict = {
        "event": None,
        "attributes": [],
        "location": None,
        "source_document": None,
        "raw_json": None,
        "error": "",
        "method": "rule",
    }

    disaster_type = _classify_disaster_type(text)
    time_str = _extract_time(text)
    loc_name = _extract_location_name(text)

    # Build event name
    loc_part = loc_name or "未知地点"
    type_labels = {
        "earthquake": "地震", "flood": "洪水", "landslide": "滑坡",
        "mudflow": "泥石流", "typhoon": "台风", "wildfire": "火灾",
        "drought": "干旱", "volcano": "火山喷发", "tsunami": "海啸", "other": "灾害",
    }
    type_label = type_labels.get(disaster_type, "灾害")
    mag = _try_match_number(_MAGNITUDE_PATTERNS, text)
    name = f"{loc_part}{mag}{type_label}" if mag else f"{loc_part}{type_label}"

    start_time = None
    if time_str:
        try:
            start_time = datetime.fromisoformat(time_str)
        except ValueError:
            pass

    confidence = 0.5 if (mag or loc_name) else 0.3

    result["event"] = DisasterEvent(
        name=name,
        disaster_type=DisasterType(disaster_type),
        start_time=start_time,
        status=EventStatus.UNCONFIRMED,
        summary=text[:300],
        confidence=confidence,
    )

    event_id = result["event"].event_id

    if mag:
        result["attributes"].append(Attribute(
            event_id=event_id, key="magnitude", value=str(mag),
            unit="Mw", category=AttrCategory.MAGNITUDE, data_type=DataType.NUMBER,
            source="rule_extraction",
        ))

    deaths = _try_match_number(_CASUALTY_DEATH_PATTERNS, text)
    if deaths:
        result["attributes"].append(Attribute(
            event_id=event_id, key="casualties_death", value=str(int(deaths)),
            unit="人", category=AttrCategory.CASUALTIES, data_type=DataType.NUMBER,
            source="rule_extraction",
        ))

    injured = _try_match_number(_CASUALTY_INJURED_PATTERNS, text)
    if injured:
        result["attributes"].append(Attribute(
            event_id=event_id, key="casualties_injured", value=str(int(injured)),
            unit="人", category=AttrCategory.CASUALTIES, data_type=DataType.NUMBER,
            source="rule_extraction",
        ))

    evacuated = _try_match_number(_EVACUATION_PATTERNS, text)
    if evacuated:
        result["attributes"].append(Attribute(
            event_id=event_id, key="evacuated", value=str(int(evacuated)),
            unit="人", category=AttrCategory.EVACUATION, data_type=DataType.NUMBER,
            source="rule_extraction",
        ))

    if loc_name:
        result["location"] = Location(name=loc_name, latitude=0.0, longitude=0.0)

    result["source_document"] = SourceDocument(
        title=name, source_type="news", content_snippet=text[:200],
    )

    logger.info(
        "Rule extraction: event='%s', type=%s, %d attributes",
        name, disaster_type, len(result["attributes"]),
    )
    return result


# ── Public API ─────────────────────────────────────────────────────────────────

def _build_extraction_llm():
    """Create an LLM instance with extraction-optimized settings."""
    from langchain_openai import ChatOpenAI
    from config import (
        LLM_PROVIDER, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
        LOCAL_LLM_BASE_URL, LOCAL_LLM_MODEL, validate_llm_config,
    )

    validate_llm_config()

    if LLM_PROVIDER == "deepseek":
        return ChatOpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            model=DEEPSEEK_MODEL,
            temperature=0.0,
            max_tokens=2048,
            timeout=90,
        )

    return ChatOpenAI(
        api_key="not-needed",
        base_url=LOCAL_LLM_BASE_URL,
        model=LOCAL_LLM_MODEL,
        temperature=0.0,
        max_tokens=2048,
        timeout=90,
    )


def _clean_json_response(text: str) -> str:
    """Strip markdown code fences and leading/trailing whitespace."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        else:
            text = text[3:]  # No newline: just strip the ```
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _safe_parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        logger.debug("Failed to parse datetime: %s", value)
        return None


def _parse_llm_result(data: dict) -> dict:
    """Parse the LLM JSON output into typed model objects."""
    result: dict = {
        "event": None,
        "attributes": [],
        "location": None,
        "source_document": None,
    }

    evt_data = data.get("event", {})
    if evt_data and evt_data.get("name"):
        result["event"] = DisasterEvent(
            name=evt_data.get("name", ""),
            disaster_type=DisasterType(evt_data.get("disaster_type", "other")),
            start_time=_safe_parse_datetime(evt_data.get("start_time")),
            end_time=_safe_parse_datetime(evt_data.get("end_time")),
            status=EventStatus(evt_data.get("status", "unconfirmed")),
            summary=evt_data.get("summary", ""),
            confidence=float(evt_data.get("confidence", 0.5)),
        )

    event_id = result["event"].event_id if result["event"] else _new_id("evt")
    for attr_data in data.get("attributes", []):
        if attr_data.get("key") and attr_data.get("value") is not None:
            result["attributes"].append(Attribute(
                event_id=event_id,
                key=attr_data["key"],
                value=str(attr_data["value"]),
                unit=attr_data.get("unit"),
                category=AttrCategory(attr_data.get("category", "other")),
                data_type=DataType(attr_data.get("data_type", "string")),
            ))

    loc_data = data.get("location", {})
    if loc_data and loc_data.get("name"):
        result["location"] = Location(
            name=loc_data.get("name", ""),
            latitude=loc_data.get("latitude") or 0.0,
            longitude=loc_data.get("longitude") or 0.0,
            address=loc_data.get("address"),
            country=loc_data.get("country"),
        )

    doc_data = data.get("source_document", {})
    if doc_data and doc_data.get("title"):
        result["source_document"] = SourceDocument(
            title=doc_data.get("title", ""),
            url=doc_data.get("url"),
            source_type=doc_data.get("source_type", "news"),
            publish_time=_safe_parse_datetime(doc_data.get("publish_time")),
            content_snippet=doc_data.get("content_snippet", ""),
        )

    return result


def extract_from_news(
    text: str,
    llm: Optional[ChatOpenAI] = None,
    fallback: bool = True,
) -> dict:
    """Extract DisasterEvent and Attributes from a Chinese news article.

    Args:
        text: The news article text (Chinese).
        llm: Optional pre-configured ChatOpenAI instance. If None, one is created.
        fallback: If True, fall back to rule-based extraction when LLM fails.

    Returns:
        dict with keys:
          - "event": DisasterEvent or None
          - "attributes": list[Attribute]
          - "location": Location or None
          - "source_document": SourceDocument or None
          - "raw_json": the raw parsed JSON from the LLM (None for rule extraction)
          - "error": error message string (empty if successful)
          - "method": "llm" or "rule" or "none"
    """
    if not text or not text.strip():
        return {
            "event": None, "attributes": [], "location": None,
            "source_document": None, "raw_json": None,
            "error": "Empty input text", "method": "none",
        }

    # ── Try LLM extraction ──
    try:
        llm_instance = llm or _build_extraction_llm()
        response = llm_instance.invoke([
            ("system", EXTRACTION_SYSTEM_PROMPT),
            ("user", EXTRACTION_USER_PROMPT.format(text=text)),
        ])
        raw_text = response.content if hasattr(response, "content") else str(response)
        cleaned = _clean_json_response(raw_text)
        data = json.loads(cleaned)
    except Exception as exc:
        logger.warning("LLM extraction failed, fallback=%s: %s", fallback, exc)
        if fallback:
            fb_result = _rule_extract(text)
            fb_result["error"] = f"LLM failed, used rule fallback: {exc}"
            return fb_result
        return {
            "event": None, "attributes": [], "location": None,
            "source_document": None, "raw_json": None,
            "error": f"LLM call failed: {exc}", "method": "none",
        }

    # ── Parse LLM JSON ──
    result = _parse_llm_result(data)
    result["raw_json"] = data
    result["error"] = ""

    # If LLM returned nothing useful and fallback is on, try rules
    if fallback and result["event"] is None:
        logger.info("LLM returned empty result, trying rule fallback")
        fb_result = _rule_extract(text)
        fb_result["error"] = "LLM returned no event, used rule fallback"
        fb_result["raw_json"] = data
        return fb_result

    result["method"] = "llm"
    logger.info(
        "LLM extraction: event='%s', %d attributes, location='%s'",
        result["event"].name if result["event"] else "None",
        len(result["attributes"]),
        result["location"].name if result["location"] else "None",
    )
    return result
