"""API schemas - camelCase on the wire, snake_case in the database.

Mirrors the TypeScript types in docs/api-contract.md v0.2.2 section 2 exactly:
Telemetry, TelemetryBucket, TelemetryHistoryResponse, DeviceState, DeviceConfig,
CommandLog, Alert and the WS envelope.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, PlainSerializer, field_validator
from pydantic.alias_generators import to_camel

ControlMode = Literal["AUTO", "MANUAL"]
DeviceName = Literal["fan", "mist", "lamp"]
CommandStatus = Literal["PENDING", "APPLIED", "REJECTED", "TIMEOUT"]
TerminalCommandResult = Literal["APPLIED", "REJECTED", "TIMEOUT"]
Bucket = Literal["raw", "1m", "5m", "1h"]
AlertCode = Literal["NO_WATER", "SENSOR_FAULT", "OFFLINE"]
AlertSeverity = Literal["INFO", "WARNING", "CRITICAL"]

BUCKET_SECONDS: dict[str, int] = {"raw": 0, "1m": 60, "5m": 300, "1h": 3600}


def _toUtcIso(value: datetime | None) -> str | None:
    """Render timestamps as ISO8601 UTC with a trailing Z (contract section 2)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# Timestamps are stored naive-UTC in SQLite; this restores the Z suffix on the wire.
UtcDateTime = Annotated[
    datetime,
    PlainSerializer(_toUtcIso, return_type=str | None, when_used="json"),
]


class CamelModel(BaseModel):
    """Serialise to camelCase, accept either camelCase or snake_case input."""

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        alias_generator=to_camel,
    )


class TelemetryOut(CamelModel):
    id: int
    device_id: str
    temperature_c: float | None = None
    humidity_pct: float | None = None
    light_lux: float | None = None
    water_ok: bool | None = None
    received_at: UtcDateTime


class TelemetryBucket(CamelModel):
    device_id: str
    bucket_start: UtcDateTime
    bucket: Literal["1m", "5m", "1h"]
    sample_count: int
    temperature_c: float | None = None
    humidity_pct: float | None = None
    light_lux: float | None = None
    water_ok: bool | None = None


class TelemetryHistoryResponse(CamelModel):
    """Envelope for GET /api/telemetry, identical for raw and bucketed data."""

    bucket: Bucket
    data: list[TelemetryOut] | list[TelemetryBucket]


class DeviceStateOut(CamelModel):
    device_id: str
    mode: ControlMode
    fan: bool
    mist: bool
    lamp: bool
    failsafe_active: bool
    online: bool
    last_seen_at: UtcDateTime | None = None
    last_command_id: str | None = None
    last_command_result: Literal["APPLIED", "REJECTED"] | None = None
    reason: str | None = None
    updated_at: UtcDateTime


class DeviceConfigOut(CamelModel):
    mode: ControlMode
    temp_on_c: float
    temp_off_c: float
    humidity_on_pct: float
    humidity_off_pct: float
    light_on_lux: float
    light_off_lux: float


class DeviceConfigRequest(DeviceConfigOut):
    """POST /api/config body with hysteresis validation (contract 3.7)."""

    @field_validator("mode", mode="before")
    @classmethod
    def _normaliseMode(cls, value: object) -> object:
        # Must run BEFORE the Literal check, otherwise "manual" is rejected
        # instead of being accepted case-insensitively.
        return value.strip().upper() if isinstance(value, str) else value

    def validateThresholds(self) -> None:
        if self.temp_on_c <= self.temp_off_c:
            raise ValueError("tempOnC phai lon hon tempOffC")
        if self.humidity_on_pct >= self.humidity_off_pct:
            raise ValueError("humidityOnPct phai nho hon humidityOffPct")
        if self.light_on_lux >= self.light_off_lux:
            raise ValueError("lightOnLux phai nho hon lightOffLux")

    def validateRanges(self) -> None:
        if not 0 <= self.humidity_on_pct <= 100 or not 0 <= self.humidity_off_pct <= 100:
            raise ValueError("humidity phai trong khoang 0-100")
        if self.light_on_lux < 0 or self.light_off_lux < 0:
            raise ValueError("lightLux phai >= 0")


class CommandRequest(CamelModel):
    device_id: str
    device: DeviceName
    on: bool


class CommandAccepted(CamelModel):
    command_id: str
    status: Literal["PENDING"] = "PENDING"


class CommandLogOut(CamelModel):
    command_id: str
    device_id: str
    device: DeviceName
    requested_on: bool
    status: CommandStatus
    reason: str | None = None
    requested_at: UtcDateTime
    completed_at: UtcDateTime | None = None


class CommandLogList(CamelModel):
    data: list[CommandLogOut]


class ConfigPublished(CamelModel):
    """202 body for POST /api/config - published, NOT applied (contract 3.7)."""

    status: Literal["PUBLISHED"] = "PUBLISHED"
    config: DeviceConfigOut


class AlertOut(CamelModel):
    id: int
    device_id: str
    code: AlertCode
    severity: AlertSeverity
    message: str
    active: bool
    started_at: UtcDateTime
    last_seen_at: UtcDateTime
    resolved_at: UtcDateTime | None = None


class AlertList(CamelModel):
    data: list[AlertOut]


class HealthOut(CamelModel):
    status: Literal["ok"] = "ok"
    mqtt_connected: bool
    db: Literal["ok", "error"]


# --- WebSocket envelopes (contract section 4) ---
# PENDING never appears on the WebSocket: it only exists in the REST 202 body
# and in GET /api/commands.


class CommandResult(CamelModel):
    command_id: str
    result: TerminalCommandResult
    reason: str | None = None
    was_late: bool = False


class WsTelemetryMessage(CamelModel):
    type: Literal["telemetry"] = "telemetry"
    data: TelemetryOut


class WsStateMessage(CamelModel):
    type: Literal["state"] = "state"
    data: DeviceStateOut


class WsCommandResultMessage(CamelModel):
    type: Literal["command_result"] = "command_result"
    data: CommandResult


class WsAlertMessage(CamelModel):
    type: Literal["alert"] = "alert"
    data: AlertOut
