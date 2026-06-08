from __future__ import annotations

from fastapi import APIRouter, Depends

from app_server.schemas.user_data import UserDataPayload, UserDataResponse
from app_server.security import CurrentUser, require_user
from app_server.services.user_data_service import load_user_data, save_user_data


router = APIRouter(prefix="/user-data", tags=["user-data"])


@router.get("", response_model=UserDataResponse)
def get_user_data(user: CurrentUser = Depends(require_user)) -> dict:
    return load_user_data(user.username)


@router.put("", response_model=UserDataResponse)
def put_user_data(payload: UserDataPayload, user: CurrentUser = Depends(require_user)) -> dict:
    return save_user_data(user.username, payload.model_dump())
