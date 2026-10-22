"""Cross-check the MQTT payload keys against docs/mqtt-protocol.md v0.1.

The Backend publishes `command` and `config` and consumes `telemetry`, `state`
and `status`. This script compares the keys used in the code with the keys
documented in the MQTT protocol, so a change on either side is caught early.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROTOCOL = REPO / "docs" / "mqtt-protocol.md"
# main is the released state; the feature branches stay as a fallback.
PROTOCOL_REF_CANDIDATES = (
    "origin/main:docs/mqtt-protocol.md",
    "origin/feat/esp32:docs/mqtt-protocol.md",
)
FIRMWARE_REF_CANDIDATES = (
    "origin/main:firmware/src/main.cpp",
    "origin/feat/esp32:firmware/src/main.cpp",
)

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    if not condition:
        failures.append(name)


def _readFirstRef(candidates: tuple[str, ...]) -> str:
    for ref in candidates:
        result = subprocess.run(
            ["git", "show", ref],
            cwd=REPO,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace")
    return ""


def protocolText() -> str:
    """Read the MQTT protocol from the working tree, or from git."""
    if PROTOCOL.exists():
        return PROTOCOL.read_text(encoding="utf-8")
    return _readFirstRef(PROTOCOL_REF_CANDIDATES)


def protocolKeys(section: str) -> set[str]:
    """Pull the JSON keys of one payload block out of the protocol document."""
    text = protocolText()
    match = re.search(rf"### {re.escape(section)}.*?```json\n(.*?)```", text, re.S)
    if not match:
        return set()
    return set(re.findall(r'"([A-Za-z][A-Za-z0-9]*)"\s*:', match.group(1)))


def codeKeys(fileName: str, pattern: str) -> set[str]:
    text = (REPO / "backend" / "app" / fileName).read_text(encoding="utf-8")
    match = re.search(pattern, text, re.S)
    if not match:
        return set()
    return set(re.findall(r'"([A-Za-z][A-Za-z0-9]*)"\s*:', match.group(1)))


def _firmwareSource() -> str:
    """Firmware main.cpp that carries the MQTT client (main first)."""
    return _readFirstRef(FIRMWARE_REF_CANDIDATES)


def main() -> int:
    print("=== MQTT payload keys: protocol vs Backend ===")

    # Backend -> ESP32
    commandKeys = codeKeys("mqtt_client.py", r"def publishCommand.*?\{(.*?)\}")
    expectedCommand = protocolKeys("3.4. Backend gửi `command`")
    check(
        "command payload matches protocol",
        commandKeys == expectedCommand,
        f"code={sorted(commandKeys)} protocol={sorted(expectedCommand)}",
    )

    configKeys = codeKeys("routers/config.py", r"def _toMqttPayload.*?return \{(.*?)\}")
    expectedConfig = protocolKeys("3.5. Backend gửi `config`")
    check(
        "config payload matches protocol",
        configKeys == expectedConfig,
        f"code={sorted(configKeys)} protocol={sorted(expectedConfig)}",
    )

    # ESP32 -> Backend (fields the ingest layer reads)
    ingestText = (REPO / "backend" / "app" / "services" / "ingest.py").read_text(encoding="utf-8")
    consumed = set(re.findall(r'payload\.get\("([A-Za-z][A-Za-z0-9]*)"', ingestText))

    telemetryExpected = protocolKeys("3.1. ESP32 gửi `telemetry`") - {"deviceId"}
    check(
        "Backend consumes every telemetry field",
        telemetryExpected <= consumed,
        f"missing={sorted(telemetryExpected - consumed)}",
    )

    stateExpected = protocolKeys("3.2. ESP32 gửi `state`") - {"deviceId"}
    check(
        "Backend consumes every state field",
        stateExpected <= consumed,
        f"missing={sorted(stateExpected - consumed)}",
    )

    check(
        "Backend consumes the online flag",
        "online" in consumed,
        f"consumed={sorted(consumed)}",
    )

    # Topics
    mqttText = (REPO / "backend" / "app" / "mqtt_client.py").read_text(encoding="utf-8")
    for topic in ("telemetry", "state", "status", "command", "config"):
        check(
            f"topic greenhouse/01/{topic} used by the Backend",
            f'f"{{self._prefix}}/{topic}"' in mqttText or f'PREFIX}}/{topic}"' in mqttText,
        )

    print()
    print("=== 6. FIRMWARE (feat/esp32) ===")
    firmware = _firmwareSource()
    if not firmware:
        check("firmware main.cpp doc duoc", False, "khong lay duoc tu origin/feat/esp32")
    else:
        for key in ("deviceId", "temperatureC", "humidityPct", "lightLux", "waterOk"):
            check(
                f"firmware publish telemetry.{key}",
                f'doc["{key}"]' in firmware,
            )
        for key in ("mode", "fan", "mist", "lamp", "failsafeActive", "lastCommandId", "lastCommandResult"):
            check(
                f"firmware publish state.{key}",
                f'doc["{key}"]' in firmware,
            )
        check(
            "firmware publish status.online",
            '\\"online\\":true' in firmware and '\\"online\\":false' in firmware,
        )
        check(
            "firmware doc biet cach gui deviceId dinh dung",
            'doc["deviceId"] = "greenhouse-01"' in firmware,
        )
        check(
            "firmware reset reason cho lenh moi",
            'mqttLastCommandReason = ""' in firmware,
        )
        check(
            "firmware co failover AUTO khi mat ket noi",
            "OFFLINE_AUTO_TIMEOUT_MS" in firmware and "MODE_AUTO" in firmware,
        )
        check(
            "firmware dat Last Will cho status",
            "setWill" in firmware,
        )
        check(
            "firmware publish state voi QoS 1 + retain",
            "greenhouse/01/state" in firmware,
        )

    print()
    if failures:
        print(f"PROTOCOL CROSS-CHECK FAILED ({len(failures)}): {failures}")
        return 1
    print("PROTOCOL CROSS-CHECK PASSED: all checks green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
