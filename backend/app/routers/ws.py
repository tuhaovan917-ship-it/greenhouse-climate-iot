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

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from app.config import settings
from app.database import engine
from app.services.auth import current_session
from app.ws_manager import wsManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# How often the server pings the Dashboard.
HEARTBEAT_S = 20
# A4.3: close a WebSocket shortly after logout/expiry/disable.
ACCESS_RECHECK_S = 1.0


def _valid_ws_session(websocket: WebSocket) -> bool:
    # Validate browser session with a fresh, short-lived DB transaction.
    # Session must be active and a valid read role; do not log raw tokens.
    try:
        with Session(engine) as db:
            user, _, _ = current_session(websocket, db)
            return user.role in {"viewer", "operator", "admin"}
    except HTTPException:
        return False
    except Exception:
        logger.exception("WebSocket session validation failed")
        return False  # Fail closed during transient DB failures.


async def _watch_session(websocket: WebSocket) -> None:
    # Enforce expiry, account disable and logout during an open socket.
    while True:
        await asyncio.sleep(ACCESS_RECHECK_S)
        if not _valid_ws_session(websocket):
            await websocket.close(code=1008)
            return


async def _read_socket(deviceId: str, websocket: WebSocket) -> None:
    try:
        while True:
            message = await websocket.receive_text()
            logger.debug("ws frame from %s: %r", deviceId, message[:80])
    except WebSocketDisconnect:
        logger.info("dashboard disconnected: device=%s", deviceId)
    except (json.JSONDecodeError, ValueError):
        logger.info("ws invalid frame, closing: device=%s", deviceId)
    except RuntimeError:
        logger.info("ws closed during shutdown: device=%s", deviceId)


@router.websocket("/ws")
async def websocketEndpoint(websocket: WebSocket, deviceId: str = Query(default=settings.device_id)) -> None:
    # The legacy Wokwi Dashboard keeps working until AUTH_ENFORCEMENT_ENABLED=1.
    strict = settings.auth_enforcement_enabled
    if strict:
        # Browsers automatically supply an Origin header during WS handshake.
        # Reject absent and untrusted Origins, not merely an unexpected value.
        if websocket.headers.get("origin") not in settings.cors_origins:
            await websocket.close(code=1008)
            return
        if not _valid_ws_session(websocket):
            await websocket.close(code=1008)
            return

    await wsManager.connect(deviceId, websocket)
    heartbeat = asyncio.create_task(_heartbeat(deviceId, websocket))
    reader = asyncio.create_task(_read_socket(deviceId, websocket))
    watcher = asyncio.create_task(_watch_session(websocket)) if strict else None
    tasks = [heartbeat, reader] + ([watcher] if watcher is not None else [])

    try:
        if watcher is not None:
            # If the session is revoked, watcher closes socket even when the
            # Dashboard sends no frames at all.
            await asyncio.wait({reader, watcher}, return_when=asyncio.FIRST_COMPLETED)
        else:
            await reader
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
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
