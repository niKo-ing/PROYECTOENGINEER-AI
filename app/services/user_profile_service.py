from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.user_profile_repository import UserProfileRepository
from app.schemas.user_profile import ProfileCreate, ProfileUpdate


class UserProfileService:
    def __init__(self, db: Session):
        self.repository = UserProfileRepository(db)

    def get(self, user_id: str):
        profile = self.repository.get_by_user_id(user_id)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perfil no inicializado")
        return profile

    def initialize(self, user_id: str, payload: ProfileCreate):
        existing = self.repository.get_by_user_id(user_id)
        if existing is not None:
            return existing, False
        return self.repository.create(user_id, payload.model_dump()), True

    def update(self, user_id: str, payload: ProfileUpdate):
        profile = self.get(user_id)
        return self.repository.update(profile, payload.model_dump(exclude_unset=True))
