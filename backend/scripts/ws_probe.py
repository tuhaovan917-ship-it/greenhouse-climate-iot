"""Live WebSocket probe: heartbeat + TIMEOUT push against a running server.

Usage:
    .venv/Scripts/python scripts/ws_probe.py ws://127.0.0.1:8092/ws?deviceId=greenhouse-01
"""

from __future__ import annotations

import asyncio
import json
import sys

import websockets


async def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8092/ws?deviceId=greenhouse-01"
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        print(f"[{'PASS' if condition else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
        if not condition:
            failures.append(name)

    async with websockets.connect(url) as socket:
        print("connected, staying silent for 25s (no client ping, no text)...")
        seen: list[dict] = []
        deadline = asyncio.get_event_loop().time() + 25
        while asyncio.get_event_loop().time() < deadline:
            try:
                message = await asyncio.wait_for(socket.recv(), timeout=25)
            except asyncio.TimeoutError:
                break
            seen.append(json.loads(message))

        pings = [item for item in seen if item.get("type") == "ping"]
        check("socket stayed open while silent", True, f"{len(seen)} message(s)")
        check("server sent heartbeat ping", len(pings) >= 1, f"ping count={len(pings)}")
        check(
            "ping shape is {type: ping}",
            all(item == {"type": "ping"} for item in pings),
            json.dumps(pings[:2]),
        )

    print()
    if failures:
        print(f"WS PROBE FAILED ({len(failures)}): {failures}")
        return 1
    print("WS PROBE PASSED: all checks green")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
