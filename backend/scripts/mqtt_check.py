"""MQTT integration check with a real broker (no Docker needed).

Runs an in-process amqtt broker on 127.0.0.1:1884, boots the Backend with MQTT
enabled, then plays the ESP32 role with paho-mqtt:

    status online -> state MANUAL -> telemetry -> command -> APPLIED reply
    telemetry with waterOk=false -> NO_WATER -> mist command -> REJECTED

Verifies the full path: MQTT in -> ingest -> DB -> REST/WS out, including the
command PENDING -> APPLIED lifecycle and QoS 1 duplicate suppression.

Usage:
    .venv/Scripts/python scripts/mqtt_check.py
    (amqtt is a dev-only dependency, not in requirements.txt)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _console import enableUtf8Console  # noqa: E402

enableUtf8Console()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PORT = 1884
DB_PATH = Path(tempfile.gettempdir()) / "greenhouse_mqtt_check.db"
for suffix in ("", "-wal", "-shm"):
    candidate = Path(str(DB_PATH) + suffix)
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["MQTT_URL"] = f"mqtt://127.0.0.1:{PORT}"
os.environ["MQTT_ENABLED"] = "1"
os.environ["MQTT_CLIENT_ID"] = "greenhouse-backend-check"
os.environ["COMMAND_TIMEOUT_S"] = "2"
os.environ["DEVICE_TIMEOUT_S"] = "15"
os.environ["AUTO_CREATE_TABLES"] = "1"

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

async def startBroker() -> Broker:
    broker = Broker({"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{PORT}"}}, "sys_interval": 0})
    await broker.start()
    return broker

async def waitFor(predicate, timeout: float = 10.0, interval: float = 0.2) -> bool:  # noqa: ANN001
    waited = 0.0
    while waited < timeout:
        if predicate():
            return True
        await asyncio.sleep(interval)
        waited += interval
    return predicate()

async def main() -> int:
    broker = await startBroker()
    esp32 = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="esp32-mock")
    esp32.will_set("greenhouse/01/status", json.dumps({"online": False}), qos=1, retain=True)
    esp32.connect("127.0.0.1", PORT, 30)
    esp32.loop_start()

    with TestClient(app) as client:
        try:
            check("backend connected to broker", await waitFor(mqttService.isConnected, 15))

            # 1. Device online.
            esp32.publish("greenhouse/01/status", json.dumps({"online": True}), qos=1, retain=True)
            check(
                "state online via MQTT status",
                await waitFor(lambda: _isOnline(client)),
                "15s device timeout is not the trigger here",
            )

            # 2. Real state message.
            esp32.publish(
                "greenhouse/01/state",
                json.dumps(
                    {
                        "deviceId": "greenhouse-01",
                        "mode": "MANUAL",
                        "fan": False,
                        "mist": False,
                        "lamp": False,
                        "failsafeActive": False,
                        "lastCommandId": None,
                        "lastCommandResult": None,
                    }
                ),
                qos=1,
                retain=True,
            )
            check(
                "state stored from MQTT",
                await waitFor(lambda: _stateMode(client) == "MANUAL"),
                _stateMode(client),
            )

            # 3. Telemetry with an empty tank -> NO_WATER.
            esp32.publish(
                "greenhouse/01/telemetry",
                json.dumps(
                    {
                        "deviceId": "greenhouse-01",
                        "temperatureC": 33.0,
                        "humidityPct": 50.0,
                        "lightLux": 900,
                        "waterOk": False,
                    }
                ),
                qos=0,
            )
            check(
                "NO_WATER alert from MQTT telemetry",
                await waitFor(lambda: _activeAlerts(client) == 1),
                f"active={_activeAlerts(client)}",
            )

            # 4. KB1: valid command -> APPLIED.
            replies: list[dict] = []

            def onCommand(_client, _userdata, message: mqtt.MQTTMessage) -> None:
                payload = json.loads(message.payload.decode())
                replies.append(payload)
                esp32.publish(
                    "greenhouse/01/state",
                    json.dumps(
                        {
                            "deviceId": "greenhouse-01",
                            "mode": "MANUAL",
                            "fan": bool(payload.get("on")),
                            "mist": False,
                            "lamp": False,
                            "failsafeActive": False,
                            "lastCommandId": payload["commandId"],
                            "lastCommandResult": "APPLIED",
                        }
                    ),
                    qos=1,
                )

            esp32.subscribe("greenhouse/01/command", qos=1)
            esp32.on_message = onCommand

            accepted = client.post(
                "/api/commands", json={"deviceId": "greenhouse-01", "device": "fan", "on": True}
            )
            check("POST /api/commands -> 202", accepted.status_code == 202, str(accepted.status_code))
            commandId = accepted.json().get("commandId", "")

            check("MQTT command received by device", await waitFor(lambda: bool(replies)), str(replies))
            if replies:
                check(
                    "command payload matches mqtt-protocol v0.1",
                    replies[0] == {"commandId": commandId, "device": "fan", "on": True},
                    json.dumps(replies[0]),
                )
            check(
                "command becomes APPLIED",
                await waitFor(lambda: _commandStatus(client, commandId) == "APPLIED"),
                _commandStatus(client, commandId),
            )

            # 5. QoS 1 duplicate must not create a second transition.
            esp32.publish(
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
            await asyncio.sleep(1.5)
            history = client.get("/api/commands").json()["data"]
            check("command log has one row", len(history) == 1, f"rows={len(history)}")
            check("duplicate reply stays APPLIED", history[0]["status"] == "APPLIED", history[0]["status"])

            # 6. KB2: failsafe blocks the mist pump.
            esp32.on_message = None

            def onCommandReject(_client, _userdata, message: mqtt.MQTTMessage) -> None:
                payload = json.loads(message.payload.decode())
                esp32.publish(
                    "greenhouse/01/state",
                    json.dumps(
                        {
                            "deviceId": "greenhouse-01",
                            "mode": "MANUAL",
                            "fan": True,
                            "mist": False,
                            "lamp": False,
                            "failsafeActive": True,
                            "lastCommandId": payload["commandId"],
                            "lastCommandResult": "REJECTED",
                            "reason": "NO_WATER",
                        }
                    ),
                    qos=1,
                )

            esp32.on_message = onCommandReject
            rejected = client.post(
                "/api/commands", json={"deviceId": "greenhouse-01", "device": "mist", "on": True}
            )
            rejectedId = rejected.json().get("commandId", "")
            check(
                "failsafe command REJECTED",
                await waitFor(lambda: _commandStatus(client, rejectedId) == "REJECTED"),
                _commandStatus(client, rejectedId),
            )
            check(
                "rejected reason is NO_WATER",
                client.get("/api/commands").json()["data"][0].get("reason") == "NO_WATER",
            )

            # 7. Config publish reaches the device.
            configMessages: list[dict] = []

            def onConfig(_client, _userdata, message: mqtt.MQTTMessage) -> None:
                configMessages.append(json.loads(message.payload.decode()))

            esp32.subscribe("greenhouse/01/config", qos=1)
            esp32.on_message = onConfig
            published = client.post(
                "/api/config",
                json={
                    "mode": "MANUAL",
                    "tempOnC": 31,
                    "tempOffC": 27,
                    "humidityOnPct": 50,
                    "humidityOffPct": 60,
                    "lightOnLux": 250,
                    "lightOffLux": 650,
                },
            )
            check("POST /api/config -> 202 PUBLISHED", published.status_code == 202, str(published.status_code))
            check(
                "config status is PUBLISHED (not applied)",
                published.json().get("status") == "PUBLISHED",
                str(published.json())[:80],
            )
            check("config reached the device", await waitFor(lambda: bool(configMessages)), str(configMessages))
            if configMessages:
                check(
                    "config payload uses camelCase MQTT keys",
                    set(configMessages[0]) == {
                        "mode",
                        "tempOnC",
                        "tempOffC",
                        "humidityOnPct",
                        "humidityOffPct",
                        "lightOnLux",
                        "lightOffLux",
                    },
                    str(configMessages[0]),
                )

            # 8. Bucket aggregation over real MQTT data.
            for index in range(4):
                esp32.publish(
                    "greenhouse/01/telemetry",
                    json.dumps(
                        {
                            "deviceId": "greenhouse-01",
                            "temperatureC": 30.0 + index,
                            "humidityPct": 55.0,
                            "lightLux": 400,
                            "waterOk": True,
                        }
                    ),
                    qos=0,
                )
                await asyncio.sleep(0.3)
            await asyncio.sleep(1.5)
            bucketed = client.get("/api/telemetry", params={"bucket": "1m", "limit": 5}).json()
            totalSamples = sum(bucket["sampleCount"] for bucket in bucketed["data"])
            check(
                "MQTT telemetry aggregated in 1m bucket",
                bucketed["bucket"] == "1m" and totalSamples >= 5,
                f"totalSampleCount={totalSamples} buckets={len(bucketed['data'])}",
            )
            check(
                "NO_WATER resolved after refill",
                await waitFor(lambda: _activeAlerts(client) == 0),
                f"active={_activeAlerts(client)}",
            )
        finally:
            esp32.loop_stop()
            esp32.disconnect()
            mqttService.stop()

    await broker.shutdown()

    print()
    if failures:
        print(f"MQTT CHECK FAILED ({len(failures)}): {failures}")
        return 1
    print("MQTT CHECK PASSED: all checks green")
    return 0

def _state(client: TestClient) -> dict | None:
    response = client.get("/api/state")
    return response.json() if response.status_code == 200 else None

def _stateMode(client: TestClient) -> str:
    state = _state(client)
    return state["mode"] if state else "none"

def _isOnline(client: TestClient) -> bool:
    state = _state(client)
    return bool(state and state["online"])

def _activeAlerts(client: TestClient) -> int:
    return len(client.get("/api/alerts", params={"active": "true"}).json()["data"])

def _commandStatus(client: TestClient, commandId: str) -> str:
    for row in client.get("/api/commands").json()["data"]:
        if row["commandId"] == commandId:
            return row["status"]
    return "missing"

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
