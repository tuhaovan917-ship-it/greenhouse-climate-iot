"""Regression tests for the `reason` field of a command result.

Reported by Member 1: after a command was rejected with NO_WATER and a later
command was applied successfully, `GET /api/state` still showed
`reason: "NO_WATER"`.

The rule (contract v0.2.6):
- the reason belongs to one command only,
- a new commandId supersedes the previous explanation and clears it,
- the same commandId is a periodic republish and keeps the known reason.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TEMP_DB = Path(tempfile.gettempdir()) / "greenhouse_reason.db"
for suffix in ("", "-wal", "-shm"):
    candidate = Path(str(TEMP_DB) + suffix)
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEMP_DB.as_posix()}"
os.environ["MQTT_ENABLED"] = "0"
os.environ["DEVICE_ID"] = "greenhouse-01"
os.environ.pop("API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.database import createTablesForTest, sessionScope  # noqa: E402
from app.main import app  # noqa: E402
from app.services import ingest  # noqa: E402
from app.services.commands import commandService  # noqa: E402

createTablesForTest()

DEVICE = "greenhouse-01"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as testClient:
        yield testClient


def _statePayload(commandId: str | None, result: str | None, reason: str | None = None) -> dict:
    """State message exactly like the ESP32 builds it (see firmware publishDeviceState)."""
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
    if reason is not None:
        payload["reason"] = reason
    return payload


def _commandRow(client: TestClient, commandId: str) -> dict:
    for row in client.get("/api/commands").json()["data"]:
        if row["commandId"] == commandId:
            return row
    return {}


def test_c36_new_command_clears_the_previous_reason(client: TestClient) -> None:
    """REJECTED/NO_WATER then a new APPLIED command -> reason becomes null."""
    import anyio

    with sessionScope() as session:
        first = commandService.createPending(session, DEVICE, "mist", True)
        firstId = first.command_id
        session.commit()

    # 1. The device refuses the pump because the tank is empty.
    anyio.run(
        lambda: ingest.handleState(
            DEVICE, _statePayload(firstId, "REJECTED", reason="NO_WATER")
        )
    )
    state = client.get("/api/state").json()
    assert state["lastCommandResult"] == "REJECTED"
    assert state["reason"] == "NO_WATER", state
    assert _commandRow(client, firstId)["reason"] == "NO_WATER"

    # 2. The tank recovers and a new command succeeds. The firmware omits the
    #    `reason` key for a successful command.
    with sessionScope() as session:
        second = commandService.createPending(session, DEVICE, "fan", True)
        secondId = second.command_id
        session.commit()

    anyio.run(lambda: ingest.handleState(DEVICE, _statePayload(secondId, "APPLIED")))

    state = client.get("/api/state").json()
    assert state["lastCommandResult"] == "APPLIED", state
    assert state["reason"] is None, f"ly do cu cua lenh truoc van con: {state['reason']!r}"
    assert state["lastCommandId"] == secondId

    row = _commandRow(client, secondId)
    assert row["status"] == "APPLIED"
    assert row["reason"] is None, f"ly do cu van con tren lenh moi: {row['reason']!r}"

    # The old command keeps its own reason - it is a different command.
    assert _commandRow(client, firstId)["reason"] == "NO_WATER"


def test_c36_periodic_republish_keeps_the_reason(client: TestClient) -> None:
    """The same commandId is republished without a reason -> keep the reason."""
    import anyio

    with sessionScope() as session:
        log = commandService.createPending(session, DEVICE, "mist", True)
        commandId = log.command_id
        session.commit()

    anyio.run(
        lambda: ingest.handleState(
            DEVICE, _statePayload(commandId, "REJECTED", reason="NO_WATER")
        )
    )
    assert client.get("/api/state").json()["reason"] == "NO_WATER"

    # The ESP32 republishes its state on a timer and omits the reason.
    anyio.run(lambda: ingest.handleState(DEVICE, _statePayload(commandId, "REJECTED")))
    state = client.get("/api/state").json()
    assert state["reason"] == "NO_WATER", "republish cung commandId phai giu ly do"
    assert _commandRow(client, commandId)["reason"] == "NO_WATER"


def test_c36_late_applied_reply_clears_the_timeout_reason(client: TestClient) -> None:
    """TIMEOUT then a late APPLIED reply -> the reason must not stay TIMEOUT."""
    import anyio

    with sessionScope() as session:
        log = commandService.createPending(session, DEVICE, "fan", True)
        commandId = log.command_id
        session.commit()

    # Simulate the timeout marker.
    from app.models import COMMAND_TIMEOUT, REASON_TIMEOUT

    with sessionScope() as session:
        row = commandService.get(session, commandId)
        row.status = COMMAND_TIMEOUT
        row.reason = REASON_TIMEOUT
        session.add(row)

    anyio.run(lambda: ingest.handleState(DEVICE, _statePayload(commandId, "APPLIED")))

    row = _commandRow(client, commandId)
    assert row["status"] == "APPLIED", row
    assert row["reason"] is None, f"ly do TIMEOUT con lai: {row['reason']!r}"
    state = client.get("/api/state").json()
    assert state["reason"] is None
