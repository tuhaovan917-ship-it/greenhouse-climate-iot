"""Password and opaque database-backed session primitives (A3).

A3 exposes login/logout/me only. Existing business endpoints are not protected
until A4 updates their dependencies and WebSocket handshake.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from pwdlib import PasswordHash
from sqlalchemy import or_
from sqlmodel import Session, select

from app.auth_models import User, UserSession
from app.database import getSession

COOKIE_NAME = "greenhouse_session"
_PASSWORD = PasswordHash.recommended()
# Verify absent users against a real Argon2id hash to reduce account enumeration.
_DUMMY_HASH = _PASSWORD.hash("not-the-real-password")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """SQLite may deserialize timezone-aware DateTime as a naive UTC value."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def hash_password(password: str) -> str:
    return _PASSWORD.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _PASSWORD.verify(password, password_hash)


def token_digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def csrf_for_token(raw: str) -> str:
    # Token is unguessable and never sent in JSON responses; derive a separate
    # per-session anti-CSRF value without another database schema migration.
    return hmac.new(raw.encode("utf-8"), b"greenhouse-csrf-v1", hashlib.sha256).hexdigest()


def lookup_user(session: Session, identity: str) -> User | None:
    # Bootstrap and future account creation must store normalized lowercase
    # usernames/emails, and forbid case-insensitive duplicates.
    identity = identity.strip().casefold()
    return session.exec(
        select(User).where(or_(User.username == identity, User.email == identity))
    ).first()


class LoginLimiter:
    """Small single-process limiter for the local demonstration environment.

    A deployment with multiple workers needs a shared limiter (e.g. Redis).
    """

    WINDOW_SECONDS = 900
    MAX_FAILURES = 5

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[tuple[str, str], deque[float]] = {}

    def blocked(self, key: tuple[str, str]) -> bool:
        now = time.monotonic()
        with self._lock:
            values = self._failures.get(key)
            if values is None:
                return False
            while values and now - values[0] > self.WINDOW_SECONDS:
                values.popleft()
            if not values:
                self._failures.pop(key, None)
                return False
            return len(values) >= self.MAX_FAILURES

    def fail(self, key: tuple[str, str]) -> None:
        now = time.monotonic()
        with self._lock:
            values = self._failures.setdefault(key, deque())
            while values and now - values[0] > self.WINDOW_SECONDS:
                values.popleft()
            values.append(now)

    def clear(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_limiter = LoginLimiter()


def authenticate_user(session: Session, identity: str, password: str) -> User | None:
    user = lookup_user(session, identity)
    candidate_hash = user.password_hash if user is not None else _DUMMY_HASH
    valid_password = verify_password(password, candidate_hash)
    if user is None or not valid_password or not user.is_active:
        return None
    return user


def create_session(session: Session, user_id: str, hours: int) -> str:
    raw = secrets.token_urlsafe(32)
    now = utc_now()
    session.add(
        UserSession(
            user_id=user_id,
            token_hash=token_digest(raw),
            created_at=now,
            expires_at=now + timedelta(hours=hours),
        )
    )
    session.commit()  # No browser cookie should be sent before DB commit succeeds.
    return raw


def current_session(request: Request, db: Session = Depends(getSession)) -> tuple[User, UserSession, str]:
    raw = request.cookies.get(COOKIE_NAME, "")
    if not (32 <= len(raw) <= 256):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    record = db.exec(select(UserSession).where(UserSession.token_hash == token_digest(raw))).first()
    if record is None or record.revoked_at is not None or as_utc(record.expires_at) <= utc_now():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")
    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable")
    return user, record, raw
