from __future__ import annotations

from pydantic import BaseModel


class DocumentItem(BaseModel):
    source: str
    name: str
    chunks: int


class UploadResponse(BaseModel):
    filename: str
    document_id: str
    saved_path: str
    chunk_count: int
    chroma_written: bool
    latency_ms: int
    parser_report: dict
