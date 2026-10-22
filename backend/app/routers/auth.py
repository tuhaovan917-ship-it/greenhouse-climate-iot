"""Authentication endpoints (A3): login, logout, current-user.

Do not enable authorization of the existing REST/WS endpoints until A4.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from app.auth_models import User
from app.config import settings
from app.database import getSession
from app.services.auth import (
    COOKIE_NAME, authenticate_user, create_session, csrf_for_token,
    current_session, login_limiter, utc_now,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class PublicUser(BaseModel):
    id: str
    username: str
    email: str
    role: str
    isActive: bool


def public_user(user: User) -> PublicUser:
    return PublicUser(
        id=user.id, username=user.username, email=user.email,
        role=user.role, isActive=user.is_active,
    )


def guard_origin(request: Request) -> None:
    """Reject unexpected browser origins for cookie-setting/mutating routes."""
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        raise HTTPException(status_code=403, detail="Origin not allowed")


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(getSession)) -> dict:
    guard_origin(request)
    key = (request.client.host if request.client else "unknown", body.username.strip().casefold())
    if login_limiter.blocked(key):
        raise HTTPException(status_code=429, detail="Too many login attempts", headers={"Retry-After": "900"})

    user = authenticate_user(db, body.username, body.password)
    if user is None:
        login_limiter.fail(key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    login_limiter.clear(key)
    token = create_session(db, user.id, settings.auth_session_hours)
    response.set_cookie(
        key=COOKIE_NAME, value=token, httponly=True,
        secure=settings.auth_cookie_secure, samesite="lax",
        max_age=settings.auth_session_hours * 3600, path="/",
    )
    no_store(response)
    return {"user": public_user(user).model_dump(), "csrfToken": csrf_for_token(token)}


@router.get("/me")
def me(response: Response, auth: tuple = Depends(current_session)) -> dict:
    user, _, token = auth
    no_store(response)
    return {"user": public_user(user).model_dump(), "csrfToken": csrf_for_token(token)}


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    auth: tuple = Depends(current_session),
    db: Session = Depends(getSession),
) -> dict[str, str]:
    guard_origin(request)
    _, record, raw = auth
    if not x_csrf_token or not hmac.compare_digest(csrf_for_token(raw), x_csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    record.revoked_at = utc_now()
    db.add(record)
    db.commit()
    response.delete_cookie(key=COOKIE_NAME, path="/", samesite="lax", secure=settings.auth_cookie_secure, httponly=True)
    no_store(response)
    return {"status": "logged_out"}
