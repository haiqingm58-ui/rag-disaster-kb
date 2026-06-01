from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app_server.schemas.document import DocumentItem, UploadResponse
from app_server.services.document_service import delete_document, list_documents, save_and_ingest


router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> dict:
    try:
        return await save_and_ingest(file)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"上传失败：{exc}") from exc


@router.get("", response_model=list[DocumentItem])
def documents() -> list[dict]:
    return list_documents()


@router.delete("")
def delete(source: str) -> dict:
    return delete_document(source)
