"""Read-only SQLite schema and migration preflight for secure localhost startup."""

from __future__ import annotations

import argparse
import ast
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TABLES = {
    "telemetry_readings",
    "device_states",
    "device_configs",
    "command_logs",
    "alerts",
    "users",
    "user_sessions",
    "audit_logs",
    "alembic_version",
}


def abort(message: str) -> None:
    raise RuntimeError(message)


def migration_value(tree: ast.Module, name: str):
    for node in tree.body:
        value = None

        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            ):
                value = node.value

        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                value = node.value

        if value is not None:
            return ast.literal_eval(value)

    abort(f"A672_MIGRATION_FIELD_MISSING: {name}")


def expected_migration_head() -> str:
    versions = ROOT / "database" / "alembic" / "versions"

    if not versions.is_dir():
        abort("A672_MIGRATIONS_DIRECTORY_MISSING")

    revisions = set()
    parents = set()

    files = sorted(
        path for path in versions.glob("*.py")
        if path.name != "__init__.py"
    )

    if not files:
        abort("A672_NO_MIGRATIONS")

    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))

        revision = migration_value(tree, "revision")
        parent = migration_value(tree, "down_revision")

        if not isinstance(revision, str) or revision in revisions:
            abort("A672_INVALID_OR_DUPLICATE_REVISION")

        revisions.add(revision)

        if isinstance(parent, str):
            parents.add(parent)
        elif isinstance(parent, (tuple, list)):
            parents.update(parent)
        elif parent is not None:
            abort("A672_UNSUPPORTED_MIGRATION_PARENT")

    heads = revisions - parents

    if len(heads) != 1:
        abort(f"A672_UNEXPECTED_MIGRATION_HEADS: {sorted(heads)}")

    return next(iter(heads))


def check_database(path: Path) -> None:
    if not path.is_file():
        abort("A672_DATABASE_MISSING")

    head = expected_migration_head()

    # mode=ro: never create or modify the application database.
    uri = path.resolve().as_uri() + "?mode=ro"

    with sqlite3.connect(uri, uri=True, timeout=10) as connection:
        connection.execute("PRAGMA query_only=ON")

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            abort("A672_DATABASE_INTEGRITY_FAILED")

        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        if "alembic_version" not in tables:
            abort("A672_ALEMBIC_VERSION_TABLE_MISSING")

        versions = [
            row[0] for row in connection.execute(
                "SELECT version_num FROM alembic_version"
            )
        ]

        if versions != [head]:
            abort(
                "A672_MIGRATION_HEAD_MISMATCH: "
                f"database={versions}, expected={head}"
            )

        missing = REQUIRED_TABLES - tables

        if missing:
            abort(f"A672_REQUIRED_TABLES_MISSING: {sorted(missing)}")

        admins = connection.execute(
            "SELECT COUNT(*) FROM users "
            "WHERE role='admin' AND is_active=1"
        ).fetchone()[0]

        if admins < 1:
            abort("A672_NO_ACTIVE_ADMIN")

    print("A672_DATABASE_INTEGRITY_PASS")
    print("A672_MIGRATION_HEAD_PASS:", head)
    print("A672_REQUIRED_TABLES_PASS")
    print("A672_ACTIVE_ADMIN_PASS")
    print("A672_DATABASE_PREFLIGHT_PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    args = parser.parse_args()

    try:
        check_database(Path(args.db).resolve())
    except (RuntimeError, sqlite3.Error, OSError, ValueError) as exc:
        print(f"A672_PREFLIGHT_REJECTED: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
