"""Device state endpoint: the real state reported by the ESP32."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.config import settings
from app.database import getSession
from app.models import DeviceState
from app.schemas import DeviceStateOut
from app.services.state import stateService

router = APIRouter(prefix="/api", tags=["state"])


@router.get("/state", response_model=DeviceStateOut, summary="Trang thai thuc te cua thiet bi")
def getState(
    deviceId: str = Query(default=settings.device_id),
    session: Session = Depends(getSession),
) -> DeviceStateOut:
    state = session.get(DeviceState, deviceId)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thiet bi chua gui state, hay kiem tra online/offline",
        )

    # Keep the online flag honest even before the monitor task ticks.
    flags = stateService.onlineFlags()
    if deviceId in flags:
        state.online = flags[deviceId]

    return DeviceStateOut.model_validate(state)
