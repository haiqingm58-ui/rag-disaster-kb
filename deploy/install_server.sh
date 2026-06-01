#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rag-disaster-kb}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip nginx git

if [ ! -d "$APP_DIR" ]; then
  echo "ERROR: $APP_DIR 不存在。请先 git clone 项目，或设置 APP_DIR=/path/to/project。"
  exit 1
fi

cd "$APP_DIR"
$PYTHON_BIN -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements-server.txt

mkdir -p data/cache data/uploads data/documents data/chroma_db logs

if [ ! -f .env ]; then
  cp .env.example .env
  echo "已创建 .env 模板，请用 nano .env 填写真实配置。"
else
  echo ".env 已存在，未覆盖。"
fi

echo "安装完成。请检查 .env，然后配置 systemd 和 Nginx。"
echo "提示：脚本不会写入 API Key，不会安装 Neo4j、本地大模型或强制启动 Ollama。"
