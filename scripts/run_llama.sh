#!/bin/bash
# 启动 llama.cpp server，加载 GGUF 模型并暴露 OpenAI 兼容 API

set -e

# 默认参数
PORT="${LLAMA_PORT:-8080}"
CTX_SIZE="${LLAMA_CTX_SIZE:-8192}"
N_GPU_LAYERS="${LLAMA_N_GPU_LAYERS:-99}"   # 99 = 全部 offload 到 Metal GPU
THREADS="${LLAMA_THREADS:-8}"
MODEL="${1:-$HOME/Downloads/qwen3.5-9b-instruct-q4_k_m.gguf}"

if [ ! -f "$MODEL" ]; then
    echo "❌ 模型文件不存在: $MODEL"
    echo "用法: $0 <gguf模型路径>"
    echo "示例: $0 ~/Downloads/qwen3.5-9b-instruct-q4_k_m.gguf"
    exit 1
fi

echo "🚀 启动 llama.cpp server..."
echo "   模型: $MODEL"
echo "   端点: http://localhost:$PORT/v1"
echo "   GPU 层数: $N_GPU_LAYERS"
echo "   上下文: $CTX_SIZE tokens"
echo ""

exec llama-server \
    -m "$MODEL" \
    --port "$PORT" \
    --ctx-size "$CTX_SIZE" \
    --n-gpu-layers "$N_GPU_LAYERS" \
    --threads "$THREADS" \
    --host 127.0.0.1 \
    --reasoning off
