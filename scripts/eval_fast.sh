#!/usr/bin/env bash
# Run the fast smoke evaluation with the project virtualenv.

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

echo "开始快速评测：python tests/run_eval.py --fast"
python tests/run_eval.py --fast
