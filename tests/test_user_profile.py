from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.security import AuthenticatedUser, get_current_user
from app.db import SessionLocal
from app.main import app
from app.models.user_profile import UserProfile

client = TestClient(app)


def use_user(user_id: str):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(id=user_id, email=f"{user_id}@example.com")


def clear_profiles():
    with SessionLocal() as db:
        db.execute(delete(UserProfile))
        db.commit()


def test_profile_initialization_and_get():
    clear_profiles()
    use_user("11111111-1111-1111-1111-111111111111")
    created = client.post("/api/v1/me/profile", json={"display_name": "Ana", "typical_budget_clp": 500000, "favorite_categories": ["notebooks"]})
    assert created.status_code == 201
    assert created.json()["user_id"] == "11111111-1111-1111-1111-111111111111"

    fetched = client.get("/api/v1/me/profile")
    assert fetched.status_code == 200
    assert fetched.json()["display_name"] == "Ana"


def test_profile_update_only_changes_authenticated_user_profile():
    clear_profiles()
    first_user = "11111111-1111-1111-1111-111111111111"
    second_user = "22222222-2222-2222-2222-222222222222"
    use_user(first_user)
    client.post("/api/v1/me/profile", json={"display_name": "Ana"})
    use_user(second_user)
    client.post("/api/v1/me/profile", json={"display_name": "Beto"})

    use_user(first_user)
    updated = client.patch("/api/v1/me/profile", json={"favorite_brands": ["Marca A"]})
    assert updated.status_code == 200
    assert updated.json()["favorite_brands"] == ["Marca A"]

    use_user(second_user)
    fetched = client.get("/api/v1/me/profile")
    assert fetched.json()["display_name"] == "Beto"
    assert fetched.json()["favorite_brands"] == []


def test_missing_or_invalid_token_is_rejected():
    clear_profiles()
    app.dependency_overrides.pop(get_current_user, None)
    assert client.get("/api/v1/me/profile").status_code == 401
    assert client.get("/api/v1/me/profile", headers={"Authorization": "Bearer invalid-token"}).status_code == 401
