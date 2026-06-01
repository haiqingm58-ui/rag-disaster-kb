from __future__ import annotations

import logging
import shutil
import time
import uuid
from pathlib import Path

from fastapi import UploadFile

from app_server.settings import settings
from config import COLLECTION_DOCS, UPLOADS_DIR
from src.ingestion.document_loader import load_and_chunk_with_report
from src.vectorstore.chroma_store import add_documents, delete_by_source, embedding_config_status, list_sources, source_chunk_count


ALLOWED_SUFFIXES = {".pdf", ".txt", ".md"}
logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    return Path(name).name.replace("/", "_").replace("\\", "_")


async def save_and_ingest(file: UploadFile) -> dict:
    start = time.perf_counter()
    filename = _safe_filename(file.filename or "upload.txt")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("仅支持 PDF、TXT、MD 文件")

    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size > settings.max_upload_bytes:
        raise ValueError(f"文件过大，最大允许 {settings.max_upload_mb}MB")

    document_id = uuid.uuid4().hex
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOADS_DIR / f"{document_id}_{filename}"
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    chunks, report = load_and_chunk_with_report(str(target))
    for chunk in chunks:
        chunk.metadata["source"] = str(target)
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
