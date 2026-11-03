import asyncio

import pytest

from app.services.config_ack import configAckService
from app.ws_manager import wsManager

from fastapi.testclient import TestClient

from app.database import createTablesForTest
from app.main import app
from app.mqtt_client import mqttService
from app.services.state import stateService

createTablesForTest()


def _captureConfigBroadcasts(monkeypatch):
    broadcasts: list[tuple[str, dict]] = []

    async def capture(deviceId: str, message: dict) -> None:
        broadcasts.append((deviceId, message))

    monkeypatch.setattr(wsManager, "broadcast", capture)
    return broadcasts


@pytest.mark.asyncio
async def test_config_ack_correlates_by_config_id(monkeypatch) -> None:
    configAckService.clear()
    broadcasts = _captureConfigBroadcasts(monkeypatch)
    configAckService.registerPending(
        "greenhouse-01",
        "cfg-a8-test-001",
    )

    await configAckService.handleAck(
        "greenhouse-01",
        {
            "deviceId": "greenhouse-01",
            "configId": "cfg-a8-test-001",
            "result": "APPLIED",
            "reason": None,
        },
    )

    ack = configAckService.get("cfg-a8-test-001")

    assert ack is not None
    assert ack.device_id == "greenhouse-01"
    assert ack.config_id == "cfg-a8-test-001"
    assert ack.result == "APPLIED"
    assert ack.reason is None
    assert ack.was_late is False
    assert broadcasts == [
        (
            "greenhouse-01",
            {
                "type": "config_result",
                "data": {
                    "configId": "cfg-a8-test-001",
                    "result": "APPLIED",
                    "reason": None,
                    "wasLate": False,
                },
            },
        )
    ]


@pytest.mark.asyncio
async def test_config_ack_rejected_broadcast_preserves_reason(monkeypatch) -> None:
    configAckService.clear()
    broadcasts = _captureConfigBroadcasts(monkeypatch)
    configId = "cfg-a8-rejected-001"
    configAckService.registerPending("greenhouse-01", configId)

    await configAckService.handleAck(
        "greenhouse-01",
        {
            "deviceId": "greenhouse-01",
            "configId": configId,
            "result": "REJECTED",
            "reason": "NVS_WRITE_FAILED",
        },
    )

    ack = configAckService.get(configId)
    assert ack is not None
    assert ack.device_id == "greenhouse-01"
    assert ack.result == "REJECTED"
    assert ack.reason == "NVS_WRITE_FAILED"
    assert broadcasts == [
        (
            "greenhouse-01",
            {
                "type": "config_result",
                "data": {
                    "configId": configId,
                    "result": "REJECTED",
                    "reason": "NVS_WRITE_FAILED",
                    "wasLate": False,
                },
            },
        )
    ]


@pytest.mark.asyncio
async def test_config_ack_rejects_invalid_result(monkeypatch) -> None:
    configAckService.clear()
    broadcasts = _captureConfigBroadcasts(monkeypatch)
    configAckService.registerPending(
        "greenhouse-01",
        "cfg-a8-test-invalid",
    )

    await configAckService.handleAck(
        "greenhouse-01",
        {
            "deviceId": "greenhouse-01",
            "configId": "cfg-a8-test-invalid",
            "result": "UNKNOWN",
        },
    )

    ack = configAckService.get("cfg-a8-test-invalid")

    assert ack is not None
    assert ack.result == "PENDING"
    assert broadcasts == []


@pytest.mark.asyncio
async def test_invalid_config_id_warning_does_not_log_payload_secrets(
    monkeypatch,
    caplog,
) -> None:
    configAckService.clear()
    broadcasts = _captureConfigBroadcasts(monkeypatch)

    await configAckService.handleAck(
        "greenhouse-01",
        {"configId": "", "result": "APPLIED", "apiKey": "do-not-log-this"},
    )

    assert "do-not-log-this" not in caplog.text
    assert broadcasts == []


@pytest.mark.asyncio
async def test_config_ack_wrong_device_is_ignored_without_cancelling_timeout(
    monkeypatch,
) -> None:
    configAckService.clear()
    configAckService.bindLoop(asyncio.get_running_loop())
    broadcasts = _captureConfigBroadcasts(monkeypatch)
    configId = "cfg-a8-device-001"
    configAckService.registerPending("greenhouse-01", configId)
    configAckService.scheduleTimeout(configId, timeoutSeconds=60)
    timeoutTask = configAckService._tasks[configId]

    try:
        await configAckService.handleAck(
            "greenhouse-02",
            {
                "deviceId": "greenhouse-02",
                "configId": configId,
                "result": "APPLIED",
                "reason": None,
            },
        )

        ack = configAckService.get(configId)
        assert ack is not None
        assert ack.result == "PENDING"
        assert ack.device_id == "greenhouse-01"
        assert configAckService._tasks.get(configId) is timeoutTask
        assert not timeoutTask.cancelled()
        assert not timeoutTask.done()
        assert broadcasts == []
    finally:
        configAckService.clear()


