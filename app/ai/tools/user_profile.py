from sqlalchemy.orm import Session

from app.ai.schemas.tools import GetUserProfileInput, UserProfileToolResult
from app.services.user_profile_service import UserProfileService


class GetUserProfileTool:
    def __init__(self, db: Session, user_id: str):
        self.service = UserProfileService(db)
        self.user_id = user_id

    def execute(self, _: GetUserProfileInput) -> dict:
        profile = self.service.get(self.user_id)
        return UserProfileToolResult(
            display_name=profile.display_name,
            typical_budget_clp=profile.typical_budget_clp,
            favorite_categories=profile.favorite_categories,
            favorite_brands=profile.favorite_brands,
            rejected_brands=profile.rejected_brands,
            shopping_preferences=profile.shopping_preferences,
        ).model_dump()
