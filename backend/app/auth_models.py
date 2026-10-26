"""Authentication persistence models.

Import this module from app.models to register metadata with Alembic and SQLModel.
Do not return User directly from API responses: password_hash is sensitive.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_auth_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "role IN ('admin', 'operator', 'viewer')", name="ck_users_role"
        ),
    )

    id: str = Field(default_factory=new_id, primary_key=True, max_length=32)
    username: str = Field(max_length=64)
    email: str = Field(max_length=254)
    password_hash: str = Field(max_length=255)
    role: str = Field(default="viewer", max_length=16)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_auth_now)
    updated_at: datetime = Field(default_factory=utc_auth_now)


class UserSession(SQLModel, table=True):
    __tablename__ = "user_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
        Index("ix_user_sessions_user_id", "user_id"),
        Index("ix_user_sessions_expires_at", "expires_at"),
    )

    id: str = Field(default_factory=new_id, primary_key=True, max_length=32)
    user_id: str = Field(foreign_key="users.id", max_length=32)
    # Persist only SHA-256 of a cryptographically random session token.
    token_hash: str = Field(max_length=64)
    created_at: datetime = Field(default_factory=utc_auth_now)
    expires_at: datetime
    revoked_at: datetime | None = Field(default=None)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_actor_created_at", "actor_user_id", "created_at"),
    )

    id: int | None = Field(default=None, primary_key=True)
    actor_user_id: str | None = Field(default=None, foreign_key="users.id", max_length=32)
    action: str = Field(max_length=64)
    target_type: str | None = Field(default=None, max_length=32)
    target_id: str | None = Field(default=None, max_length=64)
    outcome: str = Field(default="success", max_length=16)
    ip_address: str | None = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=utc_auth_now)