@pytest.mark.asyncio
async def test_config_ack_missing_device_id_is_ignored(monkeypatch) -> None:
    configAckService.clear()
    broadcasts = _captureConfigBroadcasts(monkeypatch)
    configId = "cfg-a8-device-002"
    configAckService.registerPending("greenhouse-01", configId)

    await configAckService.handleAck(
        "greenhouse-01",
        {"configId": configId, "result": "APPLIED"},
    )

    ack = configAckService.get(configId)
    assert ack is not None
    assert ack.result == "PENDING"
    assert ack.device_id == "greenhouse-01"
    assert broadcasts == []


@pytest.mark.asyncio
async def test_config_ack_becomes_timeout(monkeypatch) -> None:
    configAckService.clear()
    configAckService.bindLoop(asyncio.get_running_loop())
    broadcasts: list[tuple[str, dict]] = []
    pushed = asyncio.Event()

    async def capture(deviceId: str, message: dict) -> None:
        broadcasts.append((deviceId, message))
        pushed.set()

    monkeypatch.setattr(wsManager, "broadcast", capture)

    configId = "cfg-a8-timeout-001"

    configAckService.registerPending(
        "greenhouse-01",
        configId,
    )
    configAckService.scheduleTimeout(
        configId,
        timeoutSeconds=0.01,
    )

    await asyncio.wait_for(pushed.wait(), timeout=1)

    ack = configAckService.get(configId)

    assert ack is not None
    assert ack.result == "TIMEOUT"
    assert ack.reason == "TIMEOUT"
    assert ack.was_late is False
    assert broadcasts == [
        (
            "greenhouse-01",
            {
                "type": "config_result",
                "data": {
                    "configId": configId,
                    "result": "TIMEOUT",
                    "reason": "TIMEOUT",
                    "wasLate": False,
                },
            },
        )
    ]


@pytest.mark.asyncio
async def test_config_ack_timeout_survives_broadcast_exception(monkeypatch) -> None:
    configAckService.clear()
    configAckService.bindLoop(asyncio.get_running_loop())
    attempted = asyncio.Event()

    async def failBroadcast(_deviceId: str, _message: dict) -> None:
        attempted.set()
        raise RuntimeError("websocket unavailable")

    monkeypatch.setattr(wsManager, "broadcast", failBroadcast)
    configId = "cfg-a8-timeout-ws-error"
    configAckService.registerPending("greenhouse-01", configId)
    configAckService.scheduleTimeout(configId, timeoutSeconds=0)
    timeoutTask = configAckService._tasks[configId]

    await asyncio.wait_for(attempted.wait(), timeout=1)
    await asyncio.wait_for(asyncio.wrap_future(timeoutTask), timeout=1)

    ack = configAckService.get(configId)
    assert ack is not None
    assert ack.result == "TIMEOUT"
    assert ack.reason == "TIMEOUT"


@pytest.mark.asyncio
async def test_config_ack_late_reply_wins_over_timeout(monkeypatch) -> None:
    configAckService.clear()
    configAckService.bindLoop(asyncio.get_running_loop())
    broadcasts = _captureConfigBroadcasts(monkeypatch)
    pushed = asyncio.Event()

    async def capture(deviceId: str, message: dict) -> None:
        broadcasts.append((deviceId, message))
        if len(broadcasts) == 1:
            pushed.set()

    monkeypatch.setattr(wsManager, "broadcast", capture)

    configId = "cfg-a8-late-001"

    configAckService.registerPending(
        "greenhouse-01",
        configId,
    )
    configAckService.scheduleTimeout(
        configId,
        timeoutSeconds=0.01,
    )

    await asyncio.wait_for(pushed.wait(), timeout=1)

    timedOut = configAckService.get(configId)
    assert timedOut is not None
    assert timedOut.result == "TIMEOUT"
    assert timedOut.was_late is False

    await configAckService.handleAck(
        "greenhouse-02",
        {
            "deviceId": "greenhouse-02",
            "configId": configId,
            "result": "APPLIED",
            "reason": None,
        },
    )

    afterWrongDevice = configAckService.get(configId)
    assert afterWrongDevice is not None
    assert afterWrongDevice.result == "TIMEOUT"
    assert afterWrongDevice.device_id == "greenhouse-01"
    assert afterWrongDevice.was_late is False
    assert len(broadcasts) == 1

    await configAckService.handleAck(
        "greenhouse-01",
        {
            "deviceId": "greenhouse-01",
            "configId": configId,
            "result": "APPLIED",
            "reason": None,
        },
    )

    ack = configAckService.get(configId)

    assert ack is not None
    assert ack.result == "APPLIED"
    assert ack.reason is None
    assert ack.was_late is True
    assert broadcasts == [
        (
            "greenhouse-01",
            {
                "type": "config_result",
                "data": {
                    "configId": configId,
                    "result": "TIMEOUT",
                    "reason": "TIMEOUT",
                    "wasLate": False,
                },
            },
        ),
        (
            "greenhouse-01",
            {
                "type": "config_result",
                "data": {
                    "configId": configId,
                    "result": "APPLIED",
                    "reason": None,
                    "wasLate": True,
                },
            },
        ),
    ]


