import time
import logging
from typing import List, Iterator, Optional

from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage

from config import (
    LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS,
    OPENAI_API_KEY, OPENAI_BASE_URL, MAX_HISTORY_TURNS,
)

logger = logging.getLogger(__name__)

_last_usage: Optional[dict] = None

SYSTEM_PROMPT = """/no_think
你是一个灾害信息知识助手。你有两个信息来源：
1. 本地专业知识文档（通过向量检索获取的相关片段）
2. 实时灾害数据（来自 CENC records via Wolfx mirror、USGS 地震监测和 GDACS 全球灾害预警系统）

请根据以下检索到的上下文回答用户问题。回答规则：
- 优先使用上下文中的信息，准确回答问题
- 如果上下文信息不足，但问题属于通用灾害避险常识，可以基于通用应急知识回答，并明确说明未检索到专门资料
- 如果用户询问“最近/现在/某地是否发生灾害”等实时事实，而上下文没有实时数据，请明确说明无法确认，需要刷新实时数据或查询权威监测源
- 回答末尾标注信息来源：[文档] 表示来自本地知识库，[实时] 表示来自实时灾害API数据，[通用] 表示未命中检索资料时的通用安全建议
- 回答保持简洁、专业，用中文
- 直接给出最终答案，不要输出思考过程、推理过程或 reasoning_content

{history}

上下文：
{context}"""

USER_PROMPT = "/no_think\n用户问题：{question}\n\n请直接用中文回答："

_llm: Optional[ChatOpenAI] = None


def _build_context(documents: List[Document]) -> str:
    if not documents:
        return "（无可用上下文）"

    parts = []
    for i, doc in enumerate(documents):
        source_label = doc.metadata.get("source_label", "[未知来源]")
        parts.append(f"[片段{i + 1}]{source_label}\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


def _build_history(messages: List[dict], max_turns: int = MAX_HISTORY_TURNS) -> str:
    """Build conversation history string from recent turns."""
    if not messages:
        return ""

    recent = messages[-(max_turns * 2):]  # each turn = user + assistant
    if not recent:
        return ""

    lines = ["### 对话历史"]
    for m in recent:
        role = "用户" if m["role"] == "user" else "助手"
        content = m.get("content", "")[:500]  # truncate long messages
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _build_prompt(history: str) -> ChatPromptTemplate:
    system_with_history = SYSTEM_PROMPT.replace("{history}", history)
    return ChatPromptTemplate.from_messages([
        ("system", system_with_history),
        ("user", USER_PROMPT),
    ])


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is not None:
        return _llm

    _llm = ChatOpenAI(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
        timeout=60,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return _llm


def get_llm() -> ChatOpenAI:
    """Expose cached LLM instance for query rewriting etc."""
    return _get_llm()


def test_llm_connection() -> bool:
    try:
        llm = _get_llm()
        llm.invoke("ping")
        return True
    except Exception:
        return False


def _extract_usage(response: AIMessage, elapsed_seconds: float) -> dict:
    """Extract token usage from an AIMessage, gracefully handling missing data."""
    usage = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "tokens_per_second": None,
        "max_tokens": LLM_MAX_TOKENS,
        "llm_base_url": OPENAI_BASE_URL,
    }

    token_usage = None
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        token_usage = response.usage_metadata
    elif hasattr(response, "response_metadata") and response.response_metadata:
        token_usage = response.response_metadata.get("token_usage")

    if token_usage:
        usage["prompt_tokens"] = (
            token_usage.get("input_tokens")
            or token_usage.get("prompt_tokens")
        )
        usage["completion_tokens"] = (
            token_usage.get("output_tokens")
            or token_usage.get("completion_tokens")
        )
        usage["total_tokens"] = token_usage.get("total_tokens")
        if usage["completion_tokens"] and elapsed_seconds > 0:
            usage["tokens_per_second"] = round(
                usage["completion_tokens"] / elapsed_seconds, 1
            )

    return usage


def _log_usage(usage: dict) -> None:
    logger.info(
        "LLM usage: prompt_tokens=%s, completion_tokens=%s, total_tokens=%s, "
        "elapsed_seconds=%s, tokens_per_second=%s",
        usage["prompt_tokens"],
        usage["completion_tokens"],
        usage["total_tokens"],
        usage["elapsed_seconds"],
        usage["tokens_per_second"],
    )


def get_last_usage() -> Optional[dict]:
    """Return usage info from the most recent streaming call, if any."""
    return _last_usage


def answer(
    query: str,
    documents: List[Document],
    chat_history: List[dict] = None,
    include_usage: bool = False,
):
    """Answer a query using retrieved documents.

    Args:
        query: User question.
        documents: Retrieved LangChain Documents.
        chat_history: Previous conversation turns.
        include_usage: If True, return (answer_str, usage_dict). If False, return answer_str.

    Returns:
        str, or (str, dict) when include_usage=True.
    """
    context = _build_context(documents)
    history = _build_history(chat_history or [])
    prompt = _build_prompt(history)
    llm = _get_llm()

    chain = prompt | llm
    start_time = time.time()
    response = chain.invoke({"context": context, "question": query})
    elapsed = time.time() - start_time

    usage = _extract_usage(response, elapsed)
    _log_usage(usage)

    if include_usage:
        return response.content, usage
    return response.content


def answer_stream(
    query: str,
    documents: List[Document],
    chat_history: List[dict] = None,
) -> Iterator[str]:
    global _last_usage

    context = _build_context(documents)
    history = _build_history(chat_history or [])
    prompt = _build_prompt(history)
    llm = _get_llm()

    chain = prompt | llm
    start_time = time.time()
    full_chunks: list[AIMessage] = []

    for chunk in chain.stream({"context": context, "question": query}):
        full_chunks.append(chunk)
        content = chunk.content
        if content:
            yield content

    elapsed = time.time() - start_time

    # Try to reconstruct usage from the last chunk's metadata
    last_chunk = full_chunks[-1] if full_chunks else None
    if hasattr(last_chunk, "usage_metadata") and last_chunk.usage_metadata:
        _last_usage = _extract_usage(last_chunk, elapsed)
    else:
        _last_usage = {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "elapsed_seconds": round(elapsed, 2),
            "tokens_per_second": None,
            "max_tokens": LLM_MAX_TOKENS,
            "llm_base_url": OPENAI_BASE_URL,
        }

    _log_usage(_last_usage)
