from __future__ import annotations

import logging
import shutil
import time
import uuid
from pathlib import Path

from fastapi import UploadFile

from config import COLLECTION_DOCS, UPLOADS_DIR
from app_server.services.document_converter import (
    SUPPORTED_SUFFIX_LABEL,
    convert_to_markdown,
    safe_upload_filename,
    validate_upload_metadata,
)
from src.ingestion.document_loader import load_and_chunk_with_report
from src.vectorstore.chroma_store import add_documents, delete_by_source, embedding_config_status, list_sources, source_chunk_count


logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    return safe_upload_filename(name)


async def save_and_ingest(file: UploadFile) -> dict:
    start = time.perf_counter()
    filename = _safe_filename(file.filename or "upload.txt")
    validate_upload_metadata(file, filename)

    document_id = uuid.uuid4().hex
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOADS_DIR / f"{document_id}_{filename}"
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    conversion = convert_to_markdown(target, filename=filename, document_id=document_id)
    chunks, report = load_and_chunk_with_report(str(conversion.markdown_path))
    report.update(conversion.report)
    for chunk in chunks:
        chunk.metadata["source"] = str(target)
        chunk.metadata["markdown_path"] = str(conversion.markdown_path)
        chunk.metadata["filename"] = filename
        chunk.metadata["document_id"] = document_id
    chroma_written = False
    embedding_status = embedding_config_status()
    if not embedding_status["ready"]:
        raise ValueError(f"Embedding 配置不可用：{embedding_status['message']}")
    try:
        add_documents(chunks, COLLECTION_DOCS)
        chroma_written = True
    except Exception:
        logger.exception("write uploaded document to chroma failed document_id=%s filename=%s", document_id, filename)
    return {
        "filename": filename,
        "document_id": document_id,
        "saved_path": str(target),
        "markdown_path": str(conversion.markdown_path),
        "chunk_count": len(chunks),
        "chroma_written": chroma_written,
        "latency_ms": round((time.perf_counter() - start) * 1000),
        "parser_report": report,
    }


def list_documents() -> list[dict]:
    try:
        sources = list_sources(COLLECTION_DOCS)
    except Exception:
        logger.exception("list documents failed")
        return []
    return [
        {"source": source, "name": Path(source).name, "chunks": source_chunk_count(COLLECTION_DOCS, source)}
        for source in sources
    ]


def delete_document(source: str) -> dict:
    return {"source": source, "deleted_chunks": delete_by_source(COLLECTION_DOCS, source)}


def rebuild_document_index() -> dict:
    documents = list_documents()
    return {
        "status": "ok",
        "message": "文档索引由 Chroma 持久化维护。当前已完成索引状态检查；如需彻底重建，请重新上传源文档或执行离线重建脚本。",
        "documents": len(documents),
        "chunks": sum(item.get("chunks", 0) for item in documents),
    }


def supported_upload_label() -> str:
    return SUPPORTED_SUFFIX_LABEL
