"""Configuration endpoints: read the desired config, publish a new one."""

from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.config import settings
from app.database import getSession
from app.models import DeviceConfig, utcNow
from app.mqtt_client import mqttService
from app.routers.deps import enforce_read, enforce_write
from app.schemas import (
    ConfigAckStatus,
    ConfigPublished,
    DeviceConfigOut,
    DeviceConfigRequest,
)
from app.services.state import stateService, upsertDeviceConfig
from app.services.config_ack import configAckService

router = APIRouter(prefix="/api", tags=["config"])

# Test values from mqtt-protocol v0.1 section 3.5, not agronomically optimal.
DEFAULT_CONFIG = DeviceConfigOut(
    mode="AUTO",
    temp_on_c=30.0,
    temp_off_c=28.0,
    humidity_on_pct=55.0,
    humidity_off_pct=65.0,
    light_on_lux=300.0,
    light_off_lux=700.0,
)


def _toMqttPayload(config: DeviceConfigOut, configId: str) -> dict:
    return {
        "configId": configId,
        "mode": config.mode,
        "tempOnC": config.temp_on_c,
        "tempOffC": config.temp_off_c,
        "humidityOnPct": config.humidity_on_pct,
        "humidityOffPct": config.humidity_off_pct,
        "lightOnLux": config.light_on_lux,
        "lightOffLux": config.light_off_lux,
    }


@router.get("/config", response_model=DeviceConfigOut, summary="Doc cau hinh mong muon hien tai", dependencies=[Depends(enforce_read)])
def getConfig(
    deviceId: str = Query(default=settings.device_id),
    session: Session = Depends(getSession),
) -> DeviceConfigOut:
    row = session.get(DeviceConfig, deviceId)
    if row is None:
        return DEFAULT_CONFIG
    return DeviceConfigOut.model_validate(row)


@router.get(
    "/config/status",
    response_model=ConfigAckStatus,
    summary="Doc trang thai ACK cua mot lan cap nhat cau hinh",
    dependencies=[Depends(enforce_read)],
)
def getConfigStatus(
    configId: str = Query(min_length=1, max_length=64),
) -> ConfigAckStatus:
    record = configAckService.get(configId)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Khong tim thay configId {configId}",
        )

    return ConfigAckStatus(
        config_id=record.config_id,
        device_id=record.device_id,
        status=record.result,
        reason=record.reason,
        was_late=record.was_late,
    )


@router.post(
    "/config",
    response_model=ConfigPublished,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Cap nhat cau hinh va publish xuong ESP32",
    dependencies=[Depends(enforce_write)],
)
def postConfig(
    payload: DeviceConfigRequest,
    deviceId: str = Query(default=settings.device_id),
    session: Session = Depends(getSession),
) -> ConfigPublished:
    """Return 202 after publication while the device ACK remains pending."""
    try:
        payload.validateThresholds()
        payload.validateRanges()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error

    if not stateService.onlineFlags().get(deviceId, False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Thiet bi {deviceId} dang offline, khong the cap nhat cau hinh",
        )

    row = upsertDeviceConfig(
        session,
        deviceId,
        {
            "mode": payload.mode,
            "temp_on_c": payload.temp_on_c,
            "temp_off_c": payload.temp_off_c,
            "humidity_on_pct": payload.humidity_on_pct,
            "humidity_off_pct": payload.humidity_off_pct,
            "light_on_lux": payload.light_on_lux,
            "light_off_lux": payload.light_off_lux,
            "updated_at": utcNow(),
        },
    )
    session.commit()
    configId = f"cfg-{uuid.uuid4().hex[:12]}"
    configAckService.registerPending(
        deviceId,
        configId,
    )
    if not mqttService.publishConfig(
        _toMqttPayload(payload, configId)
    ):
        configAckService.discard(configId)

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MQTT chua ket noi, cau hinh chua duoc publish",
        )

    configAckService.scheduleTimeout(configId)

    upsertDeviceConfig(session, deviceId, {"published_at": utcNow()})
    session.commit()

    return ConfigPublished(
        config_id=configId,
        config=DeviceConfigOut.model_validate(row),
    )
