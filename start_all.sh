#!/bin/bash
# 一键启动：本地 Ollama embedding + DeepSeek/local LLM + Streamlit UI。

set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR" || exit 1

LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"
LLAMA_PORT="${LLAMA_PORT:-8080}"

if [ -f "$ROOT_DIR/.env" ]; then
    # shellcheck disable=SC1091
    set -a
    source "$ROOT_DIR/.env"
    set +a
fi

LLM_PROVIDER="$(printf "%s" "${LLM_PROVIDER:-deepseek}" | tr '[:upper:]' '[:lower:]')"
DEEPSEEK_BASE_URL="${DEEPSEEK_BASE_URL:-https://api.deepseek.com}"
DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-chat}"
LOCAL_LLM_BASE_URL="${LOCAL_LLM_BASE_URL:-http://127.0.0.1:8080/v1}"
LOCAL_LLM_MODEL="${LOCAL_LLM_MODEL:-qwen-local}"
OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-${OLLAMA_URL:-http://127.0.0.1:11434}}"
EMBED_MODEL="${OLLAMA_EMBED_MODEL:-${LOCAL_EMBEDDING_MODEL:-nomic-embed-text:v1.5}}"

if [ -n "${LOCAL_LLM_MODEL_PATH:-}" ]; then
    MODEL_PATH="$LOCAL_LLM_MODEL_PATH"
elif [ -n "${QWEN_MODEL_PATH:-}" ]; then
    MODEL_PATH="$QWEN_MODEL_PATH"
elif [ -f "$ROOT_DIR/models/Qwen_Qwen3.5-9B-Q4_K_M.gguf" ]; then
    MODEL_PATH="$ROOT_DIR/models/Qwen_Qwen3.5-9B-Q4_K_M.gguf"
else
    MODEL_PATH="$HOME/Downloads/Qwen_Qwen3.5-9B-Q4_K_M.gguf"
fi

print_step() {
    printf "\n==> %s\n" "$1"
}

ok() {
    printf "[OK] %s\n" "$1"
}

skip() {
    printf "[SKIP] %s\n" "$1"
}

warn() {
    printf "[WARN] %s\n" "$1"
}

fail() {
    printf "[ERROR] %s\n" "$1"
}

port_pid() {
    lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -n 1
}

wait_for_url() {
    local url="$1"
    local seconds="${2:-30}"
    local i
    for ((i = 1; i <= seconds; i++)); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

network_reachable() {
    local url="$1"
    local status
    status="$(curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 8 --max-time 12 "$url" 2>/dev/null || true)"
    [ -n "$status" ] && [ "$status" != "000" ]
}

print_step "检查 Python 虚拟环境"
if [ ! -d "$ROOT_DIR/venv" ]; then
    warn "未找到 venv，正在创建虚拟环境。"
    if ! python3 -m venv "$ROOT_DIR/venv"; then
        fail "创建 venv 失败。请确认已安装 Python 3。"
        exit 1
    fi
fi
ok "venv 可用"

print_step "检查 LLM_PROVIDER"
case "$LLM_PROVIDER" in
    deepseek)
        ok "LLM_PROVIDER=deepseek"
        ;;
    local)
        ok "LLM_PROVIDER=local"
        ;;
    *)
        fail "Unsupported LLM_PROVIDER: $LLM_PROVIDER"
        echo "Suggestion: set LLM_PROVIDER=deepseek or LLM_PROVIDER=local in .env"
        exit 1
        ;;
esac

if [ "$LLM_PROVIDER" = "deepseek" ]; then
    print_step "检查 DeepSeek API 配置"
    if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
        fail "DEEPSEEK_API_KEY is missing"
        echo "Suggestion: add DEEPSEEK_API_KEY=xxx to .env"
        exit 1
    fi
    ok "DeepSeek API key found"
    ok "DeepSeek model: $DEEPSEEK_MODEL"

    if network_reachable "$DEEPSEEK_BASE_URL"; then
        ok "DeepSeek API network reachable: $DEEPSEEK_BASE_URL"
    else
        fail "DeepSeek API network check failed: $DEEPSEEK_BASE_URL"
        echo "Suggestion: check network connection, proxy/VPN, or DEEPSEEK_BASE_URL in .env"
        exit 1
    fi

    skip "llama-server is not required in deepseek mode"
    skip "Qwen GGUF model file is not required in deepseek mode"
