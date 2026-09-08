import uuid

from fastapi.testclient import TestClient

from app import app


def test_register_login_and_me_contract():
    username = f"ci_{uuid.uuid4().hex[:12]}"
    password = "StrongPass123!"

    with TestClient(app) as client:
        register = client.post(
            "/api/auth/register",
            json={
                "username": username,
                "password": password,
                "display_name": "CI User",
            },
        )
        assert register.status_code == 200, register.text
        payload = register.json()
        assert payload["token"]
        assert payload["user"]["username"] == username

        token = payload["token"]
        me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        assert me.json()["user"]["username"] == username

        login = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert login.status_code == 200, login.text
        assert login.json()["user"]["id"] == payload["user"]["id"]

        bad_login = client.post(
            "/api/auth/login",
            json={"username": username, "password": "wrong-password"},
        )
        assert bad_login.status_code == 401


def test_me_rejects_missing_or_invalid_authentication():
    with TestClient(app) as client:
        assert client.get("/api/me").status_code == 401
        assert client.get(
            "/api/me", headers={"Authorization": "Bearer invalid-token"}
        ).status_code == 401
