"""WebSocket endpoint: one socket per Dashboard, push-only.

Heartbeat (contract 4)
-----------------------
The server keeps the socket alive on its own:

- every `HEARTBEAT_S` seconds the server sends an application-level ping
  `{"type": "ping"}`; the Dashboard may ignore it,
- the socket is NOT closed when the Dashboard stays silent, so a Dashboard that
  only listens (no ping, no other message) keeps receiving realtime data,
- a dead socket is detected when a send fails, then it is cleaned up.

Browsers cannot send WebSocket ping frames from JavaScript, so requiring a
client-side ping would mean inventing an extra protocol for the Dashboard.
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.config import settings
from app.ws_manager import wsManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# How often the server pings the Dashboard.
HEARTBEAT_S = 20


@router.websocket("/ws")
async def websocketEndpoint(websocket: WebSocket, deviceId: str = Query(default=settings.device_id)) -> None:
    await wsManager.connect(deviceId, websocket)
    heartbeat = asyncio.create_task(_heartbeat(deviceId, websocket))
    try:
        while True:
            # Inbound frames are optional (keepalive text or nothing at all).
            message = await websocket.receive_text()
            logger.debug("ws frame from %s: %r", deviceId, message[:80])
    except WebSocketDisconnect:
        logger.info("dashboard disconnected: device=%s", deviceId)
    except (json.JSONDecodeError, ValueError):
        logger.info("ws invalid frame, closing: device=%s", deviceId)
    except RuntimeError:
        logger.info("ws closed during shutdown: device=%s", deviceId)
    finally:
        heartbeat.cancel()
        await wsManager.disconnect(deviceId, websocket)


async def _heartbeat(deviceId: str, websocket: WebSocket) -> None:
    """Ping the Dashboard so both sides notice a dead connection."""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            await wsManager.send(deviceId, websocket, {"type": "ping"})
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - dead socket, the read loop will notice
        logger.debug("ws heartbeat stopped for device=%s", deviceId)
