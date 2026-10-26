"""Isolated RBAC/CSRF tests: no production routes or SQLite files touched."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth_models import User
from app.database import getSession
from app.routers.auth import router as auth_router
from app.services.auth import hash_password
from app.services.authz import (
    require_admin,
    require_admin_write,
    require_control,
    require_viewer,
)

PASSWORD = "a4-very-long-demo-password"


@pytest.fixture()
def browser():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for role in ("admin", "operator", "viewer"):
            session.add(
                User(
                    username=f"{role}_a4",
                    email=f"{role}@example.test",
                    password_hash=hash_password(PASSWORD),
                    role=role,
                )
            )
        session.commit()

    isolated = FastAPI()
    isolated.include_router(auth_router)
    routes = APIRouter(prefix="/__a4")

    @routes.get("/read", dependencies=[Depends(require_viewer)])
    def read():
        return {"ok": True}

    @routes.get("/admin", dependencies=[Depends(require_admin)])
    def admin_read():
        return {"ok": True}

    @routes.post("/control", dependencies=[Depends(require_control)])
    def control():
        return {"ok": True}

    @routes.post("/admin", dependencies=[Depends(require_admin_write)])
    def admin_write():
        return {"ok": True}

    isolated.include_router(routes)

    def override_session():
        with Session(engine) as session:
            yield session

    isolated.dependency_overrides[getSession] = override_session

    with TestClient(isolated) as client:
        yield client

    engine.dispose()


def sign_in(client: TestClient, role: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": f"{role}_a4", "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrfToken"]


def test_no_session_read_and_write_are_401(browser):
    assert browser.get("/__a4/read").status_code == 401
    assert browser.post("/__a4/control").status_code == 401


@pytest.mark.parametrize("role", ["admin", "operator", "viewer"])
def test_all_roles_can_read(browser, role):
    sign_in(browser, role)
    assert browser.get("/__a4/read").status_code == 200


def test_viewer_cannot_control_even_with_valid_csrf(browser):
    csrf = sign_in(browser, "viewer")
    assert browser.post("/__a4/control", headers={"X-CSRF-Token": csrf}).status_code == 403
    assert browser.get("/__a4/admin").status_code == 403


@pytest.mark.parametrize("role", ["admin", "operator"])
def test_controller_roles_can_control(browser, role):
    csrf = sign_in(browser, role)
    assert browser.post("/__a4/control", headers={"X-CSRF-Token": csrf}).status_code == 200


def test_no_csrf_is_rejected(browser):
    sign_in(browser, "operator")
    assert browser.post("/__a4/control").status_code == 403


def test_wrong_csrf_is_rejected(browser):
    sign_in(browser, "operator")
    assert browser.post("/__a4/control", headers={"X-CSRF-Token": "nope"}).status_code == 403


def test_untrusted_origin_is_rejected(browser):
    csrf = sign_in(browser, "operator")
    assert browser.post(
        "/__a4/control",
        headers={"X-CSRF-Token": csrf, "Origin": "https://attacker.example"},
    ).status_code == 403


def test_operator_cannot_admin_write(browser):
    csrf = sign_in(browser, "operator")
    assert browser.post("/__a4/admin", headers={"X-CSRF-Token": csrf}).status_code == 403


def test_admin_can_admin_write(browser):
    csrf = sign_in(browser, "admin")
    assert browser.post("/__a4/admin", headers={"X-CSRF-Token": csrf}).status_code == 200
