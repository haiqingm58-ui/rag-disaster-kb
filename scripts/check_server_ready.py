#!/usr/bin/env python3
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"


def ok(message: str) -> tuple[str, bool]:
    return f"[OK] {message}", True


def warn(message: str) -> tuple[str, bool]:
    return f"[WARN] {message}", True


def fail(message: str) -> tuple[str, bool]:
    return f"[FAIL] {message}", False


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def main() -> int:
    load_dotenv(ENV_PATH)
    checks: list[tuple[str, bool]] = []

    py = sys.version_info
    if py.major == 3 and py.minor >= 11:
        checks.append(ok(f"Python 版本 {py.major}.{py.minor}.{py.micro}"))
    else:
        checks.append(fail(f"Python 版本过低：{py.major}.{py.minor}.{py.micro}，建议 3.11+"))

    for rel in ["data", "data/documents", "data/cache", "data/uploads", "data/chroma_db", "logs"]:
        path = ROOT / rel
        if path.exists():
            checks.append(ok(f"目录存在：{rel}"))
        else:
            checks.append(warn(f"目录不存在：{rel}，首次运行可自动创建或手动 mkdir -p"))

    if ENV_PATH.exists():
        checks.append(ok(".env 存在"))
    else:
        checks.append(warn(".env 不存在；本地开发可用环境变量，生产部署建议创建 .env"))

    if os.getenv("DEEPSEEK_API_KEY", "").strip():
        checks.append(ok("DeepSeek API Key 已配置"))
    else:
        checks.append(warn("DeepSeek API Key 未配置；/api/chat 会返回清晰错误提示但不能生成回答"))

    embedding_provider = os.getenv("EMBEDDING_PROVIDER", "ollama").lower()
    if embedding_provider == "ollama":
        if os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip():
            checks.append(ok("Embedding provider=ollama，配置已读取；请确认 Ollama 服务或已有 Chroma 数据可用"))
        else:
            checks.append(warn("OLLAMA_BASE_URL 未配置；文档入库可能失败"))
    elif embedding_provider == "openai_compatible":
        if os.getenv("EMBEDDING_API_KEY", "").strip() and os.getenv("EMBEDDING_BASE_URL", "").strip():
            checks.append(ok("Embedding provider=openai_compatible，远程 embedding 配置完整"))
        else:
            checks.append(warn("远程 embedding 配置不完整；需要 EMBEDDING_API_KEY 和 EMBEDDING_BASE_URL"))
    else:
        checks.append(warn(f"未知 EMBEDDING_PROVIDER={embedding_provider}；建议使用 ollama 或 openai_compatible"))

    graph_candidates = [ROOT / "docs/data/graph_data.json", ROOT / "exports/standard_kg_browser/graph_data.json"]
    search_candidates = [ROOT / "docs/data/search_index.json", ROOT / "exports/standard_kg_browser/search_index.json"]
    if any(p.exists() for p in graph_candidates):
        checks.append(ok("graph_data.json 存在"))
    else:
        checks.append(warn("graph_data.json 不存在；图谱接口会降级为空数据"))
    if any(p.exists() for p in search_candidates):
        checks.append(ok("search_index.json 存在"))
    else:
        checks.append(warn("search_index.json 不存在；图谱搜索会降级为空列表"))

    chroma_dir = Path(os.getenv("CHROMA_DIR", str(ROOT / "data/chroma_db")))
    try:
        chroma_dir.mkdir(parents=True, exist_ok=True)
        probe = chroma_dir / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append(ok(f"Chroma 目录可写：{chroma_dir}"))
    except Exception as exc:
        checks.append(fail(f"Chroma 目录不可写：{chroma_dir}，原因：{exc}"))

    port = int(os.getenv("APP_PORT", "8000"))
    if port_available(port):
        checks.append(ok(f"端口 {port} 可用"))
    else:
        checks.append(warn(f"端口 {port} 已被占用；如果服务正在运行可忽略，否则请排查"))

    print("部署前自检报告")
    print("=" * 40)
    for line, _ in checks:
        print(line)

    hard_failed = [line for line, passed in checks if not passed]
    print("=" * 40)
    if hard_failed:
        print("总体状态：FAILED，需要先处理关键失败项。")
        return 1
    warnings = [line for line, _ in checks if line.startswith("[WARN]")]
    if warnings:
        print("总体状态：DEGRADED，可启动但建议处理警告项。")
        return 0
    print("总体状态：OK，可以部署。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
