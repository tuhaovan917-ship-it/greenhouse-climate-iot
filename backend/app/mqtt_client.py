"""MQTT client: subscribes ESP32 topics, publishes Backend commands.

Topics follow docs/mqtt-protocol.md v0.1 with the fixed prefix
`greenhouse/01/` (deviceId `greenhouse-01`, broker greenhouse code 01).

Threading model
---------------
paho-mqtt callbacks run on the network thread. They must never touch the
database or the WebSocket registry directly, so every inbound message is
handed to the asyncio loop through `loop.call_soon_threadsafe`. The loop then
processes it inside a threadpool so blocking SQLAlchemy work does not stall
realtime messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import threading
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt

from app.config import Settings, settings

logger = logging.getLogger(__name__)

# Greenhouse code 01 -> topic prefix from docs/mqtt-protocol.md v0.1.
TOPIC_PREFIX = "greenhouse/01"


class MqttService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._mqtt = settings.mqtt
        self._prefix = TOPIC_PREFIX
        self._client: mqtt.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected = threading.Event()
        self._handler: Callable[[str, str, dict], Any] | None = None
        self._stateHandler: Callable[[str, dict], Any] | None = None
        self._statusHandler: Callable[[str, dict], Any] | None = None

    # --- lifecycle ---

    def bindLoop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def setHandlers(
        self,
        onTelemetry: Callable[[str, dict], Any],
        onState: Callable[[str, dict], Any],
        onStatus: Callable[[str, dict], Any],
    ) -> None:
        self._handler = onTelemetry
        self._stateHandler = onState
        self._statusHandler = onStatus

    def start(self) -> None:
        if not self._mqtt.enabled:
            logger.warning("MQTT disabled by MQTT_ENABLED=0; running API only")
            return

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self._mqtt.client_id,
            clean_session=True,
        )
        if self._mqtt.username:
            client.username_pw_set(self._mqtt.username, self._mqtt.password or None)
        if self._mqtt.use_tls:
            context = ssl.create_default_context(cafile=self._mqtt.ca_file)
            client.tls_set_context(context)

        client.on_connect = self._onConnect
        client.on_disconnect = self._onDisconnect
        client.on_message = self._onMessage

        self._client = client
        # connect_async + loop_start retries in the background, so the API still
        # boots when the broker is not running yet (classroom demo friendly).
        client.connect_async(self._mqtt.host, self._mqtt.port, self._mqtt.keepalive)
        client.loop_start()
        logger.info("MQTT starting: %s:%s (tls=%s)", self._mqtt.host, self._mqtt.port, self._mqtt.use_tls)

    def stop(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            try:
                self._client.disconnect()
            except Exception:  # noqa: BLE001 - best effort on shutdown
                pass
            self._client = None
        self._connected.clear()

    def isConnected(self) -> bool:
        return self._connected.is_set()

    # --- topics ---

    @property
    def topicTelemetry(self) -> str:
        return f"{self._prefix}/telemetry"

    @property
    def topicState(self) -> str:
        return f"{self._prefix}/state"

    @property
    def topicStatus(self) -> str:
        return f"{self._prefix}/status"

    @property
    def topicCommand(self) -> str:
        return f"{self._prefix}/command"

    @property
    def topicConfig(self) -> str:
        return f"{self._prefix}/config"

    # --- publish ---

    def publishCommand(self, commandId: str, device: str, on: bool) -> bool:
        """QoS 1, retain False so a reconnect never replays an old command."""
        return self._publish(self.topicCommand, {"commandId": commandId, "device": device, "on": on}, qos=1, retain=False)

    def publishConfig(self, config: dict) -> bool:
        return self._publish(self.topicConfig, config, qos=1, retain=False)

    def _publish(self, topic: str, payload: dict, qos: int, retain: bool) -> bool:
        if self._client is None or not self.isConnected():
            logger.warning("publish skipped (not connected): %s", topic)
            return False
        info = self._client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=qos, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error("publish failed rc=%s topic=%s", info.rc, topic)
            return False
        return True

    # --- paho callbacks (network thread) ---

    def _onConnect(self, _client, _userdata, _flags, reasonCode, _properties=None) -> None:  # noqa: ANN001
        if reasonCode == 0:
            self._connected.set()
            for topic in (self.topicTelemetry, self.topicState, self.topicStatus):
                self._client.subscribe(topic, qos=1)
            logger.info("MQTT connected, subscribed: %s", self.topicTelemetry)
        else:
            logger.error("MQTT connect refused: %s", reasonCode)

    def _onDisconnect(self, _client, _userdata, _flags, reasonCode, _properties=None) -> None:  # noqa: ANN001
        self._connected.clear()
        logger.warning("MQTT disconnected: %s", reasonCode)

    def _onMessage(self, _client, _userdata, message: mqtt.MQTTMessage) -> None:  # noqa: ANN001
        topic = message.topic
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("invalid JSON on %s: %r", topic, message.payload[:120])
            return
        if not isinstance(payload, dict):
            logger.warning("non-object payload on %s", topic)
            return

        logger.debug("rx %s: %s", topic, payload)
        deviceId = str(payload.get("deviceId") or self._settings.device_id)
        handler = self._resolveHandler(topic)
        if handler is None:
            logger.debug("ignored topic %s", topic)
            return
        self._dispatch(handler, topic, deviceId, payload)

    def _resolveHandler(self, topic: str) -> Callable[[str, dict], Any] | None:
        if topic == self.topicTelemetry:
            return self._handler
        if topic == self.topicState:
            return self._stateHandler
        if topic == self.topicStatus:
            return self._statusHandler
        return None

    def _dispatch(self, handler: Callable[[str, dict], Any], topic: str, deviceId: str, payload: dict) -> None:
        loop = self._loop
        if loop is None:
            logger.debug("no event loop bound yet, dropping %s", topic)
            return

        def _onDone(future) -> None:  # noqa: ANN001
            try:
                future.result()
            except asyncio.CancelledError:
                logger.debug("handler cancelled for %s", topic)
            except Exception:  # noqa: BLE001 - never kill the network thread
                logger.exception("handler failed for %s", topic)

        try:
            # The handlers are coroutine functions, so they must be scheduled on
            # the loop; calling them from this thread would create a coroutine
            # that is never awaited.
            asyncio.run_coroutine_threadsafe(
                handler(deviceId, payload), loop  # type: ignore[misc]
            ).add_done_callback(_onDone)
        except RuntimeError:
            logger.warning("event loop closed, dropping %s", topic)


mqttService = MqttService(settings)
