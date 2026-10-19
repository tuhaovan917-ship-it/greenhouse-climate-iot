"""Device state endpoint: the real state reported by the ESP32."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.config import settings
from app.database import getSession
from app.models import DeviceState
from app.schemas import DeviceStateOut
from app.services.state import stateService

router = APIRouter(prefix="/api", tags=["state"])


def _emptyState(deviceId: str) -> DeviceStateOut:
    """Safe default for a device that has not published its state yet.

    The Dashboard loads several endpoints in parallel; returning an error here
    would break the whole page on a fresh start. `online: false` already tells
    the user the device is not connected.
    """
    return DeviceStateOut(
        device_id=deviceId,
        mode="AUTO",
        fan=False,
        mist=False,
        lamp=False,
        failsafe_active=False,
        online=False,
        last_seen_at=None,
        last_command_id=None,
        last_command_result=None,
        reason=None,
        updated_at=None,
    )


@router.get("/state", response_model=DeviceStateOut, summary="Trang thai thuc te cua thiet bi")
def getState(
    deviceId: str = Query(default=settings.device_id),
    session: Session = Depends(getSession),
) -> DeviceStateOut:
    state = session.get(DeviceState, deviceId)
    if state is None:
        return _emptyState(deviceId)

    # Keep the online flag honest even before the monitor task ticks.
    flags = stateService.onlineFlags()
    if deviceId in flags:
        state.online = flags[deviceId]

    return DeviceStateOut.model_validate(state)
