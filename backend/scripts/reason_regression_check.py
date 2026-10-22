"""Reproduce the exact sequence Member 1 reported, with the real firmware payload.

Scenario (from the report):
  1. switch the device to MANUAL, water level low
  2. send the mist command -> REJECTED with reason NO_WATER
  3. water back to normal
  4. send a valid command (fan) -> APPLIED, the firmware omits the reason key
  5. GET /api/state must no longer show the old NO_WATER reason

The payloads are built exactly like firmware/src/main.cpp does:
  - the reason key is only present when the firmware has one
  - a new command resets the firmware reason to an empty string

Usage:
    .venv/Scripts/python scripts/reason_regression_check.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB_PATH = Path(tempfile.gettempdir()) / "greenhouse_reason_check.db"
for suffix in ("", "-wal", "-shm"):
    candidate = Path(str(DB_PATH) + suffix)
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["MQTT_ENABLED"] = "0"
os.environ["DEVICE_ID"] = "greenhouse-01"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import createTablesForTest, sessionScope  # noqa: E402
from app.main import app  # noqa: E402
from app.services import ingest  # noqa: E402
from app.services.commands import commandService  # noqa: E402

createTablesForTest()

DEVICE = "greenhouse-01"
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    if not condition:
        failures.append(name)


def firmwareState(commandId: str | None, result: str | None, reason: str | None) -> dict:
    """Same shape as firmware publishDeviceState(): the reason key is omitted
    when the firmware has no reason for the current command."""
    payload: dict = {
        "deviceId": DEVICE,
        "mode": "MANUAL",
        "fan": False,
        "mist": False,
        "lamp": False,
        "failsafeActive": False,
    }
    if commandId:
        payload["lastCommandId"] = commandId
        payload["lastCommandResult"] = result
    if reason:
        payload["reason"] = reason
    return payload


def main() -> int:
    client = TestClient(app)

    with sessionScope() as session:
        mist = commandService.createPending(session, DEVICE, "mist", True)
        mistId = mist.command_id
        session.commit()

    # 1 + 2. The device refuses the pump: empty tank.
    import anyio

    anyio.run(
        lambda: ingest.handleState(
            DEVICE, firmwareState(mistId, "REJECTED", "NO_WATER")
        )
    )
    state = client.get("/api/state").json()
    check("buoc 2: state bao REJECTED", state["lastCommandResult"] == "REJECTED", str(state)[:90])
    check("buoc 2: state giu ly do NO_WATER", state["reason"] == "NO_WATER", str(state.get("reason")))

    # 2b. The firmware republishes its state on a timer without the reason key.
    #     The known reason must survive that.
    anyio.run(lambda: ingest.handleState(DEVICE, firmwareState(mistId, "REJECTED", None)))
    state = client.get("/api/state").json()
    check(
        "republish cung lenh giu ly do",
        state["reason"] == "NO_WATER",
        str(state.get("reason")),
    )

    # 3 + 4. The tank recovers, a new command succeeds. The firmware cleared its
    # reason, so the payload has no reason key at all.
    with sessionScope() as session:
        fan = commandService.createPending(session, DEVICE, "fan", True)
        fanId = fan.command_id
        session.commit()

    anyio.run(lambda: ingest.handleState(DEVICE, firmwareState(fanId, "APPLIED", None)))

    # 5. The old reason must be gone.
    state = client.get("/api/state").json()
    check("buoc 5: lastCommandResult = APPLIED", state["lastCommandResult"] == "APPLIED", str(state)[:90])
    check("buoc 5: reason da duoc xoa", state["reason"] is None, f"van con: {state['reason']!r}")
    check("buoc 5: lastCommandId la lenh moi", state["lastCommandId"] == fanId, str(state.get("lastCommandId")))

    rows = {row["commandId"]: row for row in client.get("/api/commands").json()["data"]}
    check("buoc 5: lenh moi co reason null", rows[fanId]["reason"] is None, str(rows[fanId]["reason"]))
    check("buoc 5: lenh cu giu ly do rieng", rows[mistId]["reason"] == "NO_WATER", str(rows[mistId]["reason"]))

    print()
    if failures:
        print(f"REASON REGRESSION CHECK FAILED ({len(failures)}): {failures}")
        return 1
    print("REASON REGRESSION CHECK PASSED: lenh moi xoa ly do cu, republish giu ly do")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
