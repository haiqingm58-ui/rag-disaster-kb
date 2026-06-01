from __future__ import annotations

import logging
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app_server.api import chat, diagnostics, disasters, documents, graph, health
from app_server.logging_config import setup_logging
from app_server.settings import settings


setup_logging()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="地质灾害知识图谱 RAG 问答系统",
        description="FastAPI entry for Graph-RAG, realtime disaster data and document management.",
        version=settings.version,
    )

    cors_origins = settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=None if cors_origins else r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception("request failed path=%s method=%s latency_ms=%s", request.url.path, request.method, elapsed_ms)
            raise
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request path=%s method=%s status=%s latency_ms=%s",
            request.url.path,
            request.method,
            response.status_code,
            elapsed_ms,
        )
        response.headers["X-Process-Time-ms"] = str(elapsed_ms)
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled error path=%s method=%s", request.url.path, request.method)
        return JSONResponse(
            status_code=500,
            content={"detail": "服务器内部错误，请查看日志或稍后重试。"},
        )

    app.include_router(health.router, prefix="/api")
    app.include_router(diagnostics.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(graph.router, prefix="/api")
    app.include_router(disasters.router, prefix="/api")

    app.mount("/static", StaticFiles(directory="app_server/static"), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse("app_server/static/index.html")

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "app_server.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        workers=1,
        log_level=settings.log_level.lower(),
    )
