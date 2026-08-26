from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.security import AuthenticatedUser, get_current_user
from app.db import get_db
from app.schemas.user_profile import ProfileCreate, ProfileRead, ProfileUpdate
from app.services.user_profile_service import UserProfileService

router = APIRouter(prefix="/me/profile", tags=["profile"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


@router.get("", response_model=ProfileRead)
def get_profile(user: CurrentUser, db: DbSession):
    return UserProfileService(db).get(user.id)


@router.post("", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
def initialize_profile(payload: ProfileCreate, response: Response, user: CurrentUser, db: DbSession):
    profile, created = UserProfileService(db).initialize(user.id, payload)
    if not created:
        response.status_code = status.HTTP_200_OK
    return profile


@router.patch("", response_model=ProfileRead)
def update_profile(payload: ProfileUpdate, user: CurrentUser, db: DbSession):
    return UserProfileService(db).update(user.id, payload)
