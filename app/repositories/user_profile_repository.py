from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_profile import UserProfile


class UserProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user_id(self, user_id: str) -> UserProfile | None:
        return self.db.scalar(select(UserProfile).where(UserProfile.user_id == user_id))

    def create(self, user_id: str, values: dict) -> UserProfile:
        profile = UserProfile(user_id=user_id, **values)
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def update(self, profile: UserProfile, values: dict) -> UserProfile:
        for field, value in values.items():
            setattr(profile, field, value)
        self.db.commit()
        self.db.refresh(profile)
        return profile
