"""FastAPI application entry point.

Startup order: bind the asyncio loop to the MQTT service, open the MQTT
connection (non-blocking, reconnects on its own), start the offline monitor,
then start serving HTTP/WS. The API stays usable even when the broker is down -
`GET /api/health` reports `mqttConnected: false` and the Dashboard shows the
device as offline.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import ensureTablesIfAllowed
from app.mqtt_client import mqttService
from app.routers import auth as authRouter
from app.routers import alerts as alertsRouter
from app.routers import commands as commandsRouter
from app.routers import config as configRouter
from app.routers import health as healthRouter
from app.routers import state as stateRouter
from app.routers import telemetry as telemetryRouter
from app.routers import ws as wsRouter
from app.services.commands import commandService
from app.services.ingest import (
    handleState,
    handleStatus,
    handleTelemetry,
    monitorOfflineDevices,
)
from app.services.config_ack import configAckService

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("app")

DESCRIPTION = """
Backend for greenhouse climate control.

* MQTT: subscribes to `greenhouse/01/telemetry|state|status|config/ack`; publishes `.../command|config`.
* REST: `/api/health`, `/api/telemetry`, `/api/telemetry/latest`, `/api/state`,
  `/api/commands`, `/api/config`, `/api/config/status`, `/api/alerts`.
* WebSocket: `/ws` pushes `telemetry`, `state`, `command_result`, `config_result`, and `alert`.

Contracts: `docs/api-contract.md` and `docs/config-ack-a8.md`.
"""


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Dev/demo convenience only; the shared schema comes from `alembic upgrade head`.
    ensureTablesIfAllowed()

    loop = asyncio.get_running_loop()
    mqttService.bindLoop(loop)
    commandService.bindLoop(loop)
    configAckService.bindLoop(loop)
    mqttService.setHandlers(
        handleTelemetry,
        handleState,
        handleStatus,
        configAckService.handleAck,
    )
    mqttService.start()

    monitor = asyncio.create_task(monitorOfflineDevices(), name="offline-monitor")
    logger.info("Backend ready: device=%s db=%s", settings.device_id, settings.database_url)

    try:
        yield
    finally:
        monitor.cancel()
        mqttService.stop()
        logger.info("Backend stopped")


app = FastAPI(
    title="Greenhouse Climate IoT Backend",
    description=DESCRIPTION,
    version="0.2.2",
    lifespan=lifespan,
)

# The Dashboard runs on the Vite dev server (localhost:5173).
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(authRouter.router)
app.include_router(healthRouter.router)
app.include_router(telemetryRouter.router)
app.include_router(stateRouter.router)
app.include_router(commandsRouter.router)
app.include_router(configRouter.router)
app.include_router(alertsRouter.router)
app.include_router(wsRouter.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": "greenhouse-climate-iot backend",
        "docs": "/docs",
        "contract": "docs/api-contract.md v0.2.2",
    }
