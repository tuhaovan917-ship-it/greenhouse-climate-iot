"""Device state cache: latest ESP32 state, online flag and lastSeenAt.

Source of truth is the `device_states` table; this in-memory layer exists so
`GET /api/state` stays cheap and so the online/offline monitor can run without
touching the database every second.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.dialects.postgresql import insert as pgInsert
from sqlalchemy.dialects.sqlite import insert as sqliteInsert
from sqlmodel import Session

from app.config import settings
from app.models import DeviceConfig, DeviceState, utcNow

logger = logging.getLogger(__name__)


@dataclass
class DeviceRuntime:
    """Latest observed runtime information for one device."""

    device_id: str
    last_seen_at: datetime | None = None
    online: bool = False
    last_command_id: str | None = None
    last_command_result: str | None = None
    reason: str | None = None

    def markSeen(self) -> None:
        self.last_seen_at = utcNow()

    def isStale(self, now: datetime | None = None) -> bool:
        """True when no valid message arrived within DEVICE_TIMEOUT_S."""
        if self.last_seen_at is None:
            return True
        reference = now or utcNow()
        return reference - self.last_seen_at > timedelta(seconds=settings.device_timeout_s)


def upsertDeviceState(session: Session, deviceId: str, values: dict) -> DeviceState:
    """Insert-or-update the state row in a single statement.

    `status` and `telemetry` can arrive at the same moment, so a plain
    "SELECT then INSERT" races and violates the primary key on
    `device_states.device_id`. ON CONFLICT keeps both SQLite and PostgreSQL
    working without engine-specific SQL in the rest of the codebase.
    """
    dialect = session.get_bind().dialect.name
    payload = {"device_id": deviceId, **values}
    table = DeviceState.__table__

    if dialect == "postgresql":
        statement = pgInsert(table).values(**payload).on_conflict_do_update(
            index_elements=[table.c.device_id], set_=values
        )
    else:
        statement = sqliteInsert(table).values(**payload).on_conflict_do_update(
            index_elements=[table.c.device_id], set_=values
        )

    session.execute(statement)
    session.flush()
    # The identity map may still hold the pre-upsert object, so drop the cached
    # attribute values before reading the row back.
    session.expire_all()
    state = session.get(DeviceState, deviceId)
    if state is None:  # pragma: no cover - only if the row vanished mid-transaction
        raise RuntimeError(f"Khong tim thay state cho {deviceId}")
    return state


def upsertDeviceConfig(session: Session, deviceId: str, values: dict) -> DeviceConfig:
    """Same race protection for the desired-configuration row."""
    dialect = session.get_bind().dialect.name
    payload = {"device_id": deviceId, **values}
    table = DeviceConfig.__table__

    if dialect == "postgresql":
        statement = pgInsert(table).values(**payload).on_conflict_do_update(
            index_elements=[table.c.device_id], set_=values
        )
    else:
        statement = sqliteInsert(table).values(**payload).on_conflict_do_update(
            index_elements=[table.c.device_id], set_=values
        )

    session.execute(statement)
    session.flush()
    session.expire_all()
    config = session.get(DeviceConfig, deviceId)
    if config is None:  # pragma: no cover
        raise RuntimeError(f"Khong tim thay config cho {deviceId}")
    return config


class StateService:
    def __init__(self) -> None:
        self._devices: dict[str, DeviceRuntime] = {}

    def runtime(self, deviceId: str) -> DeviceRuntime:
        runtime = self._devices.get(deviceId)
        if runtime is None:
            runtime = DeviceRuntime(device_id=deviceId)
            self._devices[deviceId] = runtime
        return runtime

    def markOnline(self, deviceId: str, online: bool) -> bool:
        runtime = self.runtime(deviceId)
        if runtime.online == online:
            return False
        runtime.online = online
        if online:
            runtime.markSeen()
        logger.info("device %s online=%s", deviceId, online)
        return True

    def markMessageReceived(self, deviceId: str) -> None:
        self.runtime(deviceId).markSeen()

    def recordCommandResult(self, deviceId: str, commandId: str, result: str, reason: str | None) -> None:
        runtime = self.runtime(deviceId)
        runtime.last_command_id = commandId
        runtime.last_command_result = result
        runtime.reason = reason

    def onlineFlags(self) -> dict[str, bool]:
        """online = explicit status AND recent traffic (contract 3.4)."""
        now = utcNow()
        return {
            deviceId: (runtime.online and not runtime.isStale(now))
            for deviceId, runtime in self._devices.items()
        }

    def staleDevices(self) -> list[DeviceRuntime]:
        """Devices that look online but exceeded DEVICE_TIMEOUT_S."""
        now = utcNow()
        return [
            runtime
            for runtime in self._devices.values()
            if runtime.online and runtime.isStale(now)
        ]


stateService = StateService()
