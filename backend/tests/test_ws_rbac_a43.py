"""A4.3 WebSocket session, origin and in-flight revocation checks.

Uses standalone app and in-memory SQLite, never opens the real greenhouse.db.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.websockets import WebSocketDisconnect

from app.auth_models import User, UserSession
from app.database import getSession
from app.routers import auth as authRouter
from app.routers import ws as wsRouter
from app.services.auth import hash_password, utc_now

PASSWORD = "a43-nonsecret-test-password"
ORIGIN = "http://localhost:5173"


@pytest.fixture()
def env(monkeypatch):
    db_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(db_engine)
    with Session(db_engine) as db:
        for role in ("viewer", "operator", "admin"):
            db.add(User(username=f"{role}_a43", email=f"{role}_a43@example.test",
                        password_hash=hash_password(PASSWORD), role=role))
        db.commit()

    # WS code intentionally uses short sessions against its own engine, so
    # it can verify revoked sessions after they change in another HTTP request.
    monkeypatch.setattr(wsRouter, "engine", db_engine)
    monkeypatch.setattr(wsRouter, "settings", replace(wsRouter.settings, auth_enforcement_enabled=True))
    monkeypatch.setattr(wsRouter, "ACCESS_RECHECK_S", 0.1)
    isolated = FastAPI()
    isolated.include_router(authRouter.router)
    isolated.include_router(wsRouter.router)

    def test_session():
        with Session(db_engine) as db:
            yield db

    isolated.dependency_overrides[getSession] = test_session
    try:
        with TestClient(isolated) as client:
            yield client, db_engine
    finally:
        db_engine.dispose()


def login(client, role="viewer"):
    res = client.post("/api/auth/login", json={"username": f"{role}_a43", "password": PASSWORD})
    assert res.status_code == 200, res.text
    return res.json()["csrfToken"]


def expect_denied(client, headers=None):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws", headers=headers or {}):
            pass
    assert e.value.code == 1008


def test_reject_anonymous_websocket(env):
    client, _ = env
    expect_denied(client, {"Origin": ORIGIN})


def test_reject_untrusted_origin_even_if_logged_in(env):
    client, _ = env
    login(client)
    expect_denied(client, {"Origin": "https://evil.example"})


def test_reject_missing_origin_even_if_logged_in(env):
    client, _ = env
    login(client)
    expect_denied(client)


@pytest.mark.parametrize("role", ["viewer", "operator", "admin"])
def test_signed_in_roles_can_stream(env, monkeypatch, role):
    client, _ = env
    login(client, role)
    monkeypatch.setattr(wsRouter, "HEARTBEAT_S", 0.02)
    with client.websocket_connect("/ws", headers={"Origin": ORIGIN}) as ws:
        assert ws.receive_json() == {"type": "ping"}


def test_logout_revokes_open_websocket(env):
    client, _ = env
    csrf = login(client)
    with client.websocket_connect("/ws", headers={"Origin": ORIGIN}) as ws:
        result = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        assert result.status_code == 200, result.text
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
        assert e.value.code == 1008


def test_expired_session_closes_open_websocket(env):
    client, db_engine = env
    login(client)
    with client.websocket_connect("/ws", headers={"Origin": ORIGIN}) as ws:
        with Session(db_engine) as db:
            record = db.exec(select(UserSession)).one()
            record.expires_at = utc_now() - timedelta(minutes=1)
            db.add(record)
            db.commit()
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
        assert e.value.code == 1008


def test_disabled_user_closes_open_websocket(env):
    client, db_engine = env
    login(client)
    with client.websocket_connect("/ws", headers={"Origin": ORIGIN}) as ws:
        with Session(db_engine) as db:
            user = db.exec(select(User).where(User.username == "viewer_a43")).one()
            user.is_active = False
            db.add(user)
            db.commit()
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
        assert e.value.code == 1008


def test_legacy_mode_remains_available(env, monkeypatch):
    client, _ = env
    monkeypatch.setattr(
        wsRouter,
        "settings",
        replace(wsRouter.settings, auth_enforcement_enabled=False),
    )
    monkeypatch.setattr(wsRouter, "HEARTBEAT_S", 0.02)

    # Wait for the server to clean up the socket before TestClient exits.
    # This avoids racing its cancellation of the ASGI task.
    disconnected = Event()
    original_disconnect = wsRouter.wsManager.disconnect

    async def observed_disconnect(device_id, websocket):
        await original_disconnect(device_id, websocket)
        disconnected.set()

    monkeypatch.setattr(
        wsRouter.wsManager, "disconnect", observed_disconnect
    )

    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json() == {"type": "ping"}

        # Explicit close, then confirm server-side cleanup.
        ws.close()
        assert disconnected.wait(timeout=5), (
            "Legacy WebSocket did not finish disconnect cleanup"
        )
