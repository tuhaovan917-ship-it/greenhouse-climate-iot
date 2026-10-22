"""A3 login/logout/me security smoke tests using isolated in-memory SQLite."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth_models import User, UserSession
from app.database import getSession
from app.main import app
from app.services.auth import COOKIE_NAME, hash_password, token_digest, utc_now

PASSWORD = "correct-horse-demo-password"


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(username="admin_a3", email="admin_a3@example.test", password_hash=hash_password(PASSWORD), role="admin"))
        db.commit()

    def isolated_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[getSession] = isolated_db
    client = TestClient(app)
    try:
        yield client, engine
    finally:
        client.close()
        app.dependency_overrides.pop(getSession, None)
        engine.dispose()


def login(client: TestClient, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"username": "admin_a3", "password": password})


def test_me_requires_cookie(client):
    browser, _ = client
    assert browser.get("/api/auth/me").status_code == 401


def test_login_me_cookie_and_private_password(client):
    browser, engine = client
    response = login(browser)
    assert response.status_code == 200, response.text
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "password" not in response.json()["user"]
    assert response.json()["user"]["role"] == "admin"
    assert len(response.json()["csrfToken"]) == 64
    assert browser.get("/api/auth/me").status_code == 200
    raw_token = browser.cookies.get(COOKIE_NAME)
    with Session(engine) as db:
        stored = db.exec(select(UserSession)).one()
        assert stored.token_hash == token_digest(raw_token)
        assert raw_token != stored.token_hash


def test_invalid_login_fails(client):
    browser, _ = client
    response = login(browser, "incorrect-password")
    assert response.status_code == 401
    assert browser.get("/api/auth/me").status_code == 401


def test_logout_requires_csrf_and_revokes(client):
    browser, _ = client
    result = login(browser)
    assert result.status_code == 200
    assert browser.post("/api/auth/logout").status_code == 403
    csrf = result.json()["csrfToken"]
    assert browser.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert browser.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client):
    browser, engine = client
    assert login(browser).status_code == 200
    with Session(engine) as db:
        record = db.exec(select(UserSession)).one()
        record.expires_at = utc_now() - timedelta(minutes=1)
        db.add(record)
        db.commit()
    assert browser.get("/api/auth/me").status_code == 401


def test_disabled_user_rejected(client):
    browser, engine = client
    with Session(engine) as db:
        user = db.exec(select(User)).one()
        user.is_active = False
        db.add(user)
        db.commit()
    assert login(browser).status_code == 401


def test_disallowed_origin_rejected(client):
    browser, _ = client
    response = browser.post(
        "/api/auth/login", json={"username": "admin_a3", "password": PASSWORD},
        headers={"Origin": "https://malicious.example"},
    )
    assert response.status_code == 403


def test_brute_force_throttling(client):
    browser, _ = client
    for _ in range(5):
        assert browser.post("/api/auth/login", json={"username": "fake_a3", "password": "bad"}).status_code == 401
    assert browser.post("/api/auth/login", json={"username": "fake_a3", "password": "bad"}).status_code == 429