fi

print_step "检查 Ollama 服务"
if ! curl -fsS "$OLLAMA_BASE_URL/api/tags" >/dev/null 2>&1; then
    fail "Ollama 未启动或无法访问：$OLLAMA_BASE_URL"
    echo "Suggestion: run ollama serve"
    echo "Suggestion: run ollama pull $EMBED_MODEL"
    exit 1
fi
ok "Ollama is running: $OLLAMA_BASE_URL"

print_step "检查 embedding 模型"
if ! curl -fsS "$OLLAMA_BASE_URL/api/tags" | grep -q "\"name\":\"$EMBED_MODEL\""; then
    fail "Embedding model not found: $EMBED_MODEL"
    echo "Suggestion: run ollama pull $EMBED_MODEL"
    exit 1
fi
ok "Embedding model found: $EMBED_MODEL"

if [ "$LLM_PROVIDER" = "local" ]; then
    print_step "检查本地 GGUF 模型文件"
    if [ ! -f "$MODEL_PATH" ]; then
        fail "模型文件不存在：$MODEL_PATH"
        echo "Suggestion: put the GGUF model under $ROOT_DIR/models/"
        echo "Suggestion: or set LOCAL_LLM_MODEL_PATH=/path/to/model.gguf in .env"
        exit 1
    fi
    ok "模型文件存在：$MODEL_PATH"
    ok "Local LLM model name: $LOCAL_LLM_MODEL"

    print_step "检查 llama.cpp server"
    if curl -fsS "$LOCAL_LLM_BASE_URL/models" >/dev/null 2>&1; then
        ok "llama-server 已运行：$LOCAL_LLM_BASE_URL"
    else
        if ! command -v llama-server >/dev/null 2>&1; then
            fail "未找到 llama-server 命令。"
            echo "Suggestion: brew install llama.cpp"
            exit 1
        fi

        if [ -n "$(port_pid "$LLAMA_PORT")" ]; then
            fail "端口 $LLAMA_PORT 已被其他进程占用，无法启动 llama-server。"
            echo "查看占用：lsof -nP -iTCP:$LLAMA_PORT -sTCP:LISTEN"
            exit 1
        fi

        ok "llama-server 未运行，准备后台启动。"
        if command -v screen >/dev/null 2>&1; then
            screen -S rag-llama -X quit >/dev/null 2>&1 || true
            screen -dmS rag-llama bash -lc "cd '$ROOT_DIR' && ./scripts/run_llama.sh '$MODEL_PATH' >> '$LOG_DIR/llama-server.log' 2>&1"
        else
            nohup "$ROOT_DIR/scripts/run_llama.sh" "$MODEL_PATH" >> "$LOG_DIR/llama-server.log" 2>&1 &
        fi

        if wait_for_url "$LOCAL_LLM_BASE_URL/models" 90; then
            ok "llama-server 已启动：$LOCAL_LLM_BASE_URL"
        else
            fail "llama-server 启动超时。"
            echo "请查看日志：$LOG_DIR/llama-server.log"
            echo "常见原因：模型路径错误、内存不足、llama.cpp 安装损坏。"
            exit 1
        fi
    fi
fi

print_step "检查 Streamlit 端口"
STREAMLIT_PID="$(port_pid "$STREAMLIT_PORT")"
if [ -n "$STREAMLIT_PID" ]; then
    if ps -p "$STREAMLIT_PID" -o command= | grep -qi "streamlit"; then
        ok "Streamlit 已在运行：http://localhost:$STREAMLIT_PORT"
        echo "如需重启，请先停止进程：kill $STREAMLIT_PID"
        exit 0
    fi
    fail "端口 $STREAMLIT_PORT 已被非 Streamlit 进程占用，PID=$STREAMLIT_PID"
    echo "查看占用：lsof -nP -iTCP:$STREAMLIT_PORT -sTCP:LISTEN"
    exit 1
fi
ok "端口 $STREAMLIT_PORT 可用"

print_step "启动 Streamlit UI"
echo "[START] Streamlit"
echo "访问地址：http://localhost:$STREAMLIT_PORT"
# shellcheck disable=SC1091
source "$ROOT_DIR/venv/bin/activate"
export PYTHONPATH="$ROOT_DIR"
exec streamlit run "$ROOT_DIR/src/ui/app.py" --server.headless true --server.port "$STREAMLIT_PORT"
