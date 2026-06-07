from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app_server.schemas.auth import (
    LoginRequest,
    LoginResponse,
    PasswordResetCodeRequest,
    PasswordResetRequest,
    RegisterCodeRequest,
    RegisterCodeResponse,
    RegisterRequest,
)
from app_server.security import AUTH_COOKIE_NAME, CurrentUser, authenticate_user, create_access_token, require_user
from app_server.services.account_service import (
    register_user,
    reset_user_password,
    send_password_reset_verification,
    send_registration_verification,
)
from app_server.settings import settings


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response) -> dict:
    username = payload.username.strip()
    user = authenticate_user(username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误。")
    return _issue_login_response(response, username=user["username"], role=user["role"], email=user.get("email", ""))


@router.post("/register/send-code", response_model=RegisterCodeResponse)
def send_register_code(payload: RegisterCodeRequest) -> dict:
    return send_registration_verification(email=payload.email, invite_code=payload.invite_code)


@router.post("/register", response_model=LoginResponse)
def register(payload: RegisterRequest, response: Response) -> dict:
    user = register_user(
        username=payload.username,
        password=payload.password,
        email=payload.email,
        invite_code=payload.invite_code,
        verification_code=payload.verification_code,
    )
    return _issue_login_response(response, username=user["username"], role=user["role"], email=user.get("email", ""))


@router.post("/password-reset/send-code", response_model=RegisterCodeResponse)
def send_password_reset_code(payload: PasswordResetCodeRequest) -> dict:
    return send_password_reset_verification(email=payload.email)


@router.post("/password-reset")
def reset_password(payload: PasswordResetRequest) -> dict:
    user = reset_user_password(
        email=payload.email,
        verification_code=payload.verification_code,
        new_password=payload.new_password,
    )
    return {"ok": True, "user": user}


def _issue_login_response(response: Response, username: str, role: str, email: str = "") -> dict:
    token, expires_at = create_access_token(username=username, role=role)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=settings.jwt_expire_seconds,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "expires_in": settings.jwt_expire_seconds,
        "user": {"username": username, "role": role, "email": email},
    }


@router.get("/me")
def me(user: CurrentUser = Depends(require_user)) -> dict:
    return {"username": user.username, "role": user.role}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/", samesite="lax")
    return {"ok": True}
