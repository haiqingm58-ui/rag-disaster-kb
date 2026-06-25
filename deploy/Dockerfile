# 可选 Docker 镜像：默认部署走 systemd（README_DEPLOY.md）。
# 想用 Docker 时：
#   docker build -t rag-disaster-kb -f deploy/Dockerfile .
#   docker run -d --name rag-disaster-kb \
#     --env-file .env \
#     -p 127.0.0.1:8000:8000 \
#     -v $(pwd)/data:/app/data \
#     -v $(pwd)/logs:/app/logs \
#     --restart unless-stopped \
#     rag-disaster-kb
# nginx 仍然指向 127.0.0.1:8000，不需要改。

FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-server.txt ./
RUN pip install --upgrade pip \
    && pip wheel --wheel-dir /wheels -r requirements-server.txt


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 非 root 用户。
RUN groupadd --system app && useradd --system --gid app --home /app app

COPY --from=builder /wheels /wheels
COPY requirements-server.txt ./
RUN pip install --no-index --find-links=/wheels -r requirements-server.txt \
    && rm -rf /wheels

COPY app ./app
COPY app_server ./app_server
COPY src ./src
COPY scripts ./scripts
COPY configs ./configs
COPY config.py ./config.py

RUN mkdir -p data/cache data/uploads data/documents data/chroma_db logs \
    && chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3); sys.exit(0)" || exit 1

CMD ["uvicorn", "app_server.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--loop", "uvloop", "--http", "httptools", \
     "--timeout-keep-alive", "30", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
