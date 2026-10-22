"""Tests for the behaviours tv3 asked to confirm before locking the Alembic metadata.

Covers docs/api-contract.md v0.2.4:
- TIMEOUT is pushed to the Dashboard over the WebSocket (not only stored).
- The WebSocket survives a silent Dashboard (server-side heartbeat).
- The SQLModel metadata carries the CheckConstraints from SCHEMA.md section 3,
  so `alembic revision --autogenerate` produces a migration with them.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TEMP_DB = Path(tempfile.gettempdir()) / "greenhouse_review.db"
for suffix in ("", "-wal", "-shm"):
    candidate = Path(str(TEMP_DB) + suffix)
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEMP_DB.as_posix()}"
os.environ["MQTT_ENABLED"] = "0"
os.environ["DEVICE_ID"] = "greenhouse-01"
os.environ["COMMAND_TIMEOUT_S"] = "1"
os.environ.pop("API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.database import createTablesForTest, sessionScope  # noqa: E402
from app.main import app  # noqa: E402
from app.models import TelemetryReading  # noqa: E402
from app.services.commands import commandService  # noqa: E402

createTablesForTest()

DEVICE = "greenhouse-01"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as testClient:
        yield testClient


def _receiveOfType(socket, wanted: str, maxReads: int = 8) -> dict | None:  # noqa: ANN001
    for _ in range(maxReads):
        message = socket.receive_json()
        if message.get("type") == wanted:
            return message
    return None


# --- 1. TIMEOUT is pushed on the WebSocket ---


def test_timeout_is_pushed_to_dashboard(client: TestClient) -> None:
    """Contract 3.5: TIMEOUT must reach the Dashboard, not only the database."""
    with sessionScope() as session:
        log = commandService.createPending(session, DEVICE, "fan", True)
        commandId = log.command_id
        session.commit()

    with client.websocket_connect(f"/ws?deviceId={DEVICE}") as socket:
        # scheduleTimeout uses the loop bound at startup, so the push happens
        # on the same loop the WebSocket lives on.
        commandService.scheduleTimeout(commandId)

        message = _receiveOfType(socket, "command_result")
        assert message is not None, "TIMEOUT phai duoc push qua WebSocket"
        assert message["data"]["result"] == "TIMEOUT"
        assert message["data"]["reason"] == "TIMEOUT"
        assert message["data"]["commandId"] == commandId

    rows = client.get("/api/commands").json()["data"]
    row = next(item for item in rows if item["commandId"] == commandId)
    assert row["status"] == "TIMEOUT"


# --- 2. The socket survives a silent Dashboard ---


def test_websocket_survives_silent_dashboard(client: TestClient) -> None:
    """Contract 4: the socket must not close just because the client is quiet.

    The old implementation closed the connection after 20s of silence, which
    would have killed the realtime stream of a Dashboard that only listens.
    """
    import app.routers.ws as wsRouter

    original = wsRouter.HEARTBEAT_S
    wsRouter.HEARTBEAT_S = 0.2
    try:
        with client.websocket_connect(f"/ws?deviceId={DEVICE}") as socket:
            # Stay silent for longer than the heartbeat interval.
            import time

            time.sleep(1.0)
            # The server ping arrives as an application message.
            message = socket.receive_json()
            assert message == {"type": "ping"}, message
    finally:
        wsRouter.HEARTBEAT_S = original


def test_websocket_still_receives_data_after_being_silent(client: TestClient) -> None:
    """A quiet Dashboard keeps getting telemetry pushes."""
    import anyio

    from app.services import ingest

    with client.websocket_connect(f"/ws?deviceId={DEVICE}") as socket:
        anyio.run(
            lambda: ingest.handleTelemetry(
                DEVICE,
                {"temperatureC": 30.0, "humidityPct": 60.0, "lightLux": 400, "waterOk": True},
            )
        )
        message = _receiveOfType(socket, "telemetry")
        assert message is not None
        assert message["data"]["temperatureC"] == 30.0


# --- 3. CheckConstraints exist in the metadata ---


def test_models_declare_check_constraints() -> None:
    """SCHEMA.md 3: humidity 0-100 and light >= 0 must be real DB constraints."""
    from sqlalchemy import CheckConstraint

    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in TelemetryReading.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_telemetry_humidity_range" in constraints
    assert "ck_telemetry_light_non_negative" in constraints
    assert "humidity_pct" in constraints["ck_telemetry_humidity_range"]
    assert "light_lux" in constraints["ck_telemetry_light_non_negative"]


def test_check_constraint_is_enforced_by_the_database(client: TestClient) -> None:
    """The constraint must exist in the DDL, not only in the Python model."""
    from sqlalchemy import text

    with sessionScope() as session:
        rows = session.exec(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='telemetry_readings'")
        ).all()
        ddl = rows[0][0] if rows else ""
    assert "ck_telemetry_humidity_range" in ddl, ddl
    assert "ck_telemetry_light_non_negative" in ddl, ddl


def test_out_of_range_row_is_rejected_by_database() -> None:
    """Writing humidity=150 directly must fail; the ingest path stores NULL."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with sessionScope() as session:
            session.add(
                TelemetryReading(
                    device_id=DEVICE,
                    temperature_c=30.0,
                    humidity_pct=150.0,
                    light_lux=400.0,
                    water_ok=True,
                )
            )


# --- 4. PostgreSQL driver is declared ---


def test_requirements_include_postgres_driver() -> None:
    """The PostgreSQL path advertised in DATABASE_URL must be installable."""
    requirements = Path(__file__).resolve().parents[1] / "requirements.txt"
    content = requirements.read_text(encoding="utf-8")
    activeLines = [
        line for line in content.splitlines() if line.strip() and not line.strip().startswith("#")
    ]
    assert any(line.startswith("psycopg") for line in activeLines), activeLines
