from __future__ import annotations

import time
import uuid
import logging
from collections import defaultdict
from typing import Any

from langchain_core.documents import Document

from app_server.services.disaster_service import events_for_question
from app_server.services.graph_service import get_graph_service
from src.rag.chain import answer
from src.rag.retriever import retrieve_from_docs


logger = logging.getLogger(__name__)
SESSIONS: dict[str, list[dict[str, str]]] = defaultdict(list)

DISASTER_TERMS = ("滑坡", "崩塌", "泥石流", "地震", "暴雨", "洪水", "台风", "地面塌陷", "地裂缝")
INTENT_WORDS = {
    "定义解释": ("什么是", "定义", "解释", "概念"),
    "预防措施": ("预防", "防治", "治理", "措施"),
    "应急避险": ("避险", "应急", "自救", "逃生"),
    "风险评估": ("风险", "危险性", "评估"),
    "规范条文": ("规范", "标准", "条文", "要求", "指标"),
    "实时查询": ("最近", "附近", "当前", "现在", "预警"),
}


def extract_keywords(question: str) -> dict[str, list[str]]:
    disasters = [term for term in DISASTER_TERMS if term in question]
    intents = [name for name, words in INTENT_WORDS.items() if any(w in question for w in words)]
    return {"disasters": disasters, "intents": intents}


def _doc_sources(docs: list[Document]) -> list[dict[str, Any]]:
    sources = []
    for doc in docs:
        filename = doc.metadata.get("filename") or doc.metadata.get("source", "本地文档")
        sources.append({
            "type": "document",
            "title": filename,
            "content": doc.page_content[:600],
            "score": doc.metadata.get("score"),
            "source": filename,
            "standard": doc.metadata.get("standard") or doc.metadata.get("code"),
            "clause": doc.metadata.get("clause") or doc.metadata.get("clause_number") or doc.metadata.get("number"),
            "snippet": doc.page_content[:240],
        })
    return sources


def _graph_docs(graph_context: list[dict[str, Any]]) -> list[Document]:
    docs = []
    for item in graph_context:
        content = f"【知识图谱】{item.get('type')} {item.get('label')} {item.get('content')}"
        docs.append(Document(page_content=content, metadata={"source_label": "[图谱]", "source": "knowledge_graph"}))
    return docs


def _realtime_docs(events: list[dict[str, Any]]) -> list[Document]:
    docs = []
    for ev in events:
        content = (
            f"【实时灾害】{ev.get('title')}，类型: {ev.get('event_type')}，地点: {ev.get('place')}，"
            f"时间: {ev.get('time')}，风险等级: {ev.get('risk')}，来源: {ev.get('source')}。"
        )
        docs.append(Document(page_content=content, metadata={"source_label": "[实时]", "source": ev.get("source", "")}))
    return docs


def _fallback_evidence_answer(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "当前知识库中没有找到足够依据。请补充标准条款、上传相关文档，或换用更具体的灾害类型、地点和时间范围重新提问。"
    lines = ["当前生成模型暂不可用，以下为基于已检索知识库证据的摘要："]
    for index, source in enumerate(sources[:4], start=1):
        title = source.get("title") or source.get("source") or "参考来源"
        standard = source.get("standard") or source.get("source") or ""
        clause = source.get("clause") or ""
        snippet = (source.get("snippet") or source.get("content") or "").strip()
        ref = " · ".join(item for item in (standard, clause) if item)
        lines.append(f"{index}. {title}{f'（{ref}）' if ref else ''}：{snippet[:220]}")
    lines.append("参考来源已在右侧来源列表中列出。")
    return "\n".join(lines)


def chat(question: str, session_id: str | None, use_graph: bool, use_realtime: bool, top_k: int) -> dict[str, Any]:
    start = time.time()
    sid = session_id or str(uuid.uuid4())
    keywords = extract_keywords(question)
    errors: list[str] = []

    try:
        docs = retrieve_from_docs(question, k=top_k)
    except Exception as exc:
        logger.exception("document retrieval failed")
        docs = []
        errors.append(f"文档检索失败：{exc}")
    for doc in docs:
        doc.metadata["source_label"] = "[文档]"

    try:
        graph_context = get_graph_service().context_for_question(question, limit=top_k) if use_graph else []
    except Exception as exc:
        logger.exception("graph retrieval failed")
        graph_context = []
        errors.append(f"知识图谱检索失败：{exc}")

    try:
        realtime_events = events_for_question(question, limit=top_k) if use_realtime else []
    except Exception as exc:
        logger.exception("realtime event retrieval failed")
        realtime_events = []
        errors.append(f"实时灾害数据检索失败：{exc}")

    evidence = docs + _graph_docs(graph_context) + _realtime_docs(realtime_events)
    sources = _doc_sources(docs)
    sources.extend({
        "type": "graph",
        "title": item.get("label", "知识图谱节点"),
        "content": item.get("content", ""),
        "score": None,
        "source": "知识图谱",
        "standard": item.get("code", ""),
        "clause": item.get("number") or item.get("clause_number"),
        "snippet": item.get("content", "")[:240],
    } for item in graph_context)
    sources.extend({
        "type": "realtime",
        "title": ev.get("title", "实时灾害事件"),
        "content": f"{ev.get('time', '')} {ev.get('place', '')} {ev.get('risk', '')} {ev.get('source', '')}",
        "score": None,
        "source": ev.get("source", ""),
        "standard": None,
        "clause": None,
        "snippet": f"{ev.get('time', '')} {ev.get('place', '')} {ev.get('risk', '')}",
    } for ev in realtime_events)

    augmented_question = (
        f"{question}\n\n"
        f"问题关键词: 灾种={','.join(keywords['disasters']) or '未识别'}; "
        f"意图={','.join(keywords['intents']) or '未识别'}。\n"
        "请综合文档、知识图谱和实时事件证据回答；无证据时不要编造。"
    )
    history = SESSIONS[sid][-6:]
    if not evidence:
        answer_text = "当前知识库中没有找到足够依据。请补充标准条款、上传相关文档，或换用更具体的灾害类型、地点和时间范围重新提问。"
        usage = {}
    else:
        try:
            answer_text, usage = answer(augmented_question, evidence, chat_history=history, include_usage=True)
        except Exception as exc:
            logger.exception("llm answer failed")
            errors.append(f"生成模型不可用：{exc}")
            answer_text = _fallback_evidence_answer(sources)
            usage = {}

    SESSIONS[sid].extend([
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer_text},
    ])

    latency_ms = round((time.time() - start) * 1000)
    logger.info(
        "chat completed session_id=%s latency_ms=%s rag_count=%s graph_count=%s realtime_count=%s errors=%s",
        sid,
        latency_ms,
        len(docs),
        len(graph_context),
        len(realtime_events),
        len(errors),
    )

    return {
        "answer": answer_text,
        "sources": sources or [],
        "graph_context": graph_context or [],
        "realtime_events": realtime_events or [],
        "debug": {
            "session_id": sid,
            "keywords": keywords,
            "retrieval_count": len(docs),
            "graph_count": len(graph_context),
            "realtime_count": len(realtime_events),
            "latency_ms": latency_ms,
            "llm_usage": usage,
            "errors": errors,
        },
    }
