"""In-process WebSocket connection manager for real-time dashboard updates."""
from __future__ import annotations

import asyncio

from fastapi import WebSocket

from app.core.logging_config import get_logger

log = get_logger("ws")


class WSManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        if not self._clients:
            return
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
        if dead:
            log.debug("dropped %s dead websocket client(s)", len(dead))


manager = WSManager()
