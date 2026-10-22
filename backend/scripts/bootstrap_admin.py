"""Create the FIRST admin account only, with no default credentials.

Run from backend/ with `..\\backend\\.venv\\Scripts\\python.exe scripts/bootstrap_admin.py`
(or `.\\.venv\\Scripts\\python.exe scripts/bootstrap_admin.py` from backend/).
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

# Allow direct execution without pip installing this repository as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.auth_models import User  # noqa: E402
from app.database import engine  # noqa: E402
from app.services.auth import hash_password  # noqa: E402


def main() -> int:
    if not inspect(engine).has_table("users"):
        print("ERROR: Run Alembic migration 20261022_02 on the target DB first.")
        return 1
    with Session(engine) as session:
        if session.exec(select(User).limit(1)).first() is not None:
            print("ERROR: Users already exist. Bootstrap is for the first admin only.")
            return 1

        username = input("Admin username: ").strip().casefold()
        email = input("Admin email: ").strip().casefold()
        if not (3 <= len(username) <= 64 and username.isascii() and username.replace("_", "").replace("-", "").isalnum()):
            print("ERROR: Username must be 3-64 ASCII letters/digits/_/-.")
            return 1
        if not ("@" in email and "." in email.rpartition("@")[2] and len(email) <= 254):
            print("ERROR: Invalid email.")
            return 1
        password = getpass.getpass("Admin password (12+ characters): ")
        confirmation = getpass.getpass("Repeat password: ")
        if len(password) < 12 or password != confirmation:
            print("ERROR: Password too short or values do not match.")
            return 1
        session.add(User(username=username, email=email, password_hash=hash_password(password), role="admin", is_active=True))
        session.commit()
        print("ADMIN_CREATED:", username)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
