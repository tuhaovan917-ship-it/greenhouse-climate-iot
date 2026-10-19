"""Smoke tests for the Backend against docs/api-contract.md v0.2.2.

Run from `backend/`:
    .venv/Scripts/python -m pytest -q

These tests use a throwaway SQLite file and MQTT disabled, then feed the ingest
services directly to simulate ESP32 traffic.
"""

from __future__ import annotations

import os
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest

TEMP_DB = Path(tempfile.gettempdir()) / "greenhouse_test.db"
for suffix in ("", "-wal", "-shm"):
    candidate = Path(str(TEMP_DB) + suffix)
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEMP_DB.as_posix()}"
os.environ["MQTT_ENABLED"] = "0"
os.environ["DEVICE_ID"] = "greenhouse-01"
os.environ.pop("API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.database import createTablesForTest  # noqa: E402
from app.main import app  # noqa: E402
from app.models import COMMAND_REJECTED, utcNow  # noqa: E402
from app.services import ingest  # noqa: E402
from app.services.state import stateService  # noqa: E402

createTablesForTest()


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as testClient:
        yield testClient


def _online() -> None:
    stateService.markOnline("greenhouse-01", True)


# --- health & basics ---


def testHealth(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


def testStateForUnknownDevice(client: TestClient) -> None:
    """Contract 3.4: a device with no state row answers 200 with an offline default."""
    response = client.get("/api/state", params={"deviceId": "thiet-bi-khong-ton-tai"})
    assert response.status_code == 200
    assert response.json()["online"] is False


# --- telemetry ingestion + history ---


@pytest.mark.asyncio
async def testTelemetryAndBucketEnvelope() -> None:
    _online()
    now = utcNow()
    for index in range(6):
        await ingest.handleTelemetry(
            "greenhouse-01",
            {
                "deviceId": "greenhouse-01",
                "temperatureC": 30.0 + index,
                "humidityPct": 60.0,
                "lightLux": 400,
                "waterOk": True,
            },
        )

    raw = TestClient(app).get("/api/telemetry", params={"bucket": "raw", "limit": 3})
    rawBody = raw.json()
    assert rawBody["bucket"] == "raw"
    assert len(rawBody["data"]) == 3
    assert rawBody["data"][0]["receivedAt"].endswith("Z")
    assert rawBody["data"][0]["waterOk"] is True

    bucketed = TestClient(app).get("/api/telemetry", params={"bucket": "1m", "limit": 10}).json()
    assert bucketed["bucket"] == "1m"
    assert len(bucketed["data"]) == 1
    bucket = bucketed["data"][0]
    assert bucket["sampleCount"] >= 1
    assert bucket["bucketStart"].endswith("Z")
    assert "id" not in bucket
    assert 30.0 <= bucket["temperatureC"] <= 35.0
    assert bucket["waterOk"] is True
    assert now is not None


@pytest.mark.asyncio
async def testTelemetryRejectsGarbageValues() -> None:
    await ingest.handleTelemetry(
        "greenhouse-01",
        {
            "temperatureC": float("nan"),
            "humidityPct": "abc",
            "lightLux": None,
            "waterOk": "yes",
        },
    )
    latest = TestClient(app).get("/api/telemetry/latest").json()
    assert latest["temperatureC"] is None
    assert latest["humidityPct"] is None
    assert latest["waterOk"] is None


# --- state, command result, alerts ---


@pytest.mark.asyncio
async def testStateUpsertAndCommandRejected() -> None:
    await ingest.handleState(
        "greenhouse-01",
        {
            "deviceId": "greenhouse-01",
            "mode": "MANUAL",
            "fan": True,
            "mist": False,
            "lamp": False,
            "failsafeActive": False,
            "lastCommandId": "cmd-test01",
            "lastCommandResult": COMMAND_REJECTED,
            "reason": "NO_WATER",
        },
    )
    body = TestClient(app).get("/api/state").json()
    assert body["mode"] == "MANUAL"
    assert body["fan"] is True
    assert body["online"] is True
    assert body["lastCommandResult"] == "REJECTED"
    assert body["lastCommandId"] == "cmd-test01"
    assert body["lastSeenAt"].endswith("Z")


@pytest.mark.asyncio
async def testNoWaterAlertOpensAndDeduplicates() -> None:
    for _ in range(4):
        await ingest.handleTelemetry(
            "greenhouse-01",
            {"temperatureC": 30.0, "humidityPct": 55.0, "lightLux": 400, "waterOk": False},
        )
    alerts = TestClient(app).get("/api/alerts", params={"code": "NO_WATER", "active": "true"}).json()
    assert len(alerts["data"]) == 1, "dedup phai gom nhieu chu ky telemetry vao mot alert"
    alert = alerts["data"][0]
    assert alert["severity"] == "CRITICAL"

    await ingest.handleTelemetry(
        "greenhouse-01",
        {"temperatureC": 30.0, "humidityPct": 55.0, "lightLux": 400, "waterOk": True},
    )
    resolved = TestClient(app).get("/api/alerts", params={"code": "NO_WATER", "active": "false"}).json()
    assert len(resolved["data"]) == 1
    assert resolved["data"][0]["resolvedAt"] is not None


@pytest.mark.asyncio
async def testStatusOffline() -> None:
    await ingest.handleStatus("greenhouse-01", {"online": False})
    body = TestClient(app).get("/api/state").json()
    assert body["online"] is False

    offlineAlerts = TestClient(app).get("/api/alerts", params={"code": "OFFLINE", "active": "true"}).json()
    assert len(offlineAlerts["data"]) == 1

    await ingest.handleStatus("greenhouse-01", {"online": True})
    assert TestClient(app).get("/api/state").json()["online"] is True


# --- write endpoints ---


@pytest.mark.asyncio
async def testCommandRejectedWhenOffline() -> None:
    await ingest.handleStatus("greenhouse-01", {"online": False})
    response = TestClient(app).post(
        "/api/commands", json={"deviceId": "greenhouse-01", "device": "fan", "on": True}
    )
    assert response.status_code == 409


def testConfigValidation() -> None:
    bad = TestClient(app).post(
        "/api/config",
        json={
            "mode": "AUTO",
            "tempOnC": 20,
            "tempOffC": 30,
            "humidityOnPct": 55,
            "humidityOffPct": 65,
            "lightOnLux": 300,
            "lightOffLux": 700,
        },
    )
    assert bad.status_code == 400

    offline = TestClient(app).post(
        "/api/config",
        json={
            "mode": "AUTO",
            "tempOnC": 30,
            "tempOffC": 28,
            "humidityOnPct": 55,
            "humidityOffPct": 65,
            "lightOnLux": 300,
            "lightOffLux": 700,
        },
    )
    assert offline.status_code == 409


def testApiKeyGuardBlocksWrites() -> None:
    from app.config import settings

    original = settings.api_key
    object.__setattr__(settings, "api_key", "demo-secret")
    try:
        response = TestClient(app).post(
            "/api/commands", json={"deviceId": "greenhouse-01", "device": "fan", "on": True}
        )
        assert response.status_code == 401
    finally:
        object.__setattr__(settings, "api_key", original)


def testOfflineMonitorMarksStaleDeviceOffline() -> None:
    import asyncio

    from app.config import settings

    stateService.markOnline("greenhouse-02", True)
    stateService.runtime("greenhouse-02").last_seen_at = utcNow() - timedelta(
        seconds=settings.device_timeout_s + 5
    )
    stale = stateService.staleDevices()
    assert any(item.device_id == "greenhouse-02" for item in stale)
    assert asyncio.get_event_loop_policy() is not None
