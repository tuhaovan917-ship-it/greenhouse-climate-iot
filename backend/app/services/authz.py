"""Authorization building blocks for Greenhouse (A4.1).

These dependencies do not protect any existing business route until a later
change explicitly attaches them. Never assume merely importing this module
activates RBAC.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, Request, status

from app.auth_models import User, UserSession
from app.config import settings
from app.services.auth import csrf_for_token, current_session

AuthContext = tuple[User, UserSession, str]


def _enforce_role(user: User, roles: frozenset[str]) -> User:
    if user.role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return user


def require_viewer(auth: AuthContext = Depends(current_session)) -> User:
    """Any signed-in, active user can read dashboard data."""
    return _enforce_role(auth[0], frozenset({"viewer", "operator", "admin"}))


def require_operator(auth: AuthContext = Depends(current_session)) -> User:
    """Operator and Admin may manage equipment."""
    return _enforce_role(auth[0], frozenset({"operator", "admin"}))


def require_admin(auth: AuthContext = Depends(current_session)) -> User:
    """Administration of users and security logs."""
    return _enforce_role(auth[0], frozenset({"admin"}))


def _verify_mutation(
    request: Request,
    csrf_header: str | None,
    raw_session_token: str,
) -> None:
    # A request without Origin can be from a non-browser client, but it still
    # must possess a valid CSRF token. Disallow any unexpected browser origin.
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        raise HTTPException(status_code=403, detail="Origin not allowed")

    expected = csrf_for_token(raw_session_token)
    if not csrf_header or not hmac.compare_digest(csrf_header, expected):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def require_control(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    auth: AuthContext = Depends(current_session),
) -> User:
    """For POST /api/commands, POST /api/config and other control mutations."""
    user = _enforce_role(auth[0], frozenset({"operator", "admin"}))
    _verify_mutation(request, x_csrf_token, auth[2])
    return user


def require_admin_write(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    auth: AuthContext = Depends(current_session),
) -> User:
    """Admin-only modifying endpoints, e.g. create/disable account."""
    user = _enforce_role(auth[0], frozenset({"admin"}))
    _verify_mutation(request, x_csrf_token, auth[2])
    return user
