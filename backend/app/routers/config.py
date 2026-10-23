"""Configuration endpoints: read the desired config, publish a new one."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.config import settings
from app.database import getSession
from app.models import DeviceConfig, utcNow
from app.mqtt_client import mqttService
from app.routers.deps import enforce_read, enforce_write
from app.schemas import ConfigPublished, DeviceConfigOut, DeviceConfigRequest
from app.services.state import stateService, upsertDeviceConfig

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


def _toMqttPayload(config: DeviceConfigOut) -> dict:
    """Payload for topic `greenhouse/01/config` (mqtt-protocol v0.1)."""
    return {
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
    """Contract 3.7: 202 PUBLISHED only means the Backend published the config.

    The firmware has no `configId` acknowledgement yet, so this endpoint must
    never claim the ESP32 applied the thresholds.
    """
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

    if not mqttService.publishConfig(_toMqttPayload(payload)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MQTT chua ket noi, cau hinh chua duoc publish",
        )

    upsertDeviceConfig(session, deviceId, {"published_at": utcNow()})
    session.commit()

    return ConfigPublished(config=DeviceConfigOut.model_validate(row))
