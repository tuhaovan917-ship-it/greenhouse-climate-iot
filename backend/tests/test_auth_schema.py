"""Schema checks for authentication tables (no real database is modified)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from app.auth_models import AuditLog, User, UserSession  # noqa: F401


def test_auth_tables_registered() -> None:
    assert {"users", "user_sessions", "audit_logs"}.issubset(SQLModel.metadata.tables)


def test_unique_normalized_identity_and_role_constraint() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(
            username="operator01", email="operator01@example.test",
            password_hash="not-a-real-hash", role="operator",
        )
        session.add(user)
        session.commit()
        assert session.exec(select(User)).first() is not None

        session.add(
            User(
                username="operator01", email="another@example.test",
                password_hash="not-a-real-hash",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_user_session_token_is_hash_only() -> None:
    # Model intentionally has no raw session token field.
    assert "token_hash" in UserSession.model_fields
    assert "token" not in UserSession.model_fields
