"""A8 configuration acknowledgement lifecycle service."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConfigAckRecord:
    device_id: str
    config_id: str
    result: str
    reason: str | None = None
    was_late: bool = False


class ConfigAckService:
    def __init__(self) -> None:
        self._acks: dict[str, ConfigAckRecord] = {}
        self._tasks: dict[
            str,
            concurrent.futures.Future[None],
        ] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bindLoop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def registerPending(
        self,
        deviceId: str,
        configId: str,
    ) -> ConfigAckRecord:
        record = ConfigAckRecord(
            device_id=deviceId,
            config_id=configId,
            result="PENDING",
        )

        with self._lock:
            self._acks[configId] = record

        logger.info("config pending: %s", configId)
        return record

    def scheduleTimeout(
        self,
        configId: str,
        timeoutSeconds: float | None = None,
    ) -> None:
        with self._lock:
            current = self._acks.get(configId)

            if current is None or current.result != "PENDING":
                return

        if self._loop is None:
            logger.debug(
                "no loop bound, config timeout not scheduled for %s",
                configId,
            )
            return

        self.cancelTimeout(configId)

        delay = (
            settings.config_ack_timeout_s
            if timeoutSeconds is None
            else timeoutSeconds
        )

        async def _wait() -> None:
            try:
                await asyncio.sleep(delay)
                await self._markTimeout(configId)
            except asyncio.CancelledError:
                raise
            finally:
                self._tasks.pop(configId, None)

        try:
            self._tasks[configId] = asyncio.run_coroutine_threadsafe(
                _wait(),
                self._loop,
            )
        except RuntimeError:
            logger.warning(
                "event loop unavailable, config timeout not scheduled for %s",
                configId,
            )

    def cancelTimeout(self, configId: str) -> None:
        task = self._tasks.pop(configId, None)

        if task is not None and not task.done():
            task.cancel()

    async def _markTimeout(self, configId: str) -> None:
        with self._lock:
            current = self._acks.get(configId)

            if current is None or current.result != "PENDING":
                return

            timedOut = ConfigAckRecord(
                device_id=current.device_id,
                config_id=current.config_id,
                result="TIMEOUT",
                reason="TIMEOUT",
                was_late=False,
            )
            self._acks[configId] = timedOut

        logger.warning("config ACK timeout: %s", configId)
        await self._broadcastResult(timedOut)

    async def handleAck(
        self,
        _deviceId: str,
        payload: dict,
    ) -> None:
        configId = str(payload.get("configId") or "").strip()
        ackDeviceId = str(payload.get("deviceId") or "").strip()
        result = str(payload.get("result") or "").strip().upper()

        if not configId or len(configId) > 64:
            logger.warning(
                "config ACK missing/invalid configId: %r",
                configId,
            )
            return

        with self._lock:
            current = self._acks.get(configId)

            if current is None:
                logger.warning(
                    "config ACK for unknown configId: %s",
                    configId,
                )
                return

            if not ackDeviceId:
                logger.warning(
                    "config ACK missing deviceId: configId=%s",
                    configId,
                )
                return

            if ackDeviceId != current.device_id:
                logger.warning(
                    "config ACK device mismatch: configId=%s expected=%s received=%s",
                    configId,
                    current.device_id,
                    ackDeviceId,
                )
                return

            if result not in {"APPLIED", "REJECTED"}:
                logger.warning(
                    "config ACK invalid result for %s: %r",
                    configId,
                    result,
                )
                return

            # QoS 1 can redeliver the same ACK.
            if current.result in {"APPLIED", "REJECTED"}:
                logger.debug(
                    "duplicate config ACK ignored: %s",
                    configId,
                )
                return

            wasLate = current.result == "TIMEOUT"
            rawReason = payload.get("reason")
            reason = None if rawReason is None else str(rawReason)

            self._acks[configId] = ConfigAckRecord(
                device_id=current.device_id,
                config_id=configId,
                result=result,
                reason=reason,
                was_late=wasLate,
            )
            updated = self._acks[configId]

        self.cancelTimeout(configId)

        logger.info(
            "config ACK correlated: %s -> %s (late=%s)",
            configId,
            result,
            wasLate,
        )
        await self._broadcastResult(updated)

    async def _broadcastResult(self, record: ConfigAckRecord) -> None:
        """Push one terminal Config ACK transition without affecting its lifecycle."""
        from app.schemas import WsConfigResultMessage
        from app.ws_manager import wsManager

        message = WsConfigResultMessage(
            data={
                "config_id": record.config_id,
                "result": record.result,
                "reason": record.reason,
                "was_late": record.was_late,
            }
        )
        try:
            await wsManager.broadcast(
                record.device_id,
                message.model_dump(mode="json", by_alias=True),
            )
        except Exception:  # noqa: BLE001 - a WS failure must not undo the ACK
            logger.exception(
                "failed to broadcast config ACK result for %s",
                record.config_id,
            )

    def get(self, configId: str) -> ConfigAckRecord | None:
        with self._lock:
            return self._acks.get(configId)

    def discard(self, configId: str) -> None:
        self.cancelTimeout(configId)

        with self._lock:
            self._acks.pop(configId, None)

    def clear(self) -> None:
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()

        self._tasks.clear()

        with self._lock:
            self._acks.clear()


configAckService = ConfigAckService()
