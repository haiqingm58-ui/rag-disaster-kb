#!/usr/bin/env bash
# Run all evaluation questions in three batches with the project virtualenv.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [ ! -d "venv" ] || [ ! -f "venv/bin/activate" ]; then
    echo "错误：未找到项目虚拟环境 venv。"
    echo "请先在项目根目录创建并安装依赖："
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

if [ ! -f "tests/run_eval.py" ]; then
    echo "错误：未找到 tests/run_eval.py，无法运行评测。"
    echo "请确认当前项目目录完整：$PROJECT_ROOT"
    exit 1
fi

echo "进入项目目录：$PROJECT_ROOT"
echo "激活虚拟环境：venv"
source "venv/bin/activate"

status=0

run_batch() {
    local start="$1"
    local limit="$2"

    echo ""
    echo "============================================================"
    echo "开始评测第 ${start} 题起的 ${limit} 题"
    echo "命令：python tests/run_eval.py --start ${start} --limit ${limit} --skip-sync"
    echo "============================================================"

    if ! python tests/run_eval.py --start "$start" --limit "$limit" --skip-sync; then
        echo "本批评测存在失败：start=${start}, limit=${limit}"
        status=1
    fi
}

run_batch 1 10
run_batch 11 10
run_batch 21 10

echo ""
if [ "$status" -eq 0 ]; then
    echo "全部批次评测通过。"
else
    echo "评测完成，但至少一个批次存在失败，请查看上方失败题目列表。"
fi

exit "$status"
