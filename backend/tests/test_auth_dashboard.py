"""Accounts, sessions, dashboard, and automation access."""

from uuid import uuid4

from fastapi.testclient import TestClient

from conftest import SEED_EMAIL, SEED_PASSWORD, TEST_AUTOMATION_TOKEN


def test_register_login_me_and_logout(registry_client: TestClient) -> None:
    email = f"user-{uuid4().hex[:10]}@example.com"
    password = "learning-pass-1"

    registered = registry_client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert registered.status_code == 201
    assert registered.json()["email"] == email

    me = registry_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == email

    logged_out = registry_client.post("/api/auth/logout")
    assert logged_out.status_code == 204
    assert registry_client.get("/api/auth/me").status_code == 401

    login = registry_client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    assert registry_client.get("/api/auth/me").status_code == 200


def test_login_rejects_bad_password(registry_client: TestClient) -> None:
    response = registry_client.post(
        "/api/auth/login",
        json={"email": SEED_EMAIL, "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_dashboard_lists_owned_sites_and_recent_checks(registry_client: TestClient) -> None:
    created = registry_client.post(
        "/api/websites",
        json={"name": "Dash site", "base_url": f"https://dash.invalid/{uuid4().hex}"},
    )
    assert created.status_code == 201
    website_id = created.json()["id"]
    try:
        dash = registry_client.get("/api/dashboard")
        assert dash.status_code == 200
        body = dash.json()
        assert any(item["id"] == website_id for item in body["websites"])
        assert "recent_checks" in body
        assert body["health"]["website_count"] >= 1
        assert body["health"]["monitored_count"] >= 0
    finally:
        registry_client.delete(f"/api/websites/{website_id}")


def test_automation_token_can_list_websites(
    client: TestClient,
    migrated_database: None,
) -> None:
    # Sign in as seed, create a site, then list with automation only.
    login = client.post(
        "/api/auth/login",
        json={"email": SEED_EMAIL, "password": SEED_PASSWORD},
    )
    assert login.status_code == 200
    created = client.post(
        "/api/websites",
        json={"name": "Auto site", "base_url": f"https://auto.invalid/{uuid4().hex}"},
    )
    assert created.status_code == 201
    website_id = created.json()["id"]
    client.post("/api/auth/logout")

    listed = client.get(
        "/api/websites",
        headers={"X-Automation-Token": TEST_AUTOMATION_TOKEN},
    )
    assert listed.status_code == 200
    assert any(item["id"] == website_id for item in listed.json())

    client.delete(
        f"/api/websites/{website_id}",
        headers={"X-Automation-Token": TEST_AUTOMATION_TOKEN},
    )


def test_seed_user_can_sign_in(registry_client: TestClient) -> None:
    me = registry_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == SEED_EMAIL
