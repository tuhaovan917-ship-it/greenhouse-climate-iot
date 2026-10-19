"""Telemetry endpoints: history (raw or bucketed) and latest reading."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.config import settings
from app.database import getSession
from app.routers.deps import badRequest
from app.schemas import TelemetryHistoryResponse, TelemetryOut
from app.services.telemetry import parseQueryTime, telemetryService

router = APIRouter(prefix="/api", tags=["telemetry"])

BUCKET_VALUES = ["raw", "1m", "5m", "1h"]


@router.get(
    "/telemetry",
    response_model=TelemetryHistoryResponse,
    summary="Lich su cam bien, ho tro bucket raw|1m|5m|1h",
)
def getTelemetryHistory(
    deviceId: str = Query(default=settings.device_id),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    bucket: str = Query(default="raw"),
    session: Session = Depends(getSession),
) -> TelemetryHistoryResponse:
    if bucket not in BUCKET_VALUES:
        raise badRequest(f"bucket phai mot trong {BUCKET_VALUES}")

    try:
        start = parseQueryTime(from_, "from")
        end = parseQueryTime(to, "to")
    except ValueError as error:
        raise badRequest(str(error)) from error

    if start is not None and end is not None and start > end:
        raise badRequest("from phai nho hon to")

    return telemetryService.history(
        session=session,
        deviceId=deviceId,
        start=start,
        end=end,
        limit=limit,
        desc=order == "desc",
        bucket=bucket,
    )


@router.get(
    "/telemetry/latest",
    response_model=TelemetryOut,
    summary="Ban tin cam bien moi nhat",
)
def getLatestTelemetry(
    deviceId: str = Query(default=settings.device_id),
    session: Session = Depends(getSession),
) -> TelemetryOut:
    from sqlmodel import select

    from app.models import TelemetryReading

    statement = (
        select(TelemetryReading)
        .where(TelemetryReading.device_id == deviceId)
        .order_by(TelemetryReading.received_at.desc(), TelemetryReading.id.desc())
        .limit(1)
    )
    row = session.exec(statement).first()
    if row is None:
        raise badRequest("Chua co du lieu cam bien cho thiet bi nay")
    return TelemetryOut.model_validate(row)
