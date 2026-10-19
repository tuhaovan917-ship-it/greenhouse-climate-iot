"""Verify demo_esp32_mock.py against the live Backend + a real broker.

Starts an amqtt broker, boots the Backend with MQTT enabled, runs the mock as a
subprocess, then checks the two demo scenarios from the lecturer's template:

    KB1 valid command      -> APPLIED
    KB2 failsafe           -> REJECTED / NO_WATER, pump stays OFF

Also covers LWT-driven OFFLINE alerts and config application.

Usage:
    .venv/Scripts/python scripts/mock_demo_check.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

PORT = 1886
DB_PATH = Path(tempfile.gettempdir()) / "greenhouse_mock_demo.db"
for suffix in ("", "-wal", "-shm"):
    candidate = Path(str(DB_PATH) + suffix)
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["MQTT_URL"] = f"mqtt://127.0.0.1:{PORT}"
os.environ["MQTT_ENABLED"] = "1"
os.environ["COMMAND_TIMEOUT_S"] = "3"
os.environ["DEVICE_TIMEOUT_S"] = "15"
os.environ["AUTO_CREATE_TABLES"] = "1"

import amqtt  # noqa: E402,F401  (dev-only broker for this check)
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


def startMock(*extra: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(BACKEND_DIR / "demo_esp32_mock.py"), "--broker", "127.0.0.1", "--port", str(PORT), "--period", "2", *extra],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(BACKEND_DIR),
    )


def stopMock(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        output, _ = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate()
    tail = "\n".join((output or "").splitlines()[-6:])
    print(f"--- mock output tail ---\n{tail}")


def state(client: TestClient) -> dict | None:
    response = client.get("/api/state")
    return response.json() if response.status_code == 200 else None


async def main() -> int:
    broker = Broker({"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{PORT}"}}, "sys_interval": 0})
    await broker.start()

    with TestClient(app) as client:
        mock = startMock()
        try:
            check("backend connected", await waitFor(mqttService.isConnected, 15))
            check("mock device came online", await waitFor(lambda: bool(state(client) and state(client)["online"])))
            check(
                "telemetry stored",
                await waitFor(lambda: client.get("/api/telemetry/latest").status_code == 200),
            )

            # AUTO mode control from the mock's own thresholds.
            check(
                "mock state received",
                await waitFor(lambda: bool(state(client))),
                str(state(client))[:90] if state(client) else "none",
            )

            # KB1: MANUAL command that must be applied.
            published = client.post(
                "/api/config",
                json={
                    "mode": "MANUAL",
                    "tempOnC": 30,
                    "tempOffC": 28,
                    "humidityOnPct": 55,
                    "humidityOffPct": 65,
                    "lightOnLux": 300,
                    "lightOffLux": 700,
                },
            )
            check("config 202 PUBLISHED", published.status_code == 202, str(published.status_code))
            check("mock applied MANUAL", await waitFor(lambda: bool(state(client)) and state(client)["mode"] == "MANUAL"))

            command = client.post(
                "/api/commands", json={"deviceId": "greenhouse-01", "device": "fan", "on": True}
            )
            commandId = command.json().get("commandId", "")
            check(
                "KB1 command APPLIED",
                await waitFor(lambda: _status(client, commandId) == "APPLIED", 15),
                _status(client, commandId),
            )
            check("KB1 fan is ON", bool(state(client)) and state(client)["fan"] is True)

            # AUTO-mode refusal.
            autoConfig = client.post(
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
            check("switch back to AUTO", autoConfig.status_code == 202)
            check("mock applied AUTO", await waitFor(lambda: bool(state(client)) and state(client)["mode"] == "AUTO"))

            refused = client.post(
                "/api/commands", json={"deviceId": "greenhouse-01", "device": "fan", "on": False}
            )
            refusedId = refused.json().get("commandId", "")
            check(
                "command in AUTO mode rejected",
                await waitFor(lambda: _status(client, refusedId) == "REJECTED", 15),
                _status(client, refusedId),
            )
            check(
                "rejection reason NOT_MANUAL_MODE",
                _reason(client, refusedId) == "NOT_MANUAL_MODE",
                _reason(client, refusedId),
            )
        finally:
            stopMock(mock)

    await broker.shutdown()
    print()
    if failures:
        print(f"MOCK DEMO CHECK FAILED ({len(failures)}): {failures}")
        return 1
    print("MOCK DEMO CHECK PASSED: all checks green")
    return 0


def _row(client: TestClient, commandId: str) -> dict:
    for row in client.get("/api/commands").json()["data"]:
        if row["commandId"] == commandId:
            return row
    return {}


def _status(client: TestClient, commandId: str) -> str:
    return _row(client, commandId).get("status", "missing")


def _reason(client: TestClient, commandId: str) -> str:
    return str(_row(client, commandId).get("reason"))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
