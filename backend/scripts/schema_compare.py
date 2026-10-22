"""Compare an Alembic-migrated database with the Backend SQLModel metadata.

Member 3 owns the Alembic migrations in `database/`, Member 2 owns the table
models in `backend/app/models.py`. Both must describe the same schema, so this
script reads a migrated SQLite database and reports every difference against
the models: missing tables, columns, types, nullability, primary keys, indexes
and check constraints.

Usage:
    DATABASE_URL=sqlite:///./migrated.db .venv/Scripts/python scripts/schema_compare.py
    # or
    .venv/Scripts/python scripts/schema_compare.py path/to/migrated.db
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect  # noqa: E402

from app.models import SQLModel  # noqa: E402


def databasePath() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    url = os.environ.get("DATABASE_URL", "sqlite:///./greenhouse.db")
    return url.split("///", 1)[-1]


def modelTables() -> dict[str, SQLModel.__class__]:
    return {name: table for name, table in SQLModel.metadata.tables.items()}


def main() -> int:
    path = databasePath()
    if not Path(path).is_file():
        print(f"[FAIL] database khong ton tai: {path}")
        return 1

    connection = sqlite3.connect(path)
    engine = create_engine(f"sqlite:///{path}")
    inspector = inspect(engine)
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        print(f"[{'PASS' if condition else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
        if not condition:
            failures.append(name)

    tables = modelTables()
    actualTables = set(inspector.get_table_names())
    # Alembic keeps its own bookkeeping table; it is not part of the schema.
    actualTables.discard("alembic_version")

    print("=== 1. BANG ===")
    for name in sorted(tables):
        check(f"table {name} ton tai", name in actualTables)
    for name in sorted(actualTables - set(tables)):
        check(f"table {name} khong co trong models", False, "thua trong DB")

    print()
    print("=== 2. COT ===")
    for name, table in sorted(tables.items()):
        if name not in actualTables:
            continue
        modelColumns = {column.name: column for column in table.columns}
        actualColumns = {column["name"]: column for column in inspector.get_columns(name)}
        for columnName, modelColumn in modelColumns.items():
            actual = actualColumns.get(columnName)
            if actual is None:
                check(f"{name}.{columnName} ton tai", False)
                continue
            nullableMatch = actual["nullable"] == modelColumn.nullable
            check(
                f"{name}.{columnName} kieu + nullability",
                nullableMatch,
                f"db.nullable={actual['nullable']} model.nullable={modelColumn.nullable}",
            )
        for columnName in sorted(set(actualColumns) - set(modelColumns)):
            check(f"{name}.{columnName} khong thua", False)

    print()
    print("=== 3. PRIMARY KEY ===")
    for name, table in sorted(tables.items()):
        if name not in actualTables:
            continue
        modelPk = [column.name for column in table.primary_key.columns]
        actualPk = inspector.get_pk_constraint(name).get("constrained_columns") or []
        check(f"{name} primary key", sorted(modelPk) == sorted(actualPk), f"db={actualPk} model={modelPk}")

    print()
    print("=== 4. INDEX ===")
    for name, table in sorted(tables.items()):
        if name not in actualTables:
            continue
        modelIndexes = {
            index.name: sorted(column.name for column in index.columns)
            for index in table.indexes
        }
        actualIndexes = {
            index["name"]: index["column_names"] for index in inspector.get_indexes(name)
        }
        for indexName, columns in modelIndexes.items():
            actual = actualIndexes.get(indexName)
            check(
                f"index {indexName}",
                actual is not None and sorted(actual) == sorted(columns),
                f"db={actual}",
            )
        for indexName in sorted(set(actualIndexes) - set(modelIndexes)):
            check(f"index {indexName} khong thua", False)

    print()
    print("=== 5. CHECK CONSTRAINT ===")
    for name, table in sorted(tables.items()):
        if name not in actualTables:
            continue
        modelConstraints = {
            constraint.name: str(constraint.sqltext)
            for constraint in table.constraints
            if constraint.__class__.__name__ == "CheckConstraint"
        }
        ddlRows = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchall()
        ddl = ddlRows[0][0] if ddlRows else ""
        for constraintName, expression in modelConstraints.items():
            check(
                f"constraint {constraintName} trong DDL",
                constraintName in ddl,
                ddl[:90],
            )
            check(
                f"constraint {constraintName} cung bieu thuc",
                expression.replace(" ", "") in ddl.replace(" ", "").replace("(", "(").replace(")", ")"),
                expression,
            )

    connection.close()
    print()
    if failures:
        print(f"SCHEMA COMPARE FAILED ({len(failures)}): {failures}")
        return 1
    print("SCHEMA COMPARE PASSED: migration va models giong nhau")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
