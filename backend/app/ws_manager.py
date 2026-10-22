"""WebSocket connection registry and broadcast helper (contract section 4)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Tracks live Dashboard sockets per device and pushes JSON messages."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, deviceId: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[deviceId].add(websocket)
        logger.info("dashboard connected: device=%s total=%s", deviceId, self.count())

    async def disconnect(self, deviceId: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(deviceId)
            if sockets:
                sockets.discard(websocket)
                if not sockets:
                    self._connections.pop(deviceId, None)

    async def send(self, deviceId: str, websocket: WebSocket, message: dict) -> None:
        await websocket.send_text(json.dumps(message, ensure_ascii=False))

    async def broadcast(self, deviceId: str, message: dict) -> None:
        """Push to every socket of one device; drop dead sockets silently."""
        async with self._lock:
            targets = list(self._connections.get(deviceId, set()))

        dead: list[WebSocket] = []
        for socket in targets:
            try:
                await socket.send_text(json.dumps(message, ensure_ascii=False))
            except Exception:  # noqa: BLE001 - client vanished, cleanup below
                dead.append(socket)

        if dead:
            async with self._lock:
                sockets = self._connections.get(deviceId)
                if sockets:
                    sockets.difference_update(dead)
                    if not sockets:
                        self._connections.pop(deviceId, None)

    def count(self) -> int:
        return sum(len(sockets) for sockets in self._connections.values())


wsManager = WebSocketManager()
