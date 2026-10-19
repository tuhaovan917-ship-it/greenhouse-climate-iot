"""WebSocket endpoint: one socket per Dashboard, push-only."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import settings
from app.ws_manager import wsManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Client -> server keepalive; the Dashboard pings so dead sockets drop fast.
PING_INTERVAL_S = 20


@router.websocket("/ws")
async def websocketEndpoint(websocket: WebSocket, deviceId: str = Query(default=settings.device_id)) -> None:
    await wsManager.connect(deviceId, websocket)
    try:
        while True:
            # Inbound frames are only keepalives; all real traffic is MQTT-driven.
            await asyncio.wait_for(websocket.receive_text(), timeout=PING_INTERVAL_S)
    except WebSocketDisconnect:
        logger.info("dashboard disconnected: device=%s", deviceId)
    except (asyncio.TimeoutError, json.JSONDecodeError):
        logger.info("websocket timeout/garbage, closing: device=%s", deviceId)
    except RuntimeError:
        logger.info("websocket closed during shutdown: device=%s", deviceId)
    finally:
        await wsManager.disconnect(deviceId, websocket)
