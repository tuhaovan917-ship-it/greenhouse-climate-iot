from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

repository_root = Path(__file__).resolve().parents[2]
backend_root = Path(
    os.environ.get("BACKEND_SOURCE_DIR", repository_root / "backend")
).resolve()

if not (backend_root / "app" / "models.py").is_file():
    raise RuntimeError(
        "Khong tim thay backend/app/models.py. Merge feat/backend hoac dat "
        "BACKEND_SOURCE_DIR toi thu muc backend da checkout."
    )

sys.path.insert(0, str(backend_root))

from app.models import SQLModel  # noqa: E402

target_metadata = SQLModel.metadata


def getDatabaseUrl() -> str:
    return os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))


def renderItem(type_: str, item: object, _autogen_context: object) -> str | bool:
    """Render SQLModel wrapper types as stable public SQLAlchemy types."""
    if type_ != "type" or not item.__class__.__module__.startswith("sqlmodel."):
        return False

    if item.__class__.__name__ == "AutoString":
        length = getattr(item, "length", None)
        return f"sa.String(length={length})" if length else "sa.String()"

    if item.__class__.__name__ == "UTCDateTime":
        return "sa.DateTime(timezone=True)"

    return False


def runMigrationsOffline() -> None:
    context.configure(
        url=getDatabaseUrl(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_item=renderItem,
    )

    with context.begin_transaction():
        context.run_migrations()


def runMigrationsOnline() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = getDatabaseUrl()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=connection.dialect.name == "sqlite",
            render_item=renderItem,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    runMigrationsOffline()
else:
    runMigrationsOnline()