@pytest.mark.asyncio
async def test_config_ack_duplicate_and_unknown_ack_do_not_broadcast(monkeypatch) -> None:
    configAckService.clear()
    broadcasts = _captureConfigBroadcasts(monkeypatch)
    configId = "cfg-a8-duplicate-001"
    configAckService.registerPending("greenhouse-01", configId)

    ack = {
        "deviceId": "greenhouse-01",
        "configId": configId,
        "result": "APPLIED",
        "reason": None,
    }
    await configAckService.handleAck("greenhouse-01", ack)
    await configAckService.handleAck("greenhouse-01", ack)
    await configAckService.handleAck(
        "greenhouse-02",
        {
            "deviceId": "greenhouse-02",
            "configId": configId,
            "result": "APPLIED",
            "reason": None,
        },
    )
    await configAckService.handleAck(
        "greenhouse-01",
        {"configId": "cfg-a8-unknown-001", "result": "APPLIED"},
    )

    record = configAckService.get(configId)
    assert record is not None
    assert record.device_id == "greenhouse-01"
    assert record.result == "APPLIED"
    assert len(broadcasts) == 1
    assert broadcasts[0][1]["data"]["configId"] == configId

def test_post_config_returns_pending_config_id(monkeypatch) -> None:
    configAckService.clear()

    deviceId = "greenhouse-a8-test-01"
    stateService.markOnline(deviceId, True)

    published: dict = {}

    def fakePublish(payload: dict) -> bool:
        published.update(payload)
        return True

    monkeypatch.setattr(
        mqttService,
        "publishConfig",
        fakePublish,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/config",
            params={"deviceId": deviceId},
            json={
                "mode": "AUTO",
                "tempOnC": 31,
                "tempOffC": 29,
                "humidityOnPct": 54,
                "humidityOffPct": 66,
                "lightOnLux": 290,
                "lightOffLux": 710,
            },
        )

        assert response.status_code == 202

        body = response.json()

        assert body["status"] == "PENDING"
        assert body["configId"].startswith("cfg-")
        assert published["configId"] == body["configId"]

        record = configAckService.get(body["configId"])

        assert record is not None
        assert record.device_id == deviceId
        assert record.result == "PENDING"

        # Cancel the scheduled timeout while TestClient's loop is still alive.
        configAckService.clear()

def test_post_config_discards_pending_when_publish_fails(
    monkeypatch,
) -> None:
    configAckService.clear()

    deviceId = "greenhouse-a8-test-02"
    stateService.markOnline(deviceId, True)

    capturedConfigId: list[str] = []

    def fakePublish(payload: dict) -> bool:
        capturedConfigId.append(payload["configId"])
        return False

    monkeypatch.setattr(
        mqttService,
        "publishConfig",
        fakePublish,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/config",
            params={"deviceId": deviceId},
            json={
                "mode": "AUTO",
                "tempOnC": 32,
                "tempOffC": 28,
                "humidityOnPct": 53,
                "humidityOffPct": 67,
                "lightOnLux": 280,
                "lightOffLux": 720,
            },
        )

        assert response.status_code == 503
        assert len(capturedConfigId) == 1
        assert configAckService.get(capturedConfigId[0]) is None

        configAckService.clear()

def test_get_config_status_returns_correlated_record() -> None:
    configAckService.clear()

    configAckService.registerPending(
        "greenhouse-a8-status-test",
        "cfg-a8-status-001",
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/config/status",
            params={"configId": "cfg-a8-status-001"},
        )

    assert response.status_code == 200

    body = response.json()

    assert body == {
        "configId": "cfg-a8-status-001",
        "deviceId": "greenhouse-a8-status-test",
        "status": "PENDING",
        "reason": None,
        "wasLate": False,
    }

    configAckService.clear()

def test_get_config_status_unknown_returns_404() -> None:
    configAckService.clear()

    with TestClient(app) as client:
        response = client.get(
            "/api/config/status",
            params={"configId": "cfg-khong-ton-tai"},
        )

    assert response.status_code == 404
    assert "cfg-khong-ton-tai" in response.json()["detail"]
