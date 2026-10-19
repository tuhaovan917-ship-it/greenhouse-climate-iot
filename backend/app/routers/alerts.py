"""Alert endpoints: history plus the current active alerts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.config import settings
from app.database import getSession
from app.models import ALERT_CODES, Alert
from app.routers.deps import badRequest
from app.schemas import AlertList, AlertOut
from app.services.telemetry import parseQueryTime

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get(
    "/alerts",
    response_model=AlertList,
    summary="Lich su va canh bao dang active",
)
def getAlerts(
    deviceId: str = Query(default=settings.device_id),
    active: bool | None = Query(default=None),
    code: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(getSession),
) -> AlertList:
    """REST exists so the Dashboard can restore history after a reload."""
    if code is not None and code not in ALERT_CODES:
        raise badRequest(f"code phai mot trong {list(ALERT_CODES)}")

    try:
        start = parseQueryTime(from_, "from")
        end = parseQueryTime(to, "to")
    except ValueError as error:
        raise badRequest(str(error)) from error

    statement = select(Alert).where(Alert.device_id == deviceId)
    if active is not None:
        statement = statement.where(Alert.active == active)  # type: ignore[attr-defined]
    if code is not None:
        statement = statement.where(Alert.code == code)
    if start is not None:
        statement = statement.where(Alert.started_at >= start)
    if end is not None:
        statement = statement.where(Alert.started_at < end)
    statement = statement.order_by(Alert.started_at.desc(), Alert.id.desc()).limit(limit)

    rows = session.exec(statement).all()
    return AlertList(data=[AlertOut.model_validate(row) for row in rows])
