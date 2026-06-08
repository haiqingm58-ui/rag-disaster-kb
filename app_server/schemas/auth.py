from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)


class UserInfo(BaseModel):
    username: str
    role: str
    email: str = ""


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int
    expires_in: int
    user: UserInfo


class RegisterCodeRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    invite_code: str = Field(..., min_length=1, max_length=120)


class RegisterCodeResponse(BaseModel):
    ok: bool
    expires_in: int


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=80)
    password: str = Field(..., min_length=8, max_length=200)
    email: str = Field(..., min_length=3, max_length=254)
    invite_code: str = Field(..., min_length=1, max_length=120)
    verification_code: str = Field(..., min_length=4, max_length=12)


class PasswordResetCodeRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)


class PasswordResetRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    verification_code: str = Field(..., min_length=4, max_length=12)
    new_password: str = Field(..., min_length=8, max_length=200)
