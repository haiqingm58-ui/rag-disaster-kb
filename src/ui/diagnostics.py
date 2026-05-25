"""Small runtime diagnostics used for friendly Streamlit error messages."""

from urllib.parse import urlparse

import requests

from config import LOCAL_EMBEDDING_MODEL, OPENAI_BASE_URL


def check_ollama_model(model: str = LOCAL_EMBEDDING_MODEL) -> dict:
    url = "http://127.0.0.1:11434/api/tags"
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
    base = OPENAI_BASE_URL.rstrip("/")
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
            lines.append(f"模型状态：已安装 {LOCAL_EMBEDDING_MODEL}。")
        else:
            lines.append(f"模型状态：未找到 {LOCAL_EMBEDDING_MODEL}。")
            lines.append(f"建议命令：ollama pull {LOCAL_EMBEDDING_MODEL}")
    else:
        lines.append("Ollama 状态：不可访问。")
        lines.append("建议命令：ollama serve")
    return "\n".join(lines)


def format_llm_error(error: Exception) -> str:
    status = check_llm_server()
    parsed = urlparse(OPENAI_BASE_URL)
    port_hint = f"{parsed.hostname}:{parsed.port}" if parsed.hostname and parsed.port else OPENAI_BASE_URL
    lines = [
        "LLM 生成失败，当前无法连接或调用本地大模型服务。",
        f"错误原因：{error}",
        f"配置地址：{OPENAI_BASE_URL}",
    ]
    if status["available"]:
        lines.append("llama-server 状态：可访问，但本次请求失败，请查看模型日志。")
    else:
        lines.append(f"llama-server 状态：不可访问（检查 {status['url']} 失败）。")
        lines.append(f"建议检查端口和模型路径：lsof -nP -iTCP:{parsed.port or 8080} -sTCP:LISTEN")
        lines.append("建议启动命令：./scripts/run_llama.sh /Users/georisklab02/rag-disaster-kb/models/Qwen_Qwen3.5-9B-Q4_K_M.gguf")
    lines.append(f"当前端点提示：{port_hint}")
    return "\n".join(lines)
