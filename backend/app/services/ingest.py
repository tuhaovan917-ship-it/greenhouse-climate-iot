"""MQTT message ingestion: persist, derive alerts, push to WebSocket.

Each inbound MQTT message runs inside a short transaction (database/README.md
v0.2 section 7): write first, commit, then broadcast so the Dashboard never
receives data that was not stored.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi.concurrency import run_in_threadpool

from app.database import sessionScope
from app.models import (
    COMMAND_APPLIED,
    COMMAND_REJECTED,
    CONTROL_MODES,
    Alert,
    DeviceState,
    TelemetryReading,
    utcNow,
)
from app.schemas import (
    AlertOut,
    DeviceStateOut,
    TelemetryOut,
    WsAlertMessage,
    WsCommandResultMessage,
    WsStateMessage,
    WsTelemetryMessage,
)
from app.services.alerts import NO_WATER, OFFLINE, SENSOR_FAULT, alertService
from app.services.commands import commandService
from app.services.state import stateService, upsertDeviceState
from app.services.telemetry import SENSOR_RANGES, telemetryService
from app.ws_manager import wsManager

logger = logging.getLogger(__name__)


async def handleTelemetry(deviceId: str, payload: dict) -> None:
    """Topic `telemetry`: append one reading, refresh alerts, push WS."""

    def _work() -> tuple[TelemetryOut, list[AlertOut]]:
        with sessionScope() as session:
            reading = TelemetryReading(
                device_id=deviceId,
                temperature_c=_asOptionalFloat(payload.get("temperatureC"), "temperatureC", deviceId),
                humidity_pct=_asOptionalFloat(payload.get("humidityPct"), "humidityPct", deviceId),
                light_lux=_asOptionalFloat(payload.get("lightLux"), "lightLux", deviceId),
                water_ok=_asOptionalBool(payload.get("waterOk")),
                received_at=utcNow(),
            )
            session.add(reading)
            session.flush()

            alerts = _evaluateSensorAlerts(session, deviceId, reading)
            session.flush()
            return (
                TelemetryOut.model_validate(reading),
                [AlertOut.model_validate(alert) for alert in alerts if alert is not None],
            )

    reading_out, alert_outs = await run_in_threadpool(_work)

    telemetryService.remember(
        TelemetryReading(
            id=reading_out.id,
            device_id=reading_out.device_id,
            temperature_c=reading_out.temperature_c,
            humidity_pct=reading_out.humidity_pct,
            light_lux=reading_out.light_lux,
            water_ok=reading_out.water_ok,
            received_at=reading_out.received_at,
        )
    )
    stateService.markMessageReceived(deviceId)
    await _broadcast(deviceId, WsTelemetryMessage(data=reading_out))
    for alert_out in alert_outs:
        await _broadcast(deviceId, WsAlertMessage(data=alert_out))


async def handleState(deviceId: str, payload: dict) -> None:
    """Topic `state`: upsert real device state and close the pending command."""

    def _work() -> tuple[DeviceStateOut, list[AlertOut], list[tuple[str, bool, str, str | None]]]:
        with sessionScope() as session:
            current = session.get(DeviceState, deviceId)
            mode = str(payload.get("mode") or (current.mode if current else "AUTO")).upper()
            if mode not in CONTROL_MODES:
                logger.warning("ignoring unknown mode %r from %s", mode, deviceId)
                mode = current.mode if current else "AUTO"

            now = utcNow()
            values: dict = {
                "mode": mode,
                "fan": bool(payload.get("fan", current.fan if current else False)),
                "mist": bool(payload.get("mist", current.mist if current else False)),
                "lamp": bool(payload.get("lamp", current.lamp if current else False)),
                "failsafe_active": bool(
                    payload.get("failsafeActive", current.failsafe_active if current else False)
                ),
                "online": True,
                "last_seen_at": now,
                "updated_at": now,
            }

            applied: list[tuple[str, bool, str, str | None]] = []
            commandId = payload.get("lastCommandId")
            result = payload.get("lastCommandResult")
            reason = payload.get("reason")
            if commandId and result in (COMMAND_APPLIED, COMMAND_REJECTED):
                # Mirror the real result on the state row even when the command
                # is unknown to this Backend instance (restart, or a command
                # issued elsewhere) so the Dashboard still sees the truth.
                values["last_command_id"] = str(commandId)
                values["last_command_result"] = str(result)
                # The reason belongs to one command only:
                # - a NEW commandId supersedes the previous explanation, so a
                #   successful command clears the old failure reason;
                # - the same commandId is a periodic republish, which usually
                #   omits the reason, and then the known reason is kept.
                storedCommandId = current.last_command_id if current is not None else None
                isNewCommand = storedCommandId != str(commandId)
                if reason is not None or isNewCommand or current is None:
                    values["reason"] = reason

            state = upsertDeviceState(session, deviceId, values)

            if commandId and result in (COMMAND_APPLIED, COMMAND_REJECTED):
                outcome = commandService.applyResult(
                    session, str(commandId), str(result), reason
                )
                if outcome.changed and outcome.log is not None:
                    applied.append((str(commandId), outcome.wasLate, str(result), reason))

            alerts = _evaluateStateAlerts(session, deviceId, state)
            session.flush()
            return (
                DeviceStateOut.model_validate(state),
                [AlertOut.model_validate(alert) for alert in alerts if alert is not None],
                applied,
            )

    state_out, alert_outs, applied = await run_in_threadpool(_work)

    for commandId, _wasLate, result, reason in applied:
        commandService.cancelTimeout(commandId)
        stateService.recordCommandResult(deviceId, commandId, result, reason)

    stateService.markMessageReceived(deviceId)
    stateService.markOnline(deviceId, True)

    await _broadcast(deviceId, WsStateMessage(data=state_out))
    for alert_out in alert_outs:
        await _broadcast(deviceId, WsAlertMessage(data=alert_out))
    for commandId, wasLate, result, reason in applied:
        await _broadcast(
            deviceId,
            WsCommandResultMessage(
                data={
                    "command_id": commandId,
                    "result": result,
                    "reason": reason,
                    "was_late": wasLate,
                }
            ),
        )


async def handleStatus(deviceId: str, payload: dict) -> None:
    """Topic `status` (also the LWT channel): flip the online flag."""

    online = bool(payload.get("online", True))
    changed = stateService.markOnline(deviceId, online)

    def _work() -> tuple[DeviceStateOut, AlertOut | None]:
        with sessionScope() as session:
            now = utcNow()
            values: dict = {"online": online, "updated_at": now}
            if online:
                values["last_seen_at"] = now

            state = upsertDeviceState(session, deviceId, values)

            touched = (
                alertService.clearIfHealthy(session, deviceId, OFFLINE)
                if online
                else alertService.openOrRefresh(session, deviceId, OFFLINE)
            )
            session.flush()
            alert_out = AlertOut.model_validate(touched) if touched is not None else None
            return DeviceStateOut.model_validate(state), alert_out

    state_out, alert_out = await run_in_threadpool(_work)

    if changed or alert_out is not None:
        await _broadcast(deviceId, WsStateMessage(data=state_out))
        if alert_out is not None:
            await _broadcast(deviceId, WsAlertMessage(data=alert_out))


async def monitorOfflineDevices() -> None:
    """Background task: flip devices to offline after DEVICE_TIMEOUT_S."""
    while True:
        await asyncio.sleep(1)
        for runtime in stateService.staleDevices():
            await handleStatus(runtime.device_id, {"online": False})


# --- helpers ---


async def _broadcast(deviceId: str, message) -> None:  # noqa: ANN001
    await wsManager.broadcast(deviceId, message.model_dump(mode="json", by_alias=True))


# --- alert rules (SCHEMA.md section 8) ---


def _evaluateSensorAlerts(session, deviceId: str, reading: TelemetryReading) -> list[Alert]:  # noqa: ANN001
    """waterOk=False -> NO_WATER; any NULL sensor -> SENSOR_FAULT."""
    touched: list[Alert] = []

    if reading.water_ok is False:
        touched.append(alertService.openOrRefresh(session, deviceId, NO_WATER))
    elif reading.water_ok is True:
        resolved = alertService.clearIfHealthy(session, deviceId, NO_WATER)
        if resolved is not None:
            touched.append(resolved)

    sensorNull = any(
        value is None
        for value in (reading.temperature_c, reading.humidity_pct, reading.light_lux)
    ) or reading.water_ok is None

    if sensorNull:
        touched.append(alertService.openOrRefresh(session, deviceId, SENSOR_FAULT))
    else:
        resolved = alertService.clearIfHealthy(session, deviceId, SENSOR_FAULT)
        if resolved is not None:
            touched.append(resolved)

    return [item for item in touched if item is not None]


def _evaluateStateAlerts(session, deviceId: str, state: DeviceState) -> list[Alert]:  # noqa: ANN001
    """A device-side FAILSAFE also implies NO_WATER."""
    if state.failsafe_active:
        return [alertService.openOrRefresh(session, deviceId, NO_WATER)]
    return []


def _asOptionalFloat(value: object, field: str = "", deviceId: str = "") -> float | None:
    """Parse one sensor value, returning None when it is unusable.

    A missing value, a non-number, NaN/Infinity or a value outside the physical
    range all become NULL, which is what the contract expects for a failed read.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        logger.warning("non-numeric %s from %s: %r", field, deviceId, value)
        return None

    # JSON must never carry NaN or Infinity (mqtt-protocol v0.1 section 3.1).
    if number != number or number in (float("inf"), float("-inf")):
        logger.warning("NaN/Inf %s from %s", field, deviceId)
        return None

    low, high = SENSOR_RANGES.get(field, (None, None))
    if (low is not None and number < low) or (high is not None and number > high):
        logger.warning("out-of-range %s from %s: %s", field, deviceId, number)
        return None
    return number


def _asOptionalBool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None
