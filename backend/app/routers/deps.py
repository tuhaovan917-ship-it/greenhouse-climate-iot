"""Shared router helpers: API key guard and query parsing."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

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
