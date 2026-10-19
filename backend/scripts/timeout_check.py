"""Timeout and late-response checks against a real broker (contract 3.5).

A fake ESP32 connects to the broker but stays silent, so the command times out
and the Dashboard must receive `result: "TIMEOUT"` over the WebSocket. Then the
device replies late and the final result must win with `wasLate: true`.

    REST -> MQTT command -> (no reply) -> TIMEOUT -> WS command_result
    late reply -> APPLIED/REJECTED -> WS command_result (wasLate: true)

Usage:
    .venv/Scripts/python scripts/timeout_check.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PORT = 1887
DB_PATH = Path(tempfile.gettempdir()) / "greenhouse_timeout_check.db"
for suffix in ("", "-wal", "-shm"):
    candidate = Path(str(DB_PATH) + suffix)
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["MQTT_URL"] = f"mqtt://127.0.0.1:{PORT}"
os.environ["MQTT_ENABLED"] = "1"
os.environ["COMMAND_TIMEOUT_S"] = "2"
os.environ["DEVICE_TIMEOUT_S"] = "15"
os.environ["AUTO_CREATE_TABLES"] = "1"
# The in-process test broker is strict about keepalive; Mosquitto is not.
os.environ["MQTT_KEEPALIVE_S"] = "60"

import paho.mqtt.client as mqtt  # noqa: E402
from amqtt.broker import Broker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import createTablesForTest  # noqa: E402
from app.main import app  # noqa: E402
from app.mqtt_client import mqttService  # noqa: E402

createTablesForTest()

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    if not condition:
        failures.append(name)


async def waitFor(predicate, timeout: float = 20.0, interval: float = 0.3) -> bool:  # noqa: ANN001
    waited = 0.0
    while waited < timeout:
        if predicate():
            return True
        await asyncio.sleep(interval)
        waited += interval
    return predicate()


async def main() -> int:
    broker = Broker({"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{PORT}"}}, "sys_interval": 0})
    await broker.start()

    device = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="esp32-silent")
    device.will_set("greenhouse/01/status", json.dumps({"online": False}), qos=1, retain=True)
    device.connect("127.0.0.1", PORT, 30)
    device.loop_start()
    device.publish("greenhouse/01/status", json.dumps({"online": True}), qos=1, retain=True)

    with TestClient(app) as client:
        try:
            check("backend connected", await waitFor(mqttService.isConnected, 15))
            check(
                "device online",
                await waitFor(lambda: _state(client) is not None and _state(client)["online"] is True),
                "LWT status chua den",
            )

            with client.websocket_connect("/ws?deviceId=greenhouse-01") as socket:
                # 1. Silent device -> TIMEOUT pushed on the WebSocket.
                accepted = client.post(
                    "/api/commands",
                    json={"deviceId": "greenhouse-01", "device": "fan", "on": True},
                )
                check("POST /api/commands -> 202", accepted.status_code == 202, str(accepted.status_code))
                commandId = accepted.json().get("commandId", "")

                timeoutMessage = _waitForWs(socket, "command_result")
                check(
                    "TIMEOUT pushed on WebSocket",
                    timeoutMessage is not None and timeoutMessage["data"]["result"] == "TIMEOUT",
                    json.dumps(timeoutMessage) if timeoutMessage else "khong nhan duoc",
                )
                check(
                    "TIMEOUT reason",
                    timeoutMessage is not None and timeoutMessage["data"]["reason"] == "TIMEOUT",
                )
                check(
                    "command row is TIMEOUT",
                    _status(client, commandId) == "TIMEOUT",
                    _status(client, commandId),
                )

                # 2. Late reply wins over TIMEOUT. The device retries the publish
                #    so the test does not depend on broker keepalive timing.
                latePayload = json.dumps(
                    {
                        "deviceId": "greenhouse-01",
                        "mode": "MANUAL",
                        "fan": True,
                        "mist": False,
                        "lamp": False,
                        "failsafeActive": False,
                        "lastCommandId": commandId,
                        "lastCommandResult": "APPLIED",
                    }
                )

                lateMessage = None
                for _ in range(15):
                    device.publish("greenhouse/01/state", latePayload, qos=1)
                    await asyncio.sleep(1.0)
                    if _status(client, commandId) == "APPLIED":
                        lateMessage = _waitForWs(socket, "command_result")
                        break

                check(
                    "late reply flagged wasLate=true",
                    lateMessage is not None and lateMessage["data"]["wasLate"] is True,
                    json.dumps(lateMessage) if lateMessage else "khong nhan duoc",
                )
                check(
                    "late result is APPLIED",
                    lateMessage is not None and lateMessage["data"]["result"] == "APPLIED",
                )
                check(
                    "command row updated to APPLIED",
                    _status(client, commandId) == "APPLIED",
                    _status(client, commandId),
                )

                # 3. A repeated late reply is a no-op (no extra WS message).
                device.publish(
                    "greenhouse/01/state",
                    json.dumps(
                        {
                            "deviceId": "greenhouse-01",
                            "mode": "MANUAL",
                            "fan": True,
                            "mist": False,
                            "lamp": False,
                            "failsafeActive": False,
                            "lastCommandId": commandId,
                            "lastCommandResult": "APPLIED",
                        }
                    ),
                    qos=1,
                )
                await asyncio.sleep(2.0)
                extra = _waitForWs(socket, "command_result", maxReads=2)
                check("duplicate reply does not push again", extra is None, json.dumps(extra) if extra else "")
                check("still one command row", len(client.get("/api/commands").json()["data"]) == 1)
        finally:
            device.loop_stop()
            device.disconnect()
            mqttService.stop()

    await broker.shutdown()
    print()
    if failures:
        print(f"TIMEOUT CHECK FAILED ({len(failures)}): {failures}")
        return 1
    print("TIMEOUT CHECK PASSED: all checks green")
    return 0


def _state(client: TestClient) -> dict | None:
    response = client.get("/api/state")
    return response.json() if response.status_code == 200 else None


def _status(client: TestClient, commandId: str) -> str:
    for row in client.get("/api/commands").json()["data"]:
        if row["commandId"] == commandId:
            return row["status"]
    return "missing"


def _waitForWs(socket, wanted: str, maxReads: int = 6) -> dict | None:  # noqa: ANN001
    for _ in range(maxReads):
        message = socket.receive_json()
        if message.get("type") == wanted:
            return message
    return None


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
