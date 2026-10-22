"""End-to-end check of the whole Backend in one process (MQTT disabled).

Drives the ingest services exactly like MQTT messages would, then asserts what
the Dashboard sees over HTTP and WebSocket:

    status   -> state online, no alert
    telemetry-> DB row + WS telemetry + REST raw/bucket envelope
    FAILSAFE -> NO_WATER alert (deduped, CRITICAL) + resolves on recovery
    command  -> REJECTED mirrored on GET /api/state
    config   -> defaults + hysteresis validation + offline rejection

Usage:
    .venv/Scripts/python scripts/e2e_check.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DB_PATH = Path(tempfile.gettempdir()) / "greenhouse_e2e.db"
for suffix in ("", "-wal", "-shm"):
    candidate = Path(str(DB_PATH) + suffix)
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["MQTT_ENABLED"] = "0"
os.environ.setdefault("AUTO_CREATE_TABLES", "1")

import anyio  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import createTablesForTest  # noqa: E402
from app.main import app  # noqa: E402
from app.services import ingest  # noqa: E402

createTablesForTest()

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    if not condition:
        failures.append(name)


def send(coro) -> None:
    """Drive an ingest coroutine from this synchronous script."""
    anyio.run(lambda: coro)


def receiveOfType(socket, wanted: str, maxReads: int = 8) -> dict | None:  # noqa: ANN001
    """Read queued WS messages until the wanted type shows up."""
    for _ in range(maxReads):
        message = socket.receive_json()
        if message.get("type") == wanted:
            return message
    return None


def main() -> int:
    with TestClient(app) as client:
        with client.websocket_connect("/ws?deviceId=greenhouse-01") as socket:
            # 1. Device announces itself online (LWT channel).
            send(ingest.handleStatus("greenhouse-01", {"online": True}))
            online = receiveOfType(socket, "state")
            check("WS state after status", online is not None and online["data"]["online"] is True)

            # 2. Normal telemetry -> stored and pushed.
            send(
                ingest.handleTelemetry(
                    "greenhouse-01",
                    {
                        "deviceId": "greenhouse-01",
                        "temperatureC": 31.5,
                        "humidityPct": 58.0,
                        "lightLux": 380,
                        "waterOk": True,
                    },
                )
            )
            message = receiveOfType(socket, "telemetry")
            check("WS telemetry push", message is not None)
            if message:
                data = message["data"]
                check(
                    "telemetry camelCase + ISO8601 Z",
                    data["temperatureC"] == 31.5 and data["receivedAt"].endswith("Z"),
                    data["receivedAt"],
                )
            check("WS never sends bucket", receiveOfType(socket, "telemetry_bucket", maxReads=1) is None)

            # 3. History endpoints.
            raw = client.get("/api/telemetry", params={"bucket": "raw", "limit": 5}).json()
            check("REST raw envelope", raw["bucket"] == "raw" and isinstance(raw["data"][0]["id"], int))

            bucketed = client.get("/api/telemetry", params={"bucket": "1m", "limit": 5}).json()
            bucket = bucketed["data"][0]
            check("REST bucket envelope", bucketed["bucket"] == "1m")
            check("bucket has sampleCount, no id", bucket["sampleCount"] == 1 and "id" not in bucket)
            check("bucket waterOk last non-null", bucket["waterOk"] is True)

            # 4. Device FAILSAFE raises NO_WATER.
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
                    },
                )
            )
            receiveOfType(socket, "state")
            alerts = client.get("/api/alerts", params={"code": "NO_WATER", "active": "true"}).json()
            check("NO_WATER from FAILSAFE", len(alerts["data"]) == 1, str(alerts)[:110])
            if alerts["data"]:
                check("NO_WATER severity CRITICAL", alerts["data"][0]["severity"] == "CRITICAL")

            # 5. Repeated cycles must not duplicate the alert row.
            for _ in range(3):
                send(
                    ingest.handleTelemetry(
                        "greenhouse-01",
                        {"temperatureC": 31.0, "humidityPct": 58.0, "lightLux": 380, "waterOk": False},
                    )
                )
            alerts = client.get("/api/alerts", params={"code": "NO_WATER", "active": "true"}).json()
            check("alert dedup across cycles", len(alerts["data"]) == 1, f"rows={len(alerts['data'])}")

            # 6. REJECTED command mirrored on state.
            send(
                ingest.handleState(
                    "greenhouse-01",
                    {
                        "deviceId": "greenhouse-01",
                        "mode": "MANUAL",
                        "fan": False,
                        "mist": False,
                        "lamp": False,
                        "failsafeActive": True,
                        "lastCommandId": "cmd-e2e001",
                        "lastCommandResult": "REJECTED",
                        "reason": "NO_WATER",
                    },
                )
            )
            receiveOfType(socket, "state")
            state = client.get("/api/state").json()
            check("state mirrors REJECTED", state["lastCommandResult"] == "REJECTED", str(state.get("reason")))
            check("state online + lastSeenAt Z", state["online"] is True and state["lastSeenAt"].endswith("Z"))

            # 7. Tank recovers -> alert resolves.
            send(
                ingest.handleTelemetry(
                    "greenhouse-01",
                    {"temperatureC": 31.0, "humidityPct": 58.0, "lightLux": 380, "waterOk": True},
                )
            )
            receiveOfType(socket, "telemetry")
            active = client.get("/api/alerts", params={"code": "NO_WATER", "active": "true"}).json()
            resolved = client.get("/api/alerts", params={"code": "NO_WATER", "active": "false"}).json()
            check("alert resolved on recovery", len(active["data"]) == 0 and len(resolved["data"]) == 1)

            # 8. Config defaults and validation.
            config = client.get("/api/config").json()
            check("config defaults", config["mode"] == "AUTO" and config["tempOnC"] == 30.0, str(config)[:90])
            badConfig = client.post(
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
            check("hysteresis validation", badConfig.status_code == 400, str(badConfig.status_code))

            # 9. Writes are refused while the broker link is down.
            command = client.post(
                "/api/commands", json={"deviceId": "greenhouse-01", "device": "fan", "on": True}
            )
            check("command refused without MQTT", command.status_code in (409, 503), str(command.status_code))

            health = client.get("/api/health").json()
            check("health reports mqtt false", health["mqttConnected"] is False and health["db"] == "ok")

    print()
    if failures:
        print(f"E2E FAILED ({len(failures)}): {failures}")
        return 1
    print("E2E PASSED: all checks green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
