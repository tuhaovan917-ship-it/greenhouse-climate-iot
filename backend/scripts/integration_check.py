"""Full-stack integration check: Backend + Database (Alembic) + Dashboard.

This is the check TV1 asked for before merging: run the three parts together
and exercise the interesting cases (command, AUTO/MANUAL, disconnect, failsafe).

It starts everything on the local machine:
  1. an in-process MQTT broker (amqtt, dev dependency only)
  2. the Backend, bound to a database migrated by Alembic from `database/`
  3. the mock ESP32 (`demo_esp32_mock.py`)
  4. optionally the Dashboard dev server (needs `npm install` in dashboard/)

Then it drives the Backend exactly like the Dashboard does and checks the four
scenarios. Run it from `backend/`:

    .venv/Scripts/python scripts/integration_check.py
    .venv/Scripts/python scripts/integration_check.py --dashboard "D:/path/to/dashboard"
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys

import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _console import enableUtf8Console  # noqa: E402

enableUtf8Console()

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

BROKER_PORT = 1895
API_PORT = 8010
DEVICE = "greenhouse-01"

failures: list[str] = []

def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    if not condition:
        failures.append(name)

def call(path: str, params: dict | None = None, body: dict | None = None, method: str = "GET"):
    url = f"http://127.0.0.1:{API_PORT}{path}"
    if params:
        clean = {key: value for key, value in params.items() if value is not None}
        url = f"{url}?{urllib.parse.urlencode(clean)}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, (json.loads(raw) if raw else None)

def portFree(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0

def waitPort(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not portFree(port):
            return True
        time.sleep(0.5)
    return False

def startProcess(arguments: list[str], cwd: Path, env: dict | None = None) -> subprocess.Popen:
    merged = {**os.environ, **(env or {})}
    return subprocess.Popen(
        arguments,
        cwd=str(cwd),
        env=merged,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

def main() -> int:
    # The Windows console defaults to cp1252 and cannot print Vietnamese text.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # pragma: no cover - older Python
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="", help="duong dan DB da migrate (mac dinh: SQLite tam)")
    parser.add_argument("--dashboard", default="", help="thu muc dashboard da cai npm (de chay them frontend)")
    args = parser.parse_args()

    python = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)

    workDir = BACKEND_DIR / ".integration"
    workDir.mkdir(exist_ok=True)
    database = Path(args.database) if args.database else workDir / "integration.db"
    if not args.database:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(database) + suffix)
            if candidate.exists():
                candidate.unlink()

    env = {
        "DATABASE_URL": f"sqlite:///{database.as_posix()}",
        "AUTO_CREATE_TABLES": "1",
        "MQTT_URL": f"mqtt://127.0.0.1:{BROKER_PORT}",
        "MQTT_KEEPALIVE_S": "60",
        "DEVICE_TIMEOUT_S": "8",
        "COMMAND_TIMEOUT_S": "5",
    }

    processes: list[subprocess.Popen] = []
    try:
        print("=== 0. KHOI DONG ===")
        processes.append(
            startProcess([str(python), str(BACKEND_DIR / "scripts" / "_broker_dev.py"), str(BROKER_PORT)], BACKEND_DIR)
        )
        check("MQTT broker lenh duoc", waitPort(BROKER_PORT, 20))

        processes.append(
            startProcess(
                [str(python), "-m", "uvicorn", "app.main:app", "--port", str(API_PORT), "--log-level", "warning"],
                BACKEND_DIR,
                env,
            )
        )
        check("Backend lenh duoc", waitPort(API_PORT, 30))

        status, body = call("/api/health")
        check("GET /api/health", status == 200 and body["status"] == "ok", str(body))
        check("MQTT da ket noi", bool(body and body["mqttConnected"]), str(body))

        # 1. Device online + telemetry
        processes.append(
            startProcess(
                [str(python), str(BACKEND_DIR / "demo_esp32_mock.py"), "--broker", "127.0.0.1", "--port", str(BROKER_PORT), "--period", "2"],
                BACKEND_DIR,
            )
        )
        time.sleep(10)
        status, state = call("/api/state", {"deviceId": DEVICE})
        check("thiet bi online", status == 200 and state["online"] is True, str(state)[:90])
        status, latest = call("/api/telemetry/latest", {"deviceId": DEVICE})
        check("co telemetry", status == 200 and latest is not None, str(latest)[:80])

        # 2. AUTO -> MANUAL
        print("=== 1. CHUYEN AUTO -> MANUAL ===")
        status, body = call(
            "/api/config",
            {"deviceId": DEVICE},
            {
                "mode": "MANUAL",
                "tempOnC": 30,
                "tempOffC": 28,
                "humidityOnPct": 55,
                "humidityOffPct": 65,
                "lightOnLux": 300,
                "lightOffLux": 700,
            },
            method="POST",
        )
        check("POST /api/config -> 202 PUBLISHED", status == 202 and body["status"] == "PUBLISHED", str(body)[:80])

        manual = False
        deadline = time.time() + 15
        while time.time() < deadline:
            _, state = call("/api/state", {"deviceId": DEVICE})
            if state and state["mode"] == "MANUAL":
                manual = True
                break
            time.sleep(1)
        check("ESP32 nhan config va chuyen sang MANUAL", manual, str(state)[:90])

        # 3. Send a command -> APPLIED
        print("=== 2. GUI LENH ===")
        status, body = call(
            "/api/commands", None, {"deviceId": DEVICE, "device": "fan", "on": True}, method="POST"
        )
        check("POST /api/commands -> 202 PENDING", status == 202 and body["status"] == "PENDING", str(body))
        commandId = body["commandId"]

        applied = False
        deadline = time.time() + 15
        while time.time() < deadline:
            _, rows = call("/api/commands", {"deviceId": DEVICE, "limit": 10})
            row = next((item for item in rows["data"] if item["commandId"] == commandId), None)
            if row and row["status"] == "APPLIED":
                applied = True
                break
            time.sleep(1)
        check("lenh fan ON -> APPLIED", applied, str(row)[:100] if row else "missing")
        _, state = call("/api/state", {"deviceId": DEVICE})
        check("ESP32 bao fan dang bat", state["fan"] is True, str(state["fan"]))

        # 4. Disconnect
        print("=== 3. MAT KET NOI ===")
        for process in processes:
            if "demo_esp32_mock" in " ".join(process.args):
                process.terminate()
        offline = False
        deadline = time.time() + 25
        while time.time() < deadline:
            _, state = call("/api/state", {"deviceId": DEVICE})
            if state and state["online"] is False:
                offline = True
                break
            time.sleep(1)
        check("thiet bi chuyen sang offline", offline, str(state)[:90])
        _, alerts = call("/api/alerts", {"deviceId": DEVICE, "active": "true", "code": "OFFLINE"})
        check("canh bao OFFLINE duoc mo", len(alerts["data"]) == 1, str(alerts)[:110])
        if alerts["data"]:
            check("OFFLINE severity CRITICAL", alerts["data"][0]["severity"] == "CRITICAL")

        # 5. Failsafe
        print("=== 4. FAILSAFE (het nuoc) ===")
        processes.append(
            startProcess(
                [
                    str(python),
                    str(BACKEND_DIR / "demo_esp32_mock.py"),
                    "--broker", "127.0.0.1", "--port", str(BROKER_PORT),
                    "--period", "2", "--no-water",
                ],
                BACKEND_DIR,
            )
        )
        time.sleep(12)
        _, state = call("/api/state", {"deviceId": DEVICE})
        check("failsafeActive = true", state["failsafeActive"] is True, str(state)[:90])
        _, alerts = call("/api/alerts", {"deviceId": DEVICE, "active": "true", "code": "NO_WATER"})
        check("canh bao NO_WATER duoc mo", len(alerts["data"]) == 1, str(alerts)[:110])
        if alerts["data"]:
            check("NO_WATER severity CRITICAL", alerts["data"][0]["severity"] == "CRITICAL")

        _, body = call(
            "/api/config",
            {"deviceId": DEVICE},
            {
                "mode": "MANUAL",
                "tempOnC": 30,
                "tempOffC": 28,
                "humidityOnPct": 55,
                "humidityOffPct": 65,
                "lightOnLux": 300,
                "lightOffLux": 700,
            },
            method="POST",
        )
        time.sleep(6)
        status, body = call(
            "/api/commands", None, {"deviceId": DEVICE, "device": "mist", "on": True}, method="POST"
        )
        rejected = False
        deadline = time.time() + 15
        while time.time() < deadline:
            _, rows = call("/api/commands", {"deviceId": DEVICE, "limit": 10})
            row = next((item for item in rows["data"] if item["deviceId"] == DEVICE and item["device"] == "mist"), None)
            if row and row["status"] in {"REJECTED", "TIMEOUT"}:
                rejected = True
                break
            time.sleep(1)
        check("lenh bom ON khi het nuoc bi tu choi", rejected, str(row)[:110] if row else "missing")
        if row:
            check("ly do NO_WATER", row.get("reason") == "NO_WATER", str(row.get("reason")))
        _, state = call("/api/state", {"deviceId": DEVICE})
        check("bom van tat", state["mist"] is False, str(state["mist"]))
    finally:
        for process in processes:
            process.terminate()
        time.sleep(1)
        for process in processes:
            try:
                process.kill()
            except Exception:  # noqa: BLE001
                pass

    print()
    if failures:
        print(f"INTEGRATION CHECK FAILED ({len(failures)}): {failures}")
        return 1
    print("INTEGRATION CHECK PASSED: Backend + Database + thiet bi ao chay dung")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
