"""Command endpoints: send a MANUAL command and read the command history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.config import settings
from app.database import getSession
from app.models import (
    COMMAND_PENDING,
    COMMAND_TIMEOUT,
    REASON_MQTT_NOT_CONNECTED,
)
from app.mqtt_client import mqttService
from app.routers.deps import enforce_read, enforce_write
from app.schemas import CommandAccepted, CommandLogList, CommandLogOut, CommandRequest
from app.services.commands import commandService
from app.services.state import stateService

router = APIRouter(prefix="/api", tags=["commands"])


@router.post(
    "/commands",
    response_model=CommandAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Gui lenh MANUAL xuong ESP32 qua MQTT",
    dependencies=[Depends(enforce_write)],
)
def postCommand(payload: CommandRequest, session: Session = Depends(getSession)) -> CommandAccepted:
    """Contract 3.5: store PENDING first, then publish, then arm the timeout.

    The 202 response is honest - the Dashboard waits for the real
    state/command_result coming back from the ESP32 instead of assuming success.
    """
    if not stateService.onlineFlags().get(payload.device_id, False):
        # Reject before writing anything so the audit trail stays clean.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Thiet bi {payload.device_id} dang offline, khong the gui lenh",
        )

    log = commandService.createPending(session, payload.device_id, payload.device, payload.on)
    session.commit()
    assert log.status == COMMAND_PENDING

    if not mqttService.publishCommand(log.command_id, payload.device, payload.on):
        log.status = COMMAND_TIMEOUT
        log.reason = REASON_MQTT_NOT_CONNECTED
        session.add(log)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MQTT chua ket noi, khong the gui lenh",
        )

    commandService.scheduleTimeout(log.command_id)
    return CommandAccepted(command_id=log.command_id)


@router.get("/commands", response_model=CommandLogList, summary="Lich su lenh va ket qua", dependencies=[Depends(enforce_read)])
def getCommands(
    deviceId: str = Query(default=settings.device_id),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(getSession),
) -> CommandLogList:
    logs = commandService.listRecent(session, deviceId, limit)
    return CommandLogList(data=[CommandLogOut.model_validate(log) for log in logs])
