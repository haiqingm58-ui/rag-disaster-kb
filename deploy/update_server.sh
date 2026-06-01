#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rag-disaster-kb}"

echo "进入项目目录：$APP_DIR"
cd "$APP_DIR"

echo "拉取最新代码..."
git pull

echo "激活虚拟环境并安装服务器最小依赖..."
source venv/bin/activate
pip install -r requirements-server.txt

echo "运行部署前自检..."
python scripts/check_server_ready.py

echo "重启 FastAPI systemd 服务..."
sudo systemctl restart rag-fastapi
sudo systemctl status rag-fastapi --no-pager

echo "更新完成。"
