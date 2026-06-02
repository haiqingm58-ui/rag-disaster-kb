from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app_server.schemas.auth import LoginRequest, LoginResponse
from app_server.security import CurrentUser, create_access_token, require_user, verify_login
from app_server.settings import settings


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> dict:
    username = payload.username.strip()
    if not verify_login(username, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误。")
    token, expires_at = create_access_token(username=username, role="admin")
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "expires_in": settings.jwt_expire_seconds,
        "user": {"username": username, "role": "admin"},
    }


@router.get("/me")
def me(user: CurrentUser = Depends(require_user)) -> dict:
    return {"username": user.username, "role": user.role}
