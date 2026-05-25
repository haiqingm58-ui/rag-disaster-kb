#!/bin/bash
# 灾害知识检索系统 — 一键启动脚本

set -e
cd "$(dirname "$0")"

# .env check
if [ ! -f .env ]; then
    echo "⚠️  未找到 .env，从 .env.example 复制..."
    cp .env.example .env
    echo "   请编辑 .env 填写配置后重新运行"
    exit 1
fi

# Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 Python 3"
    exit 1
fi

# venv
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "📋 启动前检查:"
echo "   - Ollama (embedding): 确认 nomic-embed-text:v1.5 已拉取"
echo "   - LLM: DeepSeek API 或本地 llama-server，取决于 LLM_PROVIDER"
echo ""

# Load .env for info
source .env 2>/dev/null || true
if [ "${LLM_PROVIDER:-deepseek}" = "deepseek" ]; then
    echo "   LLM: DeepSeek API / ${DEEPSEEK_MODEL:-deepseek-chat}"
else
    echo "   LLM: local / ${LOCAL_LLM_MODEL:-qwen-local} @ ${LOCAL_LLM_BASE_URL:-http://127.0.0.1:8080/v1}"
fi
echo "   Embedding: ${EMBEDDING_PROVIDER:-ollama} / ${OLLAMA_EMBED_MODEL:-nomic-embed-text:v1.5}"
echo ""

echo "🚀 启动 Streamlit..."
PYTHONPATH="$(pwd)" streamlit run src/ui/app.py --server.headless true
