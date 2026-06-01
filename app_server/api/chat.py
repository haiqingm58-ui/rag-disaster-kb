from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app_server.schemas.chat import ChatRequest, ChatResponse
from app_server.services.rag_service import chat as run_chat


router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> dict:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空。")
    if len(question) > 2000:
        raise HTTPException(status_code=400, detail="问题过长，请控制在 2000 个字符以内。")
    return run_chat(
        question=question,
        session_id=request.session_id,
        use_graph=request.use_graph,
        use_realtime=request.use_realtime,
        top_k=request.top_k,
    )
