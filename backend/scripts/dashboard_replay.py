"""Replay the exact requests the Dashboard sends, against a live Backend.

This mirrors dashboard/src/api/greenhouseApi.ts (Member 3) request for request:
same paths, same query parameters, same bodies, same headers, same load order
(the Dashboard loads six endpoints in parallel with Promise.all, so a single
error breaks the whole page).

Two phases:
  A. cold start  - empty database, no device yet: every call must be 200
  B. running     - mock ESP32 connected: every call must be 200 with real data

Usage:
    .venv/Scripts/python scripts/dashboard_replay.py http://127.0.0.1:8093
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8093"
DEVICE = "greenhouse-01"
API_KEY = ""  # Dashboard sends X-API-Key only when VITE_API_KEY is set

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    if not condition:
        failures.append(name)


def call(path: str, params: dict | None = None, body: dict | None = None, method: str = "GET"):
    """Same behaviour as apiRequest() of the Dashboard."""
    url = f"{BASE}{path}"
    if params:
        clean = {key: value for key, value in params.items() if value is not None}
        url = f"{url}?{urllib.parse.urlencode(clean)}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, (json.loads(raw) if raw else None)


def dashboardInitialLoad() -> dict:
    """The six parallel calls of loadInitial() + the four history calls."""
    historyFrom = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    results: dict = {}

    status, body = call("/api/telemetry/latest", {"deviceId": DEVICE})
    results["telemetry/latest"] = (status, body)

    status, body = call("/api/state", {"deviceId": DEVICE})
    results["state"] = (status, body)

    for bucket in ("raw", "1m", "5m", "1h"):
        status, body = call(
            "/api/telemetry",
            {"deviceId": DEVICE, "bucket": bucket, "from": historyFrom, "limit": 100, "order": "asc"},
        )
        results[f"telemetry/{bucket}"] = (status, body)

    status, body = call("/api/config", {"deviceId": DEVICE})
    results["config"] = (status, body)

    status, body = call("/api/commands", {"deviceId": DEVICE, "limit": 50})
    results["commands"] = (status, body)

    status, body = call("/api/alerts", {"deviceId": DEVICE, "limit": 50})
    results["alerts"] = (status, body)

    return results


def checkAllOk(results: dict, phase: str) -> None:
    for name, (status, body) in results.items():
        check(f"{phase}: GET {name} -> 200", status == 200, f"status={status} body={str(body)[:110]}")


def main() -> int:
    print("=== A. LOAD SAFETY (Dashboard loads 10 endpoints in parallel) ===")
    results = dashboardInitialLoad()
    checkAllOk(results, "load")

    telemetry = results["telemetry/latest"][1]
    state = results["state"][1]
    check("load: telemetry/latest is null or a Telemetry", telemetry is None or isinstance(telemetry, dict), str(telemetry)[:90])
    check(
        "load: state is a valid DeviceState",
        isinstance(state, dict)
        and state.get("mode") in {"AUTO", "MANUAL"}
        and isinstance(state.get("online"), bool)
        and "lastSeenAt" in state
        and "updatedAt" in state,
        str(state)[:110],
    )
    if telemetry is None:
        check(
            "load: empty system -> state is offline default",
            state.get("online") is False
            and state.get("fan") is False
            and state.get("lastSeenAt") is None
            and state.get("updatedAt") is None,
            str(state),
        )
        check(
            "load: empty system -> history envelopes are empty",
            all(
                results[f"telemetry/{bucket}"][1]["data"] == []
                and results[f"telemetry/{bucket}"][1]["bucket"] == bucket
                for bucket in ("raw", "1m", "5m", "1h")
            ),
            str(results["telemetry/raw"][1])[:90],
        )
    check("load: config returns defaults", results["config"][1].get("tempOnC") == 30.0)
    check("load: commands list shape", isinstance(results["commands"][1].get("data"), list))
    check("load: alerts list shape", isinstance(results["alerts"][1].get("data"), list))

    print()
    print("=== B. RUNNING (mock ESP32 connected) ===")
    results = dashboardInitialLoad()
    checkAllOk(results, "running")

    telemetry = results["telemetry/latest"][1]
    state = results["state"][1]
    check("running: telemetry present", isinstance(telemetry, dict) and telemetry.get("id") is not None, str(telemetry)[:90])
    check(
        "running: telemetry camelCase + Z",
        telemetry.get("receivedAt", "").endswith("Z"),
        str(telemetry.get("receivedAt")),
    )
    check("running: state online", state.get("online") is True, str(state)[:90])
    check(
        "running: state has lastSeenAt",
        state.get("lastSeenAt") is not None and state["lastSeenAt"].endswith("Z"),
    )

    print()
    print("=== C. WRITE PATH (Dashboard control panel) ===")
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
    check("config POST -> 202 PUBLISHED", status == 202 and body.get("status") == "PUBLISHED", f"{status} {str(body)[:90]}")

    status, body = call(
        "/api/commands",
        None,
        {"deviceId": DEVICE, "device": "fan", "on": True},
        method="POST",
    )
    check(
        "command POST -> 202 PENDING",
        status == 202 and body.get("status") == "PENDING" and body.get("commandId"),
        f"{status} {str(body)[:90]}",
    )
    commandId = body.get("commandId", "")

    import time

    for _ in range(15):
        time.sleep(1)
        status, rows = call("/api/commands", {"deviceId": DEVICE, "limit": 50})
        row = next((item for item in rows["data"] if item["commandId"] == commandId), None)
        if row and row["status"] != "PENDING":
            break
    check(
        "command resolved (APPLIED/REJECTED/TIMEOUT)",
        row is not None and row["status"] in {"APPLIED", "REJECTED", "TIMEOUT"},
        str(row),
    )
    check("command row camelCase", row is not None and "requestedAt" in row and "completedAt" in row)

    print()
    if failures:
        print(f"DASHBOARD REPLAY FAILED ({len(failures)}): {failures}")
        return 1
    print("DASHBOARD REPLAY PASSED: all checks green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
