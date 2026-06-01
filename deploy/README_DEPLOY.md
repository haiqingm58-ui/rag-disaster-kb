# 阿里云 Ubuntu 部署手册

目标：2 核 CPU、2GB 内存、40GB 硬盘稳定运行 FastAPI Web 应用。默认使用 DeepSeek API 生成回答，本机保存文档、图谱 JSON、Chroma 向量库、缓存和日志。不要把 Neo4j、Redis、Celery、Docker、本地大模型作为默认必需项。

## 0. Mac 本地准备

确认本地改动并提交推送：

```bash
cd /Users/georisklab02/rag-disaster-kb
git status
git add .
git commit -m "FastAPI deployment ready"
git push
```

不要提交 `.env`、`data/`、`logs/`、`venv/`、`models/`。

## 1. 阿里云安全组

在阿里云控制台安全组放行：

- `22/tcp`：SSH 登录
- `80/tcp`：Web 访问
- `8000/tcp`：仅调试时临时开放，正式环境不建议长期开放

正式访问通过 Nginx 的 80 端口反向代理到 `127.0.0.1:8000`。

## 2. 登录服务器

```bash
ssh root@你的服务器公网IP
```

## 3. 安装 Ubuntu 依赖

```bash
apt update
apt install -y git python3 python3-venv python3-pip nginx
```

## 4. 拉取项目

```bash
mkdir -p /opt
cd /opt
git clone <your-repo-url> rag-disaster-kb
cd rag-disaster-kb
```

## 5. 创建 venv 并安装服务器最小依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirements-server.txt
mkdir -p data/cache data/uploads data/documents data/chroma_db logs
```

也可以执行脚本：

```bash
bash deploy/install_server.sh
```

脚本不会写入 API Key，不会安装 Ollama、Neo4j、Docker 或本地大模型。

## 6. 创建 `.env`

```bash
cp .env.example .env
nano .env
```

推荐 2G 服务器配置远程 embedding：

```bash
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
MAX_UPLOAD_MB=30
GRAPH_TOP_K=80
DISASTER_CACHE_TTL_SECONDS=600
LOG_LEVEL=INFO
LOG_TO_FILE=true
CORS_ORIGINS=http://你的域名或IP

LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
LLM_MAX_TOKENS=512
LLM_TEMPERATURE=0.2

EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_API_KEY=你的远程embedding key
EMBEDDING_BASE_URL=https://api.xxx.com/v1
EMBEDDING_MODEL=text-embedding-3-small

CHROMA_DIR=/opt/rag-disaster-kb/data/chroma_db
```

如果你已经提前构建好了 Chroma 数据，也可以暂时保持：

```bash
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBED_MODEL=nomic-embed-text:v1.5
```

注意：部署脚本不会启动 Ollama。2GB 机器不建议同时运行本地大模型。

## 7. 部署前自检

```bash
source venv/bin/activate
python scripts/check_server_ready.py
```

若显示 `DEGRADED`，根据提示处理；图谱 JSON 缺失或 embedding 未配置时，系统仍可降级启动，但文档入库或问答质量会受影响。

## 8. 手动测试启动

```bash
source venv/bin/activate
uvicorn app_server.main:app --host 127.0.0.1 --port 8000 --workers 1
```

另开 SSH 窗口测试：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/diagnostics
```

确认正常后按 `Ctrl+C` 停止手动进程。

## 9. 配置 systemd

```bash
sudo cp deploy/rag-fastapi.service.example /etc/systemd/system/rag-fastapi.service
sudo systemctl daemon-reload
sudo systemctl enable --now rag-fastapi
sudo systemctl status rag-fastapi
```

服务配置要点：

- 使用 `/opt/rag-disaster-kb/venv/bin/uvicorn`
- 单 worker
- 监听 `127.0.0.1:8000`
- `EnvironmentFile=/opt/rag-disaster-kb/.env`
- `Restart=always`

## 10. 配置 Nginx

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/rag-fastapi
sudo nano /etc/nginx/sites-available/rag-fastapi
sudo ln -sf /etc/nginx/sites-available/rag-fastapi /etc/nginx/sites-enabled/rag-fastapi
sudo nginx -t
sudo systemctl reload nginx
```

把配置中的：

```nginx
server_name example.com;
```

改为你的域名或公网 IP。

浏览器访问：

```text
http://你的域名或IP/
```

## 11. 查看日志

```bash
journalctl -u rag-fastapi -f
tail -f /opt/rag-disaster-kb/logs/app.log
```

接口排查：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/diagnostics
```

## 12. 更新代码

```bash
cd /opt/rag-disaster-kb
git pull
source venv/bin/activate
pip install -r requirements-server.txt
python scripts/check_server_ready.py
sudo systemctl restart rag-fastapi
sudo systemctl status rag-fastapi
```

也可以执行：

```bash
bash deploy/update_server.sh
```

## 13. 备份数据

```bash
cd /opt/rag-disaster-kb
tar -czvf rag-data-backup-$(date +%F).tar.gz data logs
```

建议定期把备份下载到本地或上传对象存储。`.env` 含密钥，若备份 `.env`，务必妥善保存。

## 14. 常见问题

### 502 Bad Gateway

```bash
sudo systemctl status rag-fastapi
journalctl -u rag-fastapi -n 100 --no-pager
```

通常是 FastAPI 没启动、端口不对或 `.env` 配置错误。

### 端口被占用

```bash
ss -ltnp | grep 8000
```

停止占用进程后重启：

```bash
sudo systemctl restart rag-fastapi
```

### DeepSeek Key 缺失

检查：

```bash
grep DEEPSEEK_API_KEY .env
sudo systemctl restart rag-fastapi
```

不要把真实 Key 提交到 GitHub。

### embedding 不可用

推荐 2G 服务器配置：

```bash
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_API_KEY=你的key
EMBEDDING_BASE_URL=https://api.xxx.com/v1
EMBEDDING_MODEL=text-embedding-3-small
```

如果 embedding 不可用，图谱搜索和实时灾害功能仍可用，但文档上传入库和向量检索会受影响。

### Chroma 目录不可写

```bash
mkdir -p data/chroma_db
chown -R $USER:$USER data logs
python scripts/check_server_ready.py
```

### 上传 413

确认 Nginx：

```nginx
client_max_body_size 30m;
```

确认 `.env`：

```bash
MAX_UPLOAD_MB=30
```

### 服务器内存不足

- 保持 `--workers 1`
- 不启动本地大模型
- 不默认启动 Neo4j
- 优先使用远程 embedding
- 上传 PDF 控制大小

### 页面能打开但问答失败

查看：

```bash
curl http://127.0.0.1:8000/api/diagnostics
tail -f logs/app.log
```

常见原因是 DeepSeek Key、embedding 配置、Chroma 状态或网络访问问题。
