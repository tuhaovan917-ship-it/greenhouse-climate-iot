"""Create a verified SQLite snapshot at a NEW external destination.

Also supports testing restoration by copying a snapshot to a new
temporary database. Never replaces an existing database.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def copy_database(source: Path, destination: Path) -> None:
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()

    if not source.is_file():
        raise RuntimeError("A672D_SOURCE_MISSING")

    if source == destination:
        raise RuntimeError("A672D_SOURCE_EQUALS_DESTINATION")

    if destination == ROOT or ROOT in destination.parents:
        raise RuntimeError("A672D_DESTINATION_INSIDE_REPOSITORY")

    if not destination.parent.is_dir():
        raise RuntimeError("A672D_DESTINATION_DIRECTORY_MISSING")

    if destination.exists():
        raise RuntimeError("A672D_REFUSE_OVERWRITE")

    # Never overwrite an existing destination.
    fd = os.open(
        destination,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )
    os.close(fd)

    try:
        source_uri = source.as_uri() + "?mode=ro"

        with closing(
            sqlite3.connect(source_uri, uri=True, timeout=30)
        ) as original:
            original.execute("PRAGMA query_only=ON")

            with closing(
                sqlite3.connect(str(destination), timeout=30)
            ) as copy:
                original.backup(copy, pages=256, sleep=0.1)

        # Verify using a fresh, read-only connection.
        destination_uri = destination.as_uri() + "?mode=ro"

        with closing(
            sqlite3.connect(destination_uri, uri=True, timeout=30)
        ) as verified:
            result = verified.execute(
                "PRAGMA integrity_check"
            ).fetchall()

            if result != [("ok",)]:
                raise RuntimeError(
                    "A672D_SNAPSHOT_INTEGRITY_FAILED"
                )

    except Exception:
        # Remove only files created for this new destination.
        for item in (
            destination,
            Path(str(destination) + "-wal"),
            Path(str(destination) + "-shm"),
        ):
            if item.exists():
                item.unlink()
        raise

    print("A672D_SQLITE_BACKUP_API_PASS")
    print("A672D_SNAPSHOT_INTEGRITY_PASS")
    print("A672D_SNAPSHOT_PATH:", destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--dest", required=True)
    args = parser.parse_args()

    try:
        copy_database(Path(args.source), Path(args.dest))
    except (OSError, sqlite3.Error, RuntimeError) as error:
        print(
            "A672D_COPY_REJECTED:",
            error,
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
