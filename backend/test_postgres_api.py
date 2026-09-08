"""End-to-end API checks against PostgreSQL-backed REelo persistence."""
import os

import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    url = os.getenv("REELO_DATABASE_URL", "").strip()
    if not url.lower().startswith(("postgres://", "postgresql://")):
        pytest.skip("REELO_DATABASE_URL is not configured for PostgreSQL")

    from main import app

    with TestClient(app) as test_client:
        yield test_client


def test_auth_profile_feed_and_social_flow(client):
    suffix = "pgapi"
    first = client.post(
        "/api/auth/register",
        json={"username": f"reelo_{suffix}_one", "password": "password123", "display_name": "One"},
    )
    assert first.status_code == 200, first.text
    first_data = first.json()
    token = first_data["token"]
    user_id = first_data["user"]["id"]

    second = client.post(
        "/api/auth/register",
        json={"username": f"reelo_{suffix}_two", "password": "password123", "display_name": "Two"},
    )
    assert second.status_code == 200, second.text
    second_id = second.json()["user"]["id"]

    me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["id"] == user_id

    profile = client.patch(
        "/api/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"display_name": "One Updated", "bio": "PostgreSQL"},
    )
    assert profile.status_code == 200
    assert profile.json()["user"]["bio"] == "PostgreSQL"

    follow = client.post(
        f"/api/users/{second_id}/follow",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert follow.status_code == 200
    assert follow.json()["action"] == "follow"

    notifications = client.get(
        "/api/notifications",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert notifications.status_code == 200

    feed = client.get("/api/feed", headers={"Authorization": f"Bearer {token}"})
    assert feed.status_code == 200
    assert "items" in feed.json()

    login = client.post(
        "/api/auth/login",
        json={"username": f"reelo_{suffix}_one", "password": "password123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == user_id
