"""Mock ESP32 for demos and Dashboard development - no hardware required.

Plays the device side of docs/mqtt-protocol.md v0.1 so the whole system can be
demonstrated before the ESP32 firmware has MQTT:

    publish greenhouse/01/telemetry   every TELEMETRY_PERIOD_S seconds
    publish greenhouse/01/state       on start and after every change
    publish greenhouse/01/status       online / offline (with Last Will)
    subscribe  greenhouse/01/command   replies APPLIED or REJECTED/NO_WATER
    subscribe  greenhouse/01/config    stores mode + hysteresis thresholds

Safety rules implemented (same as the firmware):
- MANUAL commands are refused unless mode == MANUAL  -> REJECTED/NOT_MANUAL_MODE
- The mist pump is refused while the tank is empty    -> REJECTED/NO_WATER
- The failsafe flag blocks the pump in both modes

Usage:
    pip install -r requirements.txt
    docker compose up -d                          # Eclipse Mosquitto on 1883
    python demo_esp32_mock.py                     # normal demo
    python demo_esp32_mock.py --no-water          # KB2 failsafe demo
    python demo_esp32_mock.py --no-water --sensor-fault
    python demo_esp32_mock.py --offline-after 30  # LWT / OFFLINE alert demo
"""

from __future__ import annotations

import argparse
import json
import random
import time

import paho.mqtt.client as mqtt

DEVICE_ID = "greenhouse-01"
PREFIX = "greenhouse/01"

TOPIC_TELEMETRY = f"{PREFIX}/telemetry"
TOPIC_STATE = f"{PREFIX}/state"
TOPIC_STATUS = f"{PREFIX}/status"
TOPIC_COMMAND = f"{PREFIX}/command"
TOPIC_CONFIG = f"{PREFIX}/config"


