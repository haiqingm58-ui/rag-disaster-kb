"""Chinese disaster term dictionary and simple query expansion."""

from __future__ import annotations

DISASTER_TERMS = {
    "地震": ["地震", "震感", "余震", "震源", "震中", "晃动", "房子摇"],
    "洪水": ["洪水", "涨水", "内涝", "积水", "山洪", "水淹", "被淹"],
    "滑坡": ["滑坡", "塌方", "山体滑坡", "边坡垮塌", "山体塌了"],
    "泥石流": ["泥石流", "沟谷洪流", "山洪泥石流", "泥水冲下来"],
    "台风": ["台风", "气旋", "热带风暴", "大风暴"],
    "野火": ["野火", "山火", "森林火灾", "起火"],
}

ORAL_HINTS = {
    "危险": ["风险", "灾害", "预警", "附近"],
    "怎么办": ["应急", "避险", "自救"],
    "附近": ["当前位置", "周边", "半径"],
}


def detect_disaster_types(query: str) -> list[str]:
    matches = []
    for disaster_type, terms in DISASTER_TERMS.items():
        if any(term in query for term in terms):
            matches.append(disaster_type)
    return matches


def expand_query_with_terms(query: str) -> str:
    additions: list[str] = []
    for disaster_type in detect_disaster_types(query):
        additions.append(disaster_type)
        additions.extend(DISASTER_TERMS[disaster_type])

    for hint, terms in ORAL_HINTS.items():
        if hint in query:
            additions.extend(terms)

    deduped = []
    seen = set()
    for term in additions:
        if term not in seen and term not in query:
            seen.add(term)
            deduped.append(term)

    if not deduped:
        return query
    return f"{query} {' '.join(deduped)}"
