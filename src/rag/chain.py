import time
import logging
import json
import math
from typing import List, Iterator, Optional
from urllib.error import URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen

from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from config import (
    LLM_PROVIDER, LLM_TEMPERATURE, LLM_MAX_TOKENS,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    LOCAL_LLM_BASE_URL, LOCAL_LLM_MODEL, MAX_HISTORY_TURNS,
    validate_llm_config,
)

logger = logging.getLogger(__name__)

_last_usage: Optional[dict] = None

SYSTEM_PROMPT = """你是一个灾害信息知识助手。你有两个信息来源：
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

USER_PROMPT = "用户问题：{question}\n\n请直接用中文回答："

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
    # Qwen GGUF local mode benefits from /no_think; DeepSeek must receive a clean prompt.
    prefix = "/no_think\n" if LLM_PROVIDER == "local" else ""
    system_with_history = SYSTEM_PROMPT.replace("{history}", history)
    return ChatPromptTemplate.from_messages([
        ("system", prefix + system_with_history),
        ("user", prefix + USER_PROMPT),
    ])


def current_llm_base_url() -> str:
    return DEEPSEEK_BASE_URL if LLM_PROVIDER == "deepseek" else LOCAL_LLM_BASE_URL


def current_llm_model() -> str:
    return DEEPSEEK_MODEL if LLM_PROVIDER == "deepseek" else LOCAL_LLM_MODEL


def create_llm() -> ChatOpenAI:
    validate_llm_config()

    if LLM_PROVIDER == "deepseek":
        return ChatOpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            model=DEEPSEEK_MODEL,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            timeout=60,
            stream_usage=True,
        )

    if LLM_PROVIDER == "local":
        return ChatOpenAI(
            api_key="not-needed",
            base_url=LOCAL_LLM_BASE_URL,
            model=LOCAL_LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            timeout=60,
            stream_usage=True,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is not None:
        return _llm

    _llm = create_llm()
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


def _empty_usage(elapsed_seconds: float) -> dict:
    return {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "tokens_per_second": None,
        "max_tokens": LLM_MAX_TOKENS,
        "llm_base_url": current_llm_base_url(),
        "llm_provider": LLM_PROVIDER,
        "llm_model": current_llm_model(),
        "usage_source": None,
        "usage_estimated": False,
    }


def _usage_from_token_usage(token_usage: dict, elapsed_seconds: float) -> dict:
    usage = _empty_usage(elapsed_seconds)
    usage["prompt_tokens"] = (
        token_usage.get("input_tokens")
        or token_usage.get("prompt_tokens")
    )
    usage["completion_tokens"] = (
        token_usage.get("output_tokens")
        or token_usage.get("completion_tokens")
    )
    usage["total_tokens"] = token_usage.get("total_tokens")
    if usage["total_tokens"] is None and usage["prompt_tokens"] is not None and usage["completion_tokens"] is not None:
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    if usage["completion_tokens"] and elapsed_seconds > 0:
        usage["tokens_per_second"] = round(
            usage["completion_tokens"] / elapsed_seconds, 1
        )
    usage["usage_source"] = "api"
    return usage


def _extract_token_usage(response: AIMessage) -> Optional[dict]:
    token_usage = None
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        token_usage = response.usage_metadata
    elif hasattr(response, "response_metadata") and response.response_metadata:
        token_usage = response.response_metadata.get("token_usage")
    return token_usage


def _extract_usage(response: AIMessage, elapsed_seconds: float) -> dict:
    """Extract token usage from an AIMessage, gracefully handling missing data."""
    token_usage = _extract_token_usage(response)
    if token_usage:
        return _usage_from_token_usage(token_usage, elapsed_seconds)
    return _empty_usage(elapsed_seconds)


def _llama_tokenize_url() -> str:
    parsed = urlparse(LOCAL_LLM_BASE_URL)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    path = f"{path}/tokenize" if path else "/tokenize"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _count_tokens_with_llama(text: str) -> Optional[int]:
    """Count tokens through llama.cpp server's /tokenize endpoint when available."""
    if not text:
        return 0
    if LLM_PROVIDER != "local":
        return None

    request = Request(
        _llama_tokenize_url(),
        data=json.dumps({"content": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        logger.debug("llama.cpp token counting failed: %s", exc)
        return None

    tokens = payload.get("tokens")
    if isinstance(tokens, list):
        return len(tokens)
    n_tokens = payload.get("n_tokens")
    if isinstance(n_tokens, int):
        return n_tokens
    return None


def _estimate_tokens(text: str) -> int:
    """Last-resort rough estimate for mixed Chinese/English text."""
    if not text:
        return 0
    cjk_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other_chars = len(text) - cjk_chars
    return max(1, math.ceil(cjk_chars * 0.9 + other_chars / 4))


def _messages_to_token_text(messages: List[BaseMessage]) -> str:
    parts = []
    for message in messages:
        role = getattr(message, "type", "message")
        parts.append(f"{role}: {message.content}")
    return "\n".join(parts)


def _fallback_usage(
    messages: List[BaseMessage],
    response_text: str,
    elapsed_seconds: float,
) -> dict:
    prompt_text = _messages_to_token_text(messages)
    prompt_tokens = _count_tokens_with_llama(prompt_text)
    completion_tokens = _count_tokens_with_llama(response_text)
    source = "llama_tokenize"
    estimated = False

    if prompt_tokens is None:
        prompt_tokens = _estimate_tokens(prompt_text)
        source = "estimated"
        estimated = True
    if completion_tokens is None:
        completion_tokens = _estimate_tokens(response_text)
        source = "estimated"
        estimated = True

    usage = _empty_usage(elapsed_seconds)
    usage["prompt_tokens"] = prompt_tokens
    usage["completion_tokens"] = completion_tokens
    usage["total_tokens"] = prompt_tokens + completion_tokens
    if completion_tokens and elapsed_seconds > 0:
        usage["tokens_per_second"] = round(
            completion_tokens / elapsed_seconds, 1
        )
    usage["usage_source"] = source
    usage["usage_estimated"] = estimated
    return usage


def _log_usage(usage: dict) -> None:
    logger.info(
        "LLM usage: prompt_tokens=%s, completion_tokens=%s, total_tokens=%s, "
        "elapsed_seconds=%s, tokens_per_second=%s, usage_source=%s",
        usage["prompt_tokens"],
        usage["completion_tokens"],
        usage["total_tokens"],
        usage["elapsed_seconds"],
        usage["tokens_per_second"],
        usage.get("usage_source"),
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
    messages = prompt.format_messages(context=context, question=query)

    start_time = time.time()
    response = llm.invoke(messages)
    elapsed = time.time() - start_time

    usage = _extract_usage(response, elapsed)
    if usage["prompt_tokens"] is None and usage["completion_tokens"] is None:
        usage = _fallback_usage(messages, response.content, elapsed)
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
    messages = prompt.format_messages(context=context, question=query)

    start_time = time.time()
    full_chunks: list[AIMessage] = []
    response_parts: list[str] = []

    for chunk in llm.stream(messages):
        full_chunks.append(chunk)
        content = chunk.content
        if content:
            response_parts.append(content)
            yield content

    elapsed = time.time() - start_time

    usage_chunk = next(
        (chunk for chunk in reversed(full_chunks) if _extract_token_usage(chunk)),
        None,
    )
    if usage_chunk is not None:
        _last_usage = _extract_usage(usage_chunk, elapsed)
    else:
        _last_usage = _fallback_usage(messages, "".join(response_parts), elapsed)

    _log_usage(_last_usage)
