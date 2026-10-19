"""Timeout and late-response checks (docs/api-contract.md v0.2.2 section 3.5).

1. A command with no device reply becomes TIMEOUT after COMMAND_TIMEOUT_S.
2. A reply that arrives after TIMEOUT still wins (last-write-wins) and is
   reported with wasLate=true.
3. The command row keeps exactly one result; duplicate QoS 1 replies are no-ops.

Run with a short timeout, e.g.:
    COMMAND_TIMEOUT_S=1 .venv/Scripts/python scripts/timeout_check.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB_PATH = Path(tempfile.gettempdir()) / "greenhouse_timeout_check.db"
for suffix in ("", "-wal", "-shm"):
    candidate = Path(str(DB_PATH) + suffix)
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["MQTT_ENABLED"] = "0"
os.environ["AUTO_CREATE_TABLES"] = "1"
os.environ["COMMAND_TIMEOUT_S"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import createTablesForTest  # noqa: E402
from app.main import app  # noqa: E402
from app.services import ingest  # noqa: E402
from app.services.state import stateService  # noqa: E402

createTablesForTest()

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    if not condition:
        failures.append(name)


def send(coro) -> None:
    import anyio

    anyio.run(lambda: coro)


def commandRow(client: TestClient, commandId: str) -> dict:
    for row in client.get("/api/commands").json()["data"]:
        if row["commandId"] == commandId:
            return row
    return {}


def _waitForWs(socket, wanted: str, maxReads: int = 6) -> dict:  # noqa: ANN001
    for _ in range(maxReads):
        message = socket.receive_json()
        if message.get("type") == wanted:
            return message
    return {}


def main() -> int:
    with TestClient(app) as client:
        stateService.markOnline("greenhouse-01", True)

        # --- 1. silent device -> TIMEOUT ---
        from app.database import sessionScope
        from app.services.commands import commandService

        with sessionScope() as session:
            log = commandService.createPending(session, "greenhouse-01", "fan", True)
            commandId = log.command_id
            session.commit()

        # Arm the real timer the REST endpoint uses and let it fire.
        async def _letTimeoutFire() -> None:
            commandService.bindLoop(asyncio.get_running_loop())
            commandService.scheduleTimeout(commandId)
            await asyncio.sleep(2.0)

        send(_letTimeoutFire())

        row = commandRow(client, commandId)
        check("silent command becomes TIMEOUT", row.get("status") == "TIMEOUT", str(row.get("status")))
        check("timeout reason recorded", row.get("reason") == "TIMEOUT", str(row.get("reason")))
        check("completedAt set on timeout", row.get("completedAt") is not None)

        # --- 2. late reply wins over TIMEOUT ---
        send(
            ingest.handleState(
                "greenhouse-01",
                {
                    "deviceId": "greenhouse-01",
                    "mode": "MANUAL",
                    "fan": True,
                    "mist": False,
                    "lamp": False,
                    "failsafeActive": False,
                    "lastCommandId": commandId,
                    "lastCommandResult": "APPLIED",
                },
            )
        )
        row = commandRow(client, commandId)
        check("late reply overwrites TIMEOUT", row.get("status") == "APPLIED", str(row.get("status")))
        check("one row only", len(client.get("/api/commands").json()["data"]) == 1)

        # --- 3. duplicate late reply is a no-op ---
        before = commandRow(client, commandId).get("completedAt")
        send(
            ingest.handleState(
                "greenhouse-01",
                {
                    "deviceId": "greenhouse-01",
                    "mode": "MANUAL",
                    "fan": True,
                    "mist": False,
                    "lamp": False,
                    "failsafeActive": False,
                    "lastCommandId": commandId,
                    "lastCommandResult": "APPLIED",
                },
            )
        )
        after = commandRow(client, commandId)
        check("duplicate reply does not rewrite completedAt", after.get("completedAt") == before, str(after.get("completedAt")))
        check("still APPLIED", after.get("status") == "APPLIED")

        # --- 4. WS command_result shape, then a genuine late push ---
        with client.websocket_connect("/ws?deviceId=greenhouse-01") as socket:
            # 4a. Reply for an already-APPLIED command is a normal update.
            send(
                ingest.handleState(
                    "greenhouse-01",
                    {
                        "deviceId": "greenhouse-01",
                        "mode": "MANUAL",
                        "fan": True,
                        "mist": False,
                        "lamp": False,
                        "failsafeActive": False,
                        "lastCommandId": commandId,
                        "lastCommandResult": "REJECTED",
                        "reason": "NO_WATER",
                    },
                )
            )
            message = _waitForWs(socket, "command_result")
            check("normal reply has wasLate=false", message["data"]["wasLate"] is False, json.dumps(message["data"]))

            # 4b. A fresh command that times out, then replies late.
            with sessionScope() as session:
                late = commandService.createPending(session, "greenhouse-01", "mist", True)
                lateId = late.command_id
                session.commit()

            async def _timeoutThenLate() -> None:
                commandService.bindLoop(asyncio.get_running_loop())
                commandService.scheduleTimeout(lateId)
                await asyncio.sleep(2.0)

            send(_timeoutThenLate())
            check("second command timed out", commandRow(client, lateId).get("status") == "TIMEOUT")

            send(
                ingest.handleState(
                    "greenhouse-01",
                    {
                        "deviceId": "greenhouse-01",
                        "mode": "MANUAL",
                        "fan": True,
                        "mist": False,
                        "lamp": False,
                        "failsafeActive": True,
                        "lastCommandId": lateId,
                        "lastCommandResult": "REJECTED",
                        "reason": "NO_WATER",
                    },
                )
            )
            lateMessage = _waitForWs(socket, "command_result")
            check(
                "late reply flagged wasLate=true",
                lateMessage["data"]["wasLate"] is True,
                json.dumps(lateMessage["data"]),
            )
            check("late result is REJECTED/NO_WATER", lateMessage["data"]["result"] == "REJECTED")
            check("late row updated", commandRow(client, lateId).get("status") == "REJECTED")
            check("command_result never PENDING", "PENDING" not in json.dumps([lateMessage]))

    print()
    if failures:
        print(f"TIMEOUT CHECK FAILED ({len(failures)}): {failures}")
        return 1
    print("TIMEOUT CHECK PASSED: all checks green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
