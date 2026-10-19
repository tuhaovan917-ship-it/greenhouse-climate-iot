"""GET /api/health - liveness probe used by the Dashboard."""

from __future__ import annotations

from fastapi import APIRouter

from app.database import checkDatabase
from app.mqtt_client import mqttService
from app.schemas import HealthOut

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthOut, summary="Kiem tra Backend, MQTT va DB")
def getHealth() -> HealthOut:
    dbOk = checkDatabase()
    return HealthOut(mqtt_connected=mqttService.isConnected(), db="ok" if dbOk else "error")
