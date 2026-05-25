"""Multi-source retrieval with query rewriting, reranking, and relevance filtering."""

import logging
from typing import List, Tuple

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel

from src.vectorstore.chroma_store import retrieve_with_scores
from config import (
    COLLECTION_DOCS,
    COLLECTION_EVENTS,
    RETRIEVAL_PREFETCH,
    RELEVANCE_THRESHOLD,
    RERANK_TOP_K,
    ENABLE_QUERY_REWRITE,
)

logger = logging.getLogger(__name__)

_reranker = None
_last_retrieval_errors: list[str] = []


def get_last_retrieval_errors() -> list[str]:
    return list(_last_retrieval_errors)


def _get_reranker():
    global _reranker
    if _reranker is not None:
        return _reranker

    try:
        from flashrank import Ranker, RerankRequest
        _reranker = Ranker()
        return _reranker
    except ImportError:
        logger.warning("flashrank 未安装，跳过重排序")
        return None


def _rerank(query: str, docs: List[Document]) -> List[Document]:
    """Rerank documents by cross-encoder relevance to the query."""
    if len(docs) <= RERANK_TOP_K:
        return docs

    ranker = _get_reranker()
    if ranker is None:
        return docs[:RERANK_TOP_K]

    try:
        from flashrank import RerankRequest
        passages = [{"id": i, "text": d.page_content} for i, d in enumerate(docs)]
        request = RerankRequest(query=query, passages=passages)
        results = ranker.rerank(request)
        top_indices = [r["id"] for r in results[:RERANK_TOP_K]]
        return [docs[i] for i in top_indices]
    except Exception as e:
        logger.warning("重排序失败: %s，使用原始排序", e)
        return docs[:RERANK_TOP_K]


def _filter_by_threshold(
    docs_with_scores: List[Tuple[Document, float]],
    threshold: float = RELEVANCE_THRESHOLD,
) -> List[Document]:
    """Filter out documents below the relevance threshold.

    ChromaDB returns L2 distance here, so lower is better.
    """
    filtered = []
    for doc, score in docs_with_scores:
        if score <= threshold:
            filtered.append(doc)
    return filtered


def rewrite_query(query: str, llm: BaseChatModel) -> str:
    """Rewrite the user query into a more search-friendly form.

    E.g. "最近有地震吗" → "2026年5月 最近地震事件 USGS"
    """
    if not ENABLE_QUERY_REWRITE:
        return query

    if not query.strip():
        return query

    prompt = (
        "你是一个搜索查询优化器。将用户问题改写为更精确、更具体的关键词组合，"
        "便于向量检索引擎在海量文档中找到最相关的结果。\n"
        "规则：\n"
        "- 扩展缺失的时间、地点、类型信息\n"
        "- 添加同义词或相关术语\n"
        "- 仅返回改写后的查询词，不要加任何解释\n\n"
        f"用户问题: {query}\n改写后的检索词:"
    )

    try:
        resp = llm.bind(max_tokens=128).invoke(prompt)
        rewritten = resp.content.strip().strip('"').strip("'")
        if rewritten and len(rewritten) >= 2:
            logger.info("查询改写: %s → %s", query, rewritten)
            return rewritten
    except Exception as e:
        logger.warning("查询改写失败: %s", e)

    return query


def retrieve_from_docs(query: str, k: int = RETRIEVAL_PREFETCH) -> List[Document]:
    """Retrieve + rerank + filter local documents."""
    try:
        results = retrieve_with_scores(query, COLLECTION_DOCS, k=k)
        docs = _filter_by_threshold(results)
        docs = _rerank(query, docs)
        return docs
    except Exception as e:
        logger.warning("本地文档检索失败: %s", e)
        _last_retrieval_errors.append(f"本地文档检索失败: {e}")
        return []


def retrieve_from_events(query: str, k: int = RETRIEVAL_PREFETCH) -> List[Document]:
    """Retrieve + rerank + filter disaster events."""
    try:
        results = retrieve_with_scores(query, COLLECTION_EVENTS, k=k)
        docs = _filter_by_threshold(results)
        docs = _rerank(query, docs)
        return docs
    except Exception as e:
        logger.warning("实时事件检索失败: %s", e)
        _last_retrieval_errors.append(f"实时事件检索失败: {e}")
        return []


def retrieve_all(
    query: str,
    enable_docs: bool = True,
    enable_events: bool = True,
    llm: BaseChatModel = None,
) -> List[Document]:
    """Retrieve from all enabled sources with full pipeline.

    Pipeline: rewrite query → retrieve with scores → threshold filter → rerank
    """
    _last_retrieval_errors.clear()

    # Step 0: query rewriting
    search_query = query
    if llm is not None and ENABLE_QUERY_REWRITE:
        search_query = rewrite_query(query, llm)

    results: List[Document] = []

    if enable_docs:
        docs = retrieve_from_docs(search_query)
        for d in docs:
            d.metadata["source_label"] = "[文档]"
        results.extend(docs)

    if enable_events:
        events = retrieve_from_events(search_query)
        for d in events:
            d.metadata["source_label"] = "[实时]"
        results.extend(events)

    # Deduplicate by content
    seen = set()
    unique = []
    for d in results:
        if d.page_content not in seen:
            seen.add(d.page_content)
            unique.append(d)
    return unique
