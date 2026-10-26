"""Shared router helpers: API key guard and query parsing."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlmodel import Session
from app.database import getSession
from app.services.auth import current_session
from app.services.authz import require_viewer, require_control

from app.config import settings


def requireApiKey(xApiKey: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Protect write endpoints when the Backend is exposed to the LAN.

    Contract section 5: localhost demo leaves API_KEY empty and this check
    stays off; setting API_KEY turns it on for POST /commands and /config.
    """
    if not settings.api_key:
        return
    if xApiKey != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thieu hoac sai X-API-Key",
        )


def badRequest(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def enforce_read(request: Request, session: Session = Depends(getSession)) -> None:
    # Strict mode: session and Viewer+; legacy mode: no auth needed.
    if settings.auth_enforcement_enabled:
        require_viewer(auth=current_session(request, session))


def enforce_write(
    request: Request,
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: Session = Depends(getSession),
) -> None:
    # Strict mode: role and CSRF, legacy mode: existing optional API key.
    if settings.auth_enforcement_enabled:
        require_control(request=request, x_csrf_token=x_csrf_token,
                        auth=current_session(request, session))
    else:
        requireApiKey(x_api_key)
