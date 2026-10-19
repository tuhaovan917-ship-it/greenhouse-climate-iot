"""Command lifecycle: PENDING -> APPLIED / REJECTED / TIMEOUT.

Contract section 3.5 and 4:
- REST publish creates a `PENDING` row first, then publishes MQTT.
- `command_result` on the WebSocket only ever carries APPLIED, REJECTED or
  TIMEOUT - PENDING is a REST-only status.
- A late ESP32 reply always wins over TIMEOUT (last-write-wins) and is pushed
  with `wasLate: true`; duplicate QoS 1 deliveries are no-ops.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import uuid
from dataclasses import dataclass

from sqlmodel import Session, select

from app.config import settings
from app.models import (
    COMMAND_APPLIED,
    COMMAND_PENDING,
    COMMAND_REJECTED,
    COMMAND_TIMEOUT,
    REASON_TIMEOUT,
    CommandLog,
    utcNow,
)

logger = logging.getLogger(__name__)


@dataclass
class CommandApplyResult:
    """Outcome of applying a device reply to a command row.

    `changed` is False for a duplicate QoS 1 delivery, which must not trigger an
    extra WebSocket push (contract 3.5).
    """

    log: CommandLog | None
    changed: bool = False
    wasLate: bool = False


def newCommandId() -> str:
    return f"cmd-{uuid.uuid4().hex[:6]}"


class CommandService:
    def __init__(self) -> None:
        self._tasks: dict[str, "concurrent.futures.Future[None]"] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bindLoop(self, loop: asyncio.AbstractEventLoop) -> None:
        """The REST endpoints run in a threadpool, so the timeout task has to be
        scheduled back onto the server loop explicitly."""
        self._loop = loop

    # --- creation ---

    def createPending(self, session: Session, deviceId: str, device: str, on: bool) -> CommandLog:
        log = CommandLog(
            command_id=newCommandId(),
            device_id=deviceId,
            device=device,
            requested_on=on,
            status=COMMAND_PENDING,
            requested_at=utcNow(),
        )
        session.add(log)
        logger.info("command created: %s %s on=%s", log.command_id, device, on)
        return log

    def scheduleTimeout(self, commandId: str) -> None:
        """Mark TIMEOUT when the ESP32 does not answer in time."""
        if self._loop is None:
            logger.debug("no loop bound, timeout not scheduled for %s", commandId)
            return
        self.cancelTimeout(commandId)

        async def _wait() -> None:
            try:
                await asyncio.sleep(settings.command_timeout_s)
                await asyncio.to_thread(self._markTimeout, commandId)
            except asyncio.CancelledError:
                raise

        try:
            self._tasks[commandId] = asyncio.run_coroutine_threadsafe(_wait(), self._loop)
        except RuntimeError:
            logger.warning("event loop unavailable, timeout not scheduled for %s", commandId)

    def cancelTimeout(self, commandId: str) -> None:
        task = self._tasks.pop(commandId, None)
        if task is not None and not task.done():
            task.cancel()

    # --- transitions ---

    def _markTimeout(self, commandId: str) -> None:
        """Mark a command TIMEOUT and tell the Dashboard (contract 3.5).

        The Dashboard must learn about the timeout through the WebSocket, not
        only by polling `GET /api/commands`.
        """
        from app.database import sessionScope  # local import avoids a cycle

        timedOut: tuple[str, str] | None = None
        try:
            with sessionScope() as session:
                log = self.get(session, commandId)
                if log is None or log.status != COMMAND_PENDING:
                    return
                log.status = COMMAND_TIMEOUT
                log.reason = REASON_TIMEOUT
                log.completed_at = utcNow()
                timedOut = (log.device_id, log.command_id)
                logger.warning("command timeout: %s", commandId)
        except Exception:  # noqa: BLE001 - never kill the timeout task
            logger.exception("failed to mark timeout for %s", commandId)
        finally:
            self._tasks.pop(commandId, None)

        if timedOut is not None:
            self._publishTimeout(timedOut[0], timedOut[1])

    def _publishTimeout(self, deviceId: str, commandId: str) -> None:
        """Push the TIMEOUT result to the Dashboard."""
        from app.schemas import WsCommandResultMessage
        from app.ws_manager import wsManager

        message = WsCommandResultMessage(
            data={
                "command_id": commandId,
                "result": COMMAND_TIMEOUT,
                "reason": REASON_TIMEOUT,
                "was_late": False,
            }
        )

        async def _send() -> None:
            await wsManager.broadcast(
                deviceId, message.model_dump(mode="json", by_alias=True)
            )

        if self._loop is None:
            logger.warning("no loop bound, timeout not pushed for %s", commandId)
            return
        try:
            asyncio.run_coroutine_threadsafe(_send(), self._loop)
        except RuntimeError:
            logger.warning("event loop closed, timeout not pushed for %s", commandId)

    def applyResult(
        self,
        session: Session,
        commandId: str,
        result: str,
        reason: str | None,
    ) -> CommandApplyResult:
        """Apply a device reply.

        A reply arriving after TIMEOUT still updates the row and reports
        `wasLate=True` so the Dashboard can show the real final result. A repeat
        of the same final result is a duplicate QoS 1 delivery: `changed=False`.
        """
        log = self.get(session, commandId)
        if log is None:
            logger.warning("reply for unknown command %s", commandId)
            return CommandApplyResult(log=None)

        # The ESP32 republishes `state` on a timer. Once a terminal result is
        # recorded, a repeat of the same result is a no-op and must not clear an
        # already-known reason (contract 3.5).
        if log.status == result and log.status in (COMMAND_APPLIED, COMMAND_REJECTED):
            return CommandApplyResult(log=log, changed=False)

        wasLate = log.status == COMMAND_TIMEOUT
        log.status = result
        # Only a provided reason updates the stored one; null means "no new info".
        log.reason = reason or log.reason
        log.completed_at = utcNow()
        if wasLate:
            logger.info("late reply accepted for %s -> %s", commandId, result)
        return CommandApplyResult(log=log, changed=True, wasLate=wasLate)

    # --- queries ---

    @staticmethod
    def get(session: Session, commandId: str) -> CommandLog | None:
        return session.get(CommandLog, commandId)

    @staticmethod
    def listRecent(session: Session, deviceId: str, limit: int) -> list[CommandLog]:
        statement = (
            select(CommandLog)
            .where(CommandLog.device_id == deviceId)
            .order_by(CommandLog.requested_at.desc())
            .limit(limit)
        )
        return list(session.exec(statement).all())


commandService = CommandService()