class MockEsp32:
    def __init__(self, args: argparse.Namespace) -> None:
        self.noWater = args.no_water
        self.sensorFault = args.sensor_fault
        self.offlineAfter = args.offline_after
        self.broker = args.broker
        self.port = args.port
        self.period = args.period
        self.mode = "AUTO"
        self.fan = False
        self.mist = False
        self.lamp = False
        self.lastCommandId: str | None = None
        self.lastCommandResult: str | None = None
        self.thresholds = {
            "tempOnC": 30.0,
            "tempOffC": 28.0,
            "humidityOnPct": 55.0,
            "humidityOffPct": 65.0,
            "lightOnLux": 300.0,
            "lightOffLux": 700.0,
        }
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="esp32-mock")
        # Last Will: the broker publishes offline when this process dies.
        self.client.will_set(TOPIC_STATUS, json.dumps({"online": False}), qos=1, retain=True)
        self.client.on_connect = self.onConnect
        self.client.on_message = self.onMessage

    # --- telemetry ---

    def temperature(self) -> float:
        return round(random.uniform(29.0, 33.5), 1)

    def humidity(self) -> float:
        return round(random.uniform(52.0, 68.0), 1)

    def light(self) -> float:
        return round(random.uniform(150, 850))

    def buildTelemetry(self) -> dict:
        if self.sensorFault:
            # Simulate an SHT31/BH1750 read failure: NULL, never NaN.
            return {
                "deviceId": DEVICE_ID,
                "temperatureC": None,
                "humidityPct": None,
                "lightLux": None,
                "waterOk": None,
            }
        return {
            "deviceId": DEVICE_ID,
            "temperatureC": self.temperature(),
            "humidityPct": self.humidity(),
            "lightLux": self.light(),
            "waterOk": not self.noWater,
        }

    # --- control ---

    def failsafeActive(self) -> bool:
        return self.noWater

    def autoControl(self, telemetry: dict) -> None:
        if self.noWater or telemetry["temperatureC"] is None:
            self.fan = False
            self.mist = False
        else:
            self.fan = telemetry["temperatureC"] >= self.thresholds["tempOnC"]
            self.mist = (
                not self.noWater
                and telemetry["humidityPct"] is not None
                and telemetry["humidityPct"] <= self.thresholds["humidityOnPct"]
            )
        if telemetry["lightLux"] is None:
            self.lamp = False
        else:
            self.lamp = telemetry["lightLux"] <= self.thresholds["lightOnLux"]

    def handleCommand(self, payload: dict) -> None:
        commandId = payload.get("commandId")
        device = payload.get("device")
        on = bool(payload.get("on"))

        if device not in {"fan", "mist", "lamp"}:
            print(f"command {commandId}: unknown device {device!r}")
            return

        # FAILSAFE has the highest priority and overrules MANUAL commands.
        if device == "mist" and self.noWater:
            self.mist = False
            self.lastCommandId, self.lastCommandResult = commandId, "REJECTED"
            print(f"command {commandId}: REJECTED (NO_WATER)")
            self.publishState(reason="NO_WATER")
            return

        if self.mode != "MANUAL":
            self.lastCommandId, self.lastCommandResult = commandId, "REJECTED"
            print(f"command {commandId}: REJECTED (NOT_MANUAL_MODE)")
            self.publishState(reason="NOT_MANUAL_MODE")
            return

        setattr(self, device, on)
        self.lastCommandId, self.lastCommandResult = commandId, "APPLIED"
        print(f"command {commandId}: APPLIED {device}={'ON' if on else 'OFF'}")
        self.publishState()

    def handleConfig(self, payload: dict) -> None:
        mode = str(payload.get("mode", self.mode)).upper()
        if mode not in {"AUTO", "MANUAL"}:
            mode = "AUTO"
        if payload.get("tempOnC", 0) <= payload.get("tempOffC", 0):
            print("config rejected: tempOnC must be > tempOffC")
            return
        self.mode = mode
        for key in self.thresholds:
            if key in payload:
                self.thresholds[key] = float(payload[key])
        print(f"config applied: mode={self.mode} thresholds={self.thresholds}")
        self.publishState()

    # --- MQTT plumbing ---

    def statePayload(self, reason: str | None = None) -> dict:
        return {
            "deviceId": DEVICE_ID,
            "mode": self.mode,
            "fan": self.fan,
            "mist": self.mist,
            "lamp": self.lamp,
            "failsafeActive": self.failsafeActive(),
            "lastCommandId": self.lastCommandId,
            "lastCommandResult": self.lastCommandResult,
            "reason": reason,
        }

    def publishState(self, reason: str | None = None) -> None:
        self.client.publish(TOPIC_STATE, json.dumps(self.statePayload(reason)), qos=1, retain=True)

    def publishStatus(self, online: bool) -> None:
        self.client.publish(TOPIC_STATUS, json.dumps({"online": online}), qos=1, retain=True)

    def onConnect(self, _client, _userdata, _flags, reasonCode, _properties=None) -> None:  # noqa: ANN001
        if reasonCode != 0:
            print(f"connect refused: {reasonCode}")
            return
        self.client.subscribe(TOPIC_COMMAND, qos=1)
        self.client.subscribe(TOPIC_CONFIG, qos=1)
        self.publishStatus(True)
        self.publishState()
        print(f"connected to {self.broker}:{self.port} as {DEVICE_ID}")

    def onMessage(self, _client, _userdata, message: mqtt.MQTTMessage) -> None:  # noqa: ANN001
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f"bad payload on {message.topic}")
            return
        if message.topic == TOPIC_COMMAND:
            self.handleCommand(payload)
        elif message.topic == TOPIC_CONFIG:
            self.handleConfig(payload)

    def run(self) -> None:
        self.client.connect(self.broker, self.port, keepalive=30)
        self.client.loop_start()

        mode = "FAILSAFE (no water)" if self.noWater else "NORMAL"
        if self.sensorFault:
            mode += " + SENSOR FAULT"
        print(f"mock ESP32 running [{mode}] - Ctrl+C to stop (LWT marks offline)")
        print(f"telemetry every {self.period}s on {TOPIC_TELEMETRY}")

        started = time.time()
        try:
            while True:
                telemetry = self.buildTelemetry()
                self.client.publish(TOPIC_TELEMETRY, json.dumps(telemetry), qos=0)
                print("telemetry:", telemetry)

                if self.mode == "AUTO":
                    self.autoControl(telemetry)
                    self.publishState()

                if self.offlineAfter and time.time() - started > self.offlineAfter:
                    print("simulating network loss")
                    self.publishStatus(False)
                    self.client.loop_stop()
                    self.client.disconnect()
                    print("disconnected. Restart to come back online.")
                    return

                time.sleep(self.period)
        except KeyboardInterrupt:
            print("\nstopping")
        finally:
            try:
                self.publishStatus(False)
            except Exception:  # noqa: BLE001 - best effort on shutdown
                pass
            self.client.loop_stop()
            self.client.disconnect()


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mock ESP32 for the greenhouse demo")
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--period", type=float, default=5.0, help="telemetry period in seconds")
    parser.add_argument("--no-water", action="store_true", help="empty tank (KB2 failsafe demo)")
    parser.add_argument("--sensor-fault", action="store_true", help="publish NULL sensors (SENSOR_FAULT)")
    parser.add_argument("--offline-after", type=float, default=0, help="go offline after N seconds")
    return parser.parse_args()


if __name__ == "__main__":
    MockEsp32(parseArgs()).run()
