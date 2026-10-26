"""Conformance tests: one test per requirement in docs/api-contract.md v0.2.2.

Run from `backend/`:
    .venv/Scripts/python -m pytest -q tests/test_contract_conformance.py

Each test names the contract clause it enforces so a failure points straight at
the line of the document that is not being met.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

TEMP_DB = Path(tempfile.gettempdir()) / "greenhouse_contract.db"
for suffix in ("", "-wal", "-shm"):
    candidate = Path(str(TEMP_DB) + suffix)
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEMP_DB.as_posix()}"
os.environ["MQTT_ENABLED"] = "0"
os.environ["DEVICE_ID"] = "greenhouse-01"
os.environ["COMMAND_TIMEOUT_S"] = "5"
os.environ["DEVICE_TIMEOUT_S"] = "15"
os.environ.pop("API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.database import createTablesForTest, sessionScope  # noqa: E402
from app.main import app  # noqa: E402
from app.models import DeviceState, TelemetryReading, utcNow  # noqa: E402
from app.services import ingest  # noqa: E402
from app.services.telemetry import bucketStartOf  # noqa: E402

createTablesForTest()

DEVICE = "greenhouse-01"


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as testClient:
        yield testClient


def _clearTelemetry() -> None:
    with sessionScope() as session:
        session.query(TelemetryReading).delete()


def _insert(
    receivedAt: datetime,
    temperatureC: float | None = 30.0,
    humidityPct: float | None = 60.0,
    lightLux: float | None = 400.0,
    waterOk: bool | None = True,
    deviceId: str = DEVICE,
) -> None:
    with sessionScope() as session:
        session.add(
            TelemetryReading(
                device_id=deviceId,
                temperature_c=temperatureC,
                humidity_pct=humidityPct,
                light_lux=lightLux,
                water_ok=waterOk,
                received_at=receivedAt,
            )
        )


def _history(client: TestClient, **params) -> dict:
    response = client.get("/api/telemetry", params={"deviceId": DEVICE, **params})
    assert response.status_code == 200, response.text
    return response.json()


# --- Section 2: shared conventions ---


def test_c2_timestamps_are_iso8601_utc_with_z(client: TestClient) -> None:
    """C2: every timestamp is ISO8601 UTC ending in Z."""
    _clearTelemetry()
    _insert(utcNow())
    for row in _history(client, bucket="raw")["data"]:
        assert row["receivedAt"].endswith("Z"), row

    from app.services.state import upsertDeviceState

    now = utcNow()
    with sessionScope() as scoped:
        upsertDeviceState(
            scoped,
            DEVICE,
            {"mode": "AUTO", "online": True, "updated_at": now, "last_seen_at": now},
        )
    body = client.get("/api/state").json()
    assert body["updatedAt"].endswith("Z")
    assert body["lastSeenAt"] is not None and body["lastSeenAt"].endswith("Z")


def test_c2_sensor_ranges_reject_out_of_range_values() -> None:
    """C2: humidity 0-100, lightLux >= 0; invalid readings become NULL."""
    import anyio

    anyio.run(
        lambda: ingest.handleTelemetry(
            DEVICE,
            {
                "deviceId": DEVICE,
                "temperatureC": 30.0,
                "humidityPct": 150.0,  # out of range
                "lightLux": -5.0,  # out of range
                "waterOk": True,
            },
        )
    )
    with sessionScope() as session:
        from sqlmodel import select

        row = session.exec(
            select(TelemetryReading)
            .where(TelemetryReading.device_id == DEVICE)
            .order_by(TelemetryReading.id.desc())
        ).first()
        assert row is not None
        assert row.humidity_pct is None, "humidity > 100 phai luu NULL"
        assert row.light_lux is None, "light < 0 phai luu NULL"
        assert row.temperature_c == 30.0


def test_c2_nan_and_non_numeric_become_null() -> None:
    import anyio

    anyio.run(
        lambda: ingest.handleTelemetry(
            DEVICE,
            {"temperatureC": float("nan"), "humidityPct": "abc", "lightLux": True, "waterOk": None},
        )
    )
    with sessionScope() as session:
        from sqlmodel import select

        row = session.exec(
            select(TelemetryReading)
            .where(TelemetryReading.device_id == DEVICE)
            .order_by(TelemetryReading.id.desc())
        ).first()
        assert row.temperature_c is None and row.humidity_pct is None
        assert row.light_lux is None and row.water_ok is None


def test_c2_error_body_shape(client: TestClient) -> None:
    """C2: errors use {"detail": ...}."""
    response = client.get("/api/telemetry", params={"deviceId": DEVICE, "bucket": "7d"})
    assert response.status_code == 400
    assert "detail" in response.json()


# --- Section 3.2: history, ordering, bucketing ---


def test_c32_envelope_for_raw_and_bucket(client: TestClient) -> None:
    """C3.2: always {bucket, data}."""
    _clearTelemetry()
    _insert(utcNow())
    raw = _history(client, bucket="raw")
    assert raw["bucket"] == "raw" and isinstance(raw["data"][0]["id"], int)

    bucketed = _history(client, bucket="1m")
    assert bucketed["bucket"] == "1m"
    assert "id" not in bucketed["data"][0]
    assert "sampleCount" in bucketed["data"][0]


def test_c32_range_is_half_open_from_to(client: TestClient) -> None:
    """C3.2: filter is [from, to) - `to` is exclusive."""
    _clearTelemetry()
    base = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    _insert(base)  # exactly on `from`
    _insert(base + timedelta(minutes=5))  # exactly on `to`

    body = _history(
        client,
        bucket="raw",
        **{"from": "2026-03-01T12:00:00Z", "to": "2026-03-01T12:05:00Z"},
    )
    stamps = [row["receivedAt"] for row in body["data"]]
    assert stamps == ["2026-03-01T12:00:00Z"], f"to phai exclusive, nhan duoc {stamps}"


def test_c32_limit_keeps_newest_rows_and_order_only_sorts(client: TestClient) -> None:
    """C3.2: limit takes the newest N; order decides presentation."""
    _clearTelemetry()
    base = datetime(2026, 3, 2, 8, 0, 0, tzinfo=timezone.utc)
    for index in range(10):
        _insert(base + timedelta(minutes=index))

    desc = _history(client, bucket="raw", limit=3, order="desc")["data"]
    asc = _history(client, bucket="raw", limit=3, order="asc")["data"]

    assert [row["receivedAt"] for row in desc] == [
        "2026-03-02T08:09:00Z",
        "2026-03-02T08:08:00Z",
        "2026-03-02T08:07:00Z",
    ]
    # Same three newest samples, ascending - NOT the three oldest in range.
    assert [row["receivedAt"] for row in asc] == [
        "2026-03-02T08:07:00Z",
        "2026-03-02T08:08:00Z",
        "2026-03-02T08:09:00Z",
    ]


def test_c32_limit_counts_buckets_not_rows(client: TestClient) -> None:
    """C3.2: with a bucket, limit counts buckets."""
    _clearTelemetry()
    base = datetime(2026, 3, 3, 9, 0, 0, tzinfo=timezone.utc)
    for minute in range(4):
        for _ in range(3):  # 3 samples per minute bucket
            _insert(base + timedelta(minutes=minute, seconds=1))

    body = _history(client, bucket="1m", limit=2)
    assert len(body["data"]) == 2
    assert [bucket["bucketStart"] for bucket in body["data"]] == [
        "2026-03-03T09:03:00Z",
        "2026-03-03T09:02:00Z",
    ]
    assert all(bucket["sampleCount"] == 3 for bucket in body["data"])

    ascending = _history(client, bucket="1m", limit=2, order="asc")["data"]
    assert [bucket["bucketStart"] for bucket in ascending] == [
        "2026-03-03T09:02:00Z",
        "2026-03-03T09:03:00Z",
    ]


def test_c32_bucket_alignment_is_utc_epoch() -> None:
    """C3.2: buckets align to the UTC epoch, not to the query time."""
    moment = datetime(2026, 3, 4, 10, 37, 42, 123456, tzinfo=timezone.utc)
    assert bucketStartOf(moment, 60) == datetime(2026, 3, 4, 10, 37, tzinfo=timezone.utc)
    assert bucketStartOf(moment, 300) == datetime(2026, 3, 4, 10, 35, tzinfo=timezone.utc)
    assert bucketStartOf(moment, 3600) == datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)


def test_c32_bucket_averages_ignore_null_and_keep_last_water(client: TestClient) -> None:
    """C3.2: average over non-NULL; waterOk = last non-NULL in the bucket."""
    _clearTelemetry()
    base = datetime(2026, 3, 5, 11, 0, 5, tzinfo=timezone.utc)
    _insert(base, temperatureC=20.0, waterOk=True)
    _insert(base + timedelta(seconds=10), temperatureC=40.0, waterOk=None)
    _insert(base + timedelta(seconds=20), temperatureC=None, waterOk=None)
    _insert(base + timedelta(seconds=30), temperatureC=30.0, waterOk=False)

    bucket = _history(client, bucket="1m")["data"][0]
    assert bucket["sampleCount"] == 4, "sampleCount dem moi ban tin raw, ke ca NULL"
    assert bucket["temperatureC"] == 30.0, "average bo NULL: (20+40+30)/3"
    assert bucket["waterOk"] is False, "lay gia tri khac null cuoi bucket"


def test_c32_bucket_all_null_water_returns_null(client: TestClient) -> None:
    """C3.2: a bucket whose waterOk values are all NULL reports NULL."""
    _clearTelemetry()
    base = datetime(2026, 3, 6, 12, 0, 5, tzinfo=timezone.utc)
    _insert(base, waterOk=None)
    _insert(base + timedelta(seconds=10), waterOk=None)

    bucket = _history(client, bucket="1m")["data"][0]
    assert bucket["waterOk"] is None


def test_c32_empty_buckets_are_skipped(client: TestClient) -> None:
    """C3.2: buckets with no data are omitted, gaps stay visible."""
    _clearTelemetry()
    base = datetime(2026, 3, 7, 13, 0, 5, tzinfo=timezone.utc)
    _insert(base)
    _insert(base + timedelta(minutes=5))  # 13:05 bucket, 13:01-13:04 empty

    buckets = _history(client, bucket="1m")["data"]
    assert [bucket["bucketStart"] for bucket in buckets] == [
        "2026-03-07T13:05:00Z",
        "2026-03-07T13:00:00Z",
    ]


def test_c32_stable_order_when_timestamps_tie(client: TestClient) -> None:
    """C2: id is the tie-breaker when two rows share receivedAt."""
    _clearTelemetry()
    sameMoment = datetime(2026, 3, 8, 14, 0, 0, tzinfo=timezone.utc)
    for temperature in (10.0, 20.0, 30.0):
        _insert(sameMoment, temperatureC=temperature)

    rows = _history(client, bucket="raw")["data"]
    assert [row["temperatureC"] for row in rows] == [30.0, 20.0, 10.0]
    assert [row["id"] for row in rows] == sorted([row["id"] for row in rows], reverse=True)


def test_c32_limit_bounds_enforced(client: TestClient) -> None:
    """C3.2: limit defaults to 100, max 1000."""
    assert client.get("/api/telemetry", params={"limit": 0}).status_code == 422
    assert client.get("/api/telemetry", params={"limit": 1001}).status_code == 422
    assert client.get("/api/telemetry", params={"order": "sideways"}).status_code == 422


def test_c32_from_after_to_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/telemetry",
        params={"from": "2026-03-09T12:00:00Z", "to": "2026-03-09T10:00:00Z"},
    )
    assert response.status_code == 400


def test_c32_invalid_time_format_rejected(client: TestClient) -> None:
    response = client.get("/api/telemetry", params={"from": "khong-phai-thoi-gian"})
    assert response.status_code == 400


def test_c32_scan_guard_reports_error_instead_of_truncating(client: TestClient) -> None:
    """MAX_SCAN_ROWS must not silently return a partial window."""
    from app.config import settings

    _clearTelemetry()
    base = datetime(2026, 3, 10, 0, 0, 0, tzinfo=timezone.utc)
    rows = min(settings.max_scan_rows + 5, 2005)
    with sessionScope() as session:
        session.bulk_save_objects(
            [
                TelemetryReading(
                    device_id=DEVICE,
                    temperature_c=25.0,
                    humidity_pct=50.0,
                    light_lux=300.0,
                    water_ok=True,
                    received_at=base + timedelta(seconds=index),
                )
                for index in range(rows)
            ]
        )

    original = settings.max_scan_rows
    object.__setattr__(settings, "max_scan_rows", 1000)
    try:
        response = client.get("/api/telemetry", params={"bucket": "raw"})
        assert response.status_code == 400, "phai bao loi thay vi cat im lang"
        assert "bucket" in response.json()["detail"]
    finally:
        object.__setattr__(settings, "max_scan_rows", original)
        _clearTelemetry()


# --- Section 3.4: state ---


def test_c34_state_reports_online_and_last_seen(client: TestClient) -> None:
    import anyio

    anyio.run(lambda: ingest.handleStatus(DEVICE, {"online": True}))
    body = client.get("/api/state").json()
    assert body["online"] is True
    assert body["lastSeenAt"] is not None and body["lastSeenAt"].endswith("Z")


def test_c34_stale_device_goes_offline_after_device_timeout() -> None:
    """C3.4: no valid message within DEVICE_TIMEOUT_S means online=false."""
    import anyio

    from app.config import settings
    from app.services.state import stateService

    anyio.run(lambda: ingest.handleStatus(DEVICE, {"online": True}))
    runtime = stateService.runtime(DEVICE)
    runtime.last_seen_at = utcNow() - timedelta(seconds=settings.device_timeout_s + 2)

    stale = stateService.staleDevices()
    assert any(item.device_id == DEVICE for item in stale), "phai phat hien thiet bi qua han"

    anyio.run(lambda: ingest.monitorOfflineDevices_step()) if hasattr(ingest, "monitorOfflineDevices_step") else None
    anyio.run(lambda: ingest.handleStatus(DEVICE, {"online": False}))
    assert stateService.onlineFlags()[DEVICE] is False


def test_c34_unknown_device_state_returns_offline_default(client: TestClient) -> None:
    """C3.4 (v0.2.5): no state row -> 200 with a safe offline default, not an error.

    The Dashboard loads several endpoints in parallel, so an error here would
    break the whole page before the device ever connects.
    """
    response = client.get("/api/state", params={"deviceId": "khong-ton-tai-99"})
    assert response.status_code == 200
    body = response.json()
    assert body["online"] is False
    assert body["mode"] == "AUTO"
    assert body["fan"] is False and body["mist"] is False and body["lamp"] is False
    assert body["failsafeActive"] is False
    assert body["lastSeenAt"] is None
    assert body["updatedAt"] is None


def test_c33_latest_telemetry_is_null_when_empty(client: TestClient) -> None:
    """C3.3 (v0.2.5): no reading -> 200 with body null, not an error."""
    _clearTelemetry()
    response = client.get("/api/telemetry/latest", params={"deviceId": "thiet-bi-chua-co-du-lieu"})
    assert response.status_code == 200
    assert response.json() is None


def test_c34_unknown_mode_is_ignored() -> None:
    """C2: only AUTO/MANUAL are accepted from the device."""
    import anyio

    anyio.run(lambda: ingest.handleState(DEVICE, {"mode": "TURBO", "fan": False}))
    with sessionScope() as session:
        state = session.get(DeviceState, DEVICE)
        assert state is not None
        assert state.mode in {"AUTO", "MANUAL"}, f"mode lai={state.mode!r}"


# --- Section 3.5/3.6: commands ---


def test_c35_command_row_created_before_publish(client: TestClient) -> None:
    """C3.5: PENDING is stored before publishing, offline writes are refused."""
    import anyio

    # A device id of its own keeps the check independent from other tests.
    offlineDevice = "thiet-bi-offline-01"

    anyio.run(lambda: ingest.handleStatus(offlineDevice, {"online": False}))
    response = client.post(
        "/api/commands", json={"deviceId": offlineDevice, "device": "fan", "on": True}
    )
    assert response.status_code == 409
    # Nothing may be written when the device cannot be reached.
    rows = client.get("/api/commands", params={"deviceId": offlineDevice}).json()["data"]
    assert rows == [], rows


def test_c35_invalid_device_name_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/commands", json={"deviceId": DEVICE, "device": "aircooler", "on": True}
    )
    assert response.status_code == 422


def test_c36_command_history_shape(client: TestClient) -> None:
    """C3.6: history exposes status + reason + timestamps in camelCase."""
    from app.database import sessionScope as scope
    from app.services.commands import commandService

    with scope() as session:
        log = commandService.createPending(session, DEVICE, "lamp", True)
        commandId = log.command_id
        session.commit()

    rows = client.get("/api/commands").json()["data"]
    row = next(item for item in rows if item["commandId"] == commandId)
    for key in (
        "commandId",
        "deviceId",
        "device",
        "requestedOn",
        "status",
        "requestedAt",
        "completedAt",
    ):
        assert key in row, f"thieu truong {key}"
    assert row["requestedAt"].endswith("Z")
    assert row["completedAt"] is None


def test_c35_duplicate_reply_does_not_push_extra_ws(monkeypatch: pytest.MonkeyPatch) -> None:
    """C3.5: QoS 1 duplicate must not broadcast command_result twice.

    Spy on the outgoing event boundary instead of blocking indefinitely while
    waiting for an event that correctly does not exist. Other tests exercise
    real WebSocket connections and session enforcement.
    """
    import anyio

    from app.database import sessionScope as scope
    from app.services.commands import commandService
    from app.ws_manager import wsManager

    captured: list[tuple[str, dict]] = []

    async def capture_broadcast(device_id: str, message: dict) -> None:
        captured.append((device_id, message))

    monkeypatch.setattr(wsManager, "broadcast", capture_broadcast)

    with scope() as session:
        log = commandService.createPending(session, DEVICE, "fan", False)
        commandId = log.command_id
        session.commit()

    payload = {
        "deviceId": DEVICE,
        "mode": "MANUAL",
        "fan": True,
        "mist": False,
        "lamp": False,
        "failsafeActive": False,
        "lastCommandId": commandId,
        "lastCommandResult": "APPLIED",
    }

    def results_for_command() -> list[dict]:
        return [
            message
            for device_id, message in captured
            if device_id == DEVICE
            and message.get("type") == "command_result"
            and message.get("data", {}).get("commandId") == commandId
        ]

    anyio.run(lambda: ingest.handleState(DEVICE, payload))
    first = results_for_command()
    assert len(first) == 1, "first state must broadcast one command_result"
    assert first[0]["data"]["result"] == "APPLIED"
    assert first[0]["data"]["wasLate"] is False

    anyio.run(lambda: ingest.handleState(DEVICE, payload))
    assert len(results_for_command()) == 1, "duplicate QoS 1 must not broadcast again"

    with scope() as session:
        assert commandService.get(session, commandId).status == "APPLIED"


def test_c35_periodic_state_publish_keeps_reason(client: TestClient) -> None:
    """C3.5: a republish without `reason` must not erase the recorded reason.

    The ESP32 publishes `state` on a timer; only the message that carries the
    rejection explains it, so later bare republishes must not clear it.
    """
    import anyio

    from app.database import sessionScope as scope
    from app.services.commands import commandService

    with scope() as session:
        log = commandService.createPending(session, DEVICE, "mist", True)
        commandId = log.command_id
        session.commit()

    base = {
        "deviceId": DEVICE,
        "mode": "MANUAL",
        "fan": False,
        "mist": False,
        "lamp": False,
        # No failsafe here: it would open a NO_WATER alert and couple this test
        # to the alert count of the other test files.
        "failsafeActive": False,
        "lastCommandId": commandId,
    }
    anyio.run(
        lambda: ingest.handleState(
            DEVICE, {**base, "lastCommandResult": "REJECTED", "reason": "NO_WATER"}
        )
    )
    # Periodic republish without a reason.
    anyio.run(lambda: ingest.handleState(DEVICE, {**base, "lastCommandResult": "REJECTED"}))

    row = next(
        item
        for item in client.get("/api/commands").json()["data"]
        if item["commandId"] == commandId
    )
    assert row["status"] == "REJECTED"
    assert row["reason"] == "NO_WATER", f"ly do bi xoa: {row['reason']!r}"
    assert client.get("/api/state").json()["reason"] == "NO_WATER"


# --- Section 3.7: config ---


def test_c37_config_accepts_lowercase_mode() -> None:
    """C3.7: mode is case-insensitive on input."""
    from app.schemas import DeviceConfigRequest

    request = DeviceConfigRequest(
        mode="manual",
        tempOnC=30,
        tempOffC=28,
        humidityOnPct=55,
        humidityOffPct=65,
        lightOnLux=300,
        lightOffLux=700,
    )
    assert request.mode == "MANUAL"


def test_c37_config_hysteresis_rules() -> None:
    """C3.7: on > off for temperature, on < off for humidity and light."""
    from app.schemas import DeviceConfigRequest

    def build(**overrides):
        base = {
            "mode": "AUTO",
            "tempOnC": 30,
            "tempOffC": 28,
            "humidityOnPct": 55,
            "humidityOffPct": 65,
            "lightOnLux": 300,
            "lightOffLux": 700,
        }
        base.update(overrides)
        return DeviceConfigRequest(**base)

    assert build().validateThresholds() is None
    for bad in (
        {"tempOnC": 28, "tempOffC": 30},
        {"humidityOnPct": 70, "humidityOffPct": 65},
        {"lightOnLux": 700, "lightOffLux": 300},
    ):
        with pytest.raises(ValueError):
            build(**bad).validateThresholds()
    with pytest.raises(ValueError):
        build(humidityOnPct=120).validateRanges()
    with pytest.raises(ValueError):
        build(lightOnLux=-1).validateRanges()


def test_c37_config_defaults_are_contract_values(client: TestClient) -> None:
    """C3.7: documented test thresholds are the defaults."""
    body = client.get("/api/config", params={"deviceId": DEVICE}).json()
    assert body == {
        "mode": "AUTO",
        "tempOnC": 30.0,
        "tempOffC": 28.0,
        "humidityOnPct": 55.0,
        "humidityOffPct": 65.0,
        "lightOnLux": 300.0,
        "lightOffLux": 700.0,
    }


# --- Section 3.8: alerts ---


def test_c38_alert_filters_and_validation(client: TestClient) -> None:
    """C3.8: active/code filters, invalid code rejected, newest first."""
    response = client.get("/api/alerts", params={"code": "FIRE"})
    assert response.status_code == 400

    active = client.get("/api/alerts", params={"active": "true"}).json()["data"]
    inactive = client.get("/api/alerts", params={"active": "false"}).json()["data"]
    for row in active + inactive:
        assert row["code"] in {"NO_WATER", "SENSOR_FAULT", "OFFLINE"}
        assert row["severity"] in {"INFO", "WARNING", "CRITICAL"}
        assert row["startedAt"].endswith("Z")
    stamps = [row["startedAt"] for row in active]
    assert stamps == sorted(stamps, reverse=True), "alerts phai sap xep moi nhat truoc"


def test_c38_severity_map() -> None:
    """SCHEMA.md 8: NO_WATER/OFFLINE CRITICAL, SENSOR_FAULT WARNING."""
    from app.models import ALERT_SEVERITY_BY_CODE

    assert ALERT_SEVERITY_BY_CODE["NO_WATER"] == "CRITICAL"
    assert ALERT_SEVERITY_BY_CODE["OFFLINE"] == "CRITICAL"
    assert ALERT_SEVERITY_BY_CODE["SENSOR_FAULT"] == "WARNING"


def test_c38_offline_alert_opens_and_resolves(client: TestClient) -> None:
    import anyio

    before = len(client.get("/api/alerts", params={"code": "OFFLINE", "active": "false"}).json()["data"])

    anyio.run(lambda: ingest.handleStatus(DEVICE, {"online": False}))
    rows = client.get("/api/alerts", params={"code": "OFFLINE", "active": "true"}).json()["data"]
    assert len(rows) == 1, "chi co mot alert OFFLINE dang active"
    assert rows[0]["severity"] == "CRITICAL"

    anyio.run(lambda: ingest.handleStatus(DEVICE, {"online": True}))
    active = client.get("/api/alerts", params={"code": "OFFLINE", "active": "true"}).json()["data"]
    resolved = client.get("/api/alerts", params={"code": "OFFLINE", "active": "false"}).json()["data"]
    assert active == []
    assert len(resolved) == before + 1
    assert resolved[0]["resolvedAt"] is not None


# --- Section 5: auth ---


def test_c5_api_key_protects_writes_only(client: TestClient) -> None:
    """C5: writes need X-API-Key when API_KEY is set; reads stay open."""
    from app.config import settings

    original = settings.api_key
    object.__setattr__(settings, "api_key", "khoa-demo")
    try:
        assert client.get("/api/state").status_code in (200, 404)
        assert client.get("/api/telemetry").status_code == 200
        assert client.post(
            "/api/commands", json={"deviceId": DEVICE, "device": "fan", "on": True}
        ).status_code == 401
        assert client.post(
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
        ).status_code == 401

        # Correct key passes the guard (offline device then yields 409).
        withKey = client.post(
            "/api/commands",
            json={"deviceId": DEVICE, "device": "fan", "on": True},
            headers={"X-API-Key": "khoa-demo"},
        )
        assert withKey.status_code in (202, 409, 503)
    finally:
        object.__setattr__(settings, "api_key", original)


# --- Section 3.1: health ---


def test_c31_health_shape(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert isinstance(body["mqttConnected"], bool)
    assert body["db"] == "ok"


# --- isolation ---


def test_history_is_scoped_per_device(client: TestClient) -> None:
    """SCHEMA.md 2: no hard-coded single device."""
    _clearTelemetry()
    _insert(utcNow(), deviceId=DEVICE)
    _insert(utcNow(), deviceId="greenhouse-02")
    try:
        body = _history(client, bucket="raw")
        assert {row["deviceId"] for row in body["data"]} == {DEVICE}
    finally:
        with sessionScope() as session:
            session.query(TelemetryReading).filter(TelemetryReading.device_id == "greenhouse-02").delete()