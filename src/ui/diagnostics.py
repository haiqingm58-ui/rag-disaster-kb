"""Small runtime diagnostics used for friendly Streamlit error messages."""

from urllib.parse import urlparse

import requests

from config import (
    LLM_PROVIDER,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    LOCAL_LLM_BASE_URL,
    LOCAL_LLM_MODEL_PATH,
    OLLAMA_BASE_URL,
    OLLAMA_EMBED_MODEL,
)


def check_ollama_model(model: str = OLLAMA_EMBED_MODEL) -> dict:
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        resp = requests.get(url, timeout=3)
        resp.raise_for_status()
        names = [m.get("name", "") for m in resp.json().get("models", [])]
        return {
            "available": True,
            "model_installed": model in names,
            "models": names,
            "error": "",
        }
    except Exception as e:
        return {
            "available": False,
            "model_installed": False,
            "models": [],
            "error": str(e),
        }


def check_llm_server() -> dict:
    base = LOCAL_LLM_BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = f"{base}/v1/models"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return {"available": True, "url": url, "error": ""}
    except Exception as e:
        return {"available": False, "url": url, "error": str(e)}


def format_embedding_error(error: Exception) -> str:
    status = check_ollama_model()
    lines = [
        "Embedding 生成失败，无法完成向量检索或写入。",
        f"错误原因：{error}",
    ]
    if status["available"]:
        lines.append("Ollama 状态：可访问。")
        if status["model_installed"]:
            lines.append(f"模型状态：已安装 {OLLAMA_EMBED_MODEL}。")
        else:
            lines.append(f"模型状态：未找到 {OLLAMA_EMBED_MODEL}。")
            lines.append(f"建议命令：ollama pull {OLLAMA_EMBED_MODEL}")
    else:
        lines.append("Ollama 状态：不可访问。")
        lines.append("建议命令：ollama serve")
    return "\n".join(lines)


def format_deepseek_error(error: Exception) -> str:
    text = str(error)
    lower = text.lower()
    lines = [
        "DeepSeek API 请求失败，当前无法生成回答。",
        f"错误原因：{error}",
        f"DEEPSEEK_BASE_URL：{DEEPSEEK_BASE_URL}",
        f"DEEPSEEK_MODEL：{DEEPSEEK_MODEL}",
        f"API Key 状态：{'已配置' if DEEPSEEK_API_KEY.strip() else '未配置'}",
    ]

    if "401" in text or "unauthorized" in lower or "authentication" in lower:
        lines.append("可能原因：API Key 错误、失效，或没有 DeepSeek API 权限。")
    elif "429" in text or "rate limit" in lower or "quota" in lower:
        lines.append("可能原因：额度不足、请求过快或触发限流。")
    elif "timeout" in lower or "timed out" in lower:
        lines.append("可能原因：网络连接不稳定或模型响应超时。")
    else:
        lines.append("请检查网络连接、DeepSeek API 服务状态和环境变量配置。")

    lines.extend([
        "建议：确认 .env 中 DEEPSEEK_API_KEY 已填写。",
        "建议：确认当前网络可以访问 DeepSeek API。",
        "建议：确认 DEEPSEEK_BASE_URL 和 DEEPSEEK_MODEL 配置正确。",
    ])
    return "\n".join(lines)


def format_local_llm_error(error: Exception) -> str:
    status = check_llm_server()
    parsed = urlparse(LOCAL_LLM_BASE_URL)
    port_hint = f"{parsed.hostname}:{parsed.port}" if parsed.hostname and parsed.port else LOCAL_LLM_BASE_URL
    lines = [
        "LLM 生成失败，当前无法连接或调用本地大模型服务。",
        f"错误原因：{error}",
        f"配置地址：{LOCAL_LLM_BASE_URL}",
    ]
    if status["available"]:
        lines.append("llama-server 状态：可访问，但本次请求失败，请查看模型日志。")
    else:
        lines.append(f"llama-server 状态：不可访问（检查 {status['url']} 失败）。")
        lines.append(f"建议检查端口和模型路径：lsof -nP -iTCP:{parsed.port or 8080} -sTCP:LISTEN")
        if LOCAL_LLM_MODEL_PATH:
            lines.append(f"建议启动命令：./scripts/run_llama.sh {LOCAL_LLM_MODEL_PATH}")
        else:
            lines.append("建议设置 LOCAL_LLM_MODEL_PATH 后运行 bash start_all.sh")
    lines.append(f"当前端点提示：{port_hint}")
    return "\n".join(lines)


def format_llm_error(error: Exception) -> str:
    if LLM_PROVIDER == "deepseek":
        return format_deepseek_error(error)
    return format_local_llm_error(error)
