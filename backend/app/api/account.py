from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import AuthenticatedUser, require_user
from app.config import Settings, get_settings
from app.database import get_db
from app.schemas import AccountResponse, UsageResponse
from app.services.quotas import usage_snapshot


router = APIRouter(prefix="/account", tags=["account"])


@router.get("", response_model=AccountResponse)
def get_account(user: AuthenticatedUser = Depends(require_user)) -> AccountResponse:
    return AccountResponse(user_id=user.id, email=user.email)


@router.get("/usage", response_model=UsageResponse)
def get_usage(
    db: Session = Depends(get_db),
    user: AuthenticatedUser = Depends(require_user),
    settings: Settings = Depends(get_settings),
) -> UsageResponse:
    return UsageResponse.model_validate(usage_snapshot(db, user.id, settings), from_attributes=True)
