"""Local HTTP/WebSocket server that feeds the OBS Browser Source overlay."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web


class OverlayServer:
    def __init__(self, overlay_dir: Path, port: int = 8765):
        self._dir = overlay_dir
        self._requested_port = port
        self._port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: set[web.WebSocketResponse] = set()
        self._runner: web.AppRunner | None = None
        self._thread: threading.Thread | None = None
        self._caption: dict[str, Any] | None = None
        self._config: dict[str, Any] = {}

    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="cyctitles-overlay")
        self._thread.start()

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._start())
            self._loop.run_forever()
        finally:
            self._loop.close()

    async def _start(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._index)
        app.router.add_get("/ws", self._ws)
        app.router.add_get("/health", self._health)
        app.router.add_static("/static/", self._dir)

        self._runner = web.AppRunner(app)
        await self._runner.setup()

        last_error: Exception | None = None
        for offset in range(0, 20):
            candidate = self._requested_port + offset
            site = web.TCPSite(self._runner, "127.0.0.1", candidate)
            try:
                await site.start()
                self._port = candidate
                return
            except OSError as exc:
                last_error = exc
        raise RuntimeError(f"Could not bind overlay server: {last_error}")

    def stop(self) -> None:
        if self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
            except Exception:
                self._loop.call_soon_threadsafe(self._loop.stop)

    async def _shutdown(self) -> None:
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()
        if self._runner is not None:
            try:
                await self._runner.cleanup()
            except Exception:
                pass
        self._loop.stop()  # type: ignore[union-attr]

    # -- routes --------------------------------------------------------------
    async def _index(self, request: web.Request) -> web.StreamResponse:
        return web.FileResponse(self._dir / "index.html")

    async def _health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "clients": len(self._clients)})

    async def _ws(self, request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        self._clients.add(ws)
        await ws.send_json(
            {"type": "state", "caption": self._caption, "config": self._config}
        )
        try:
            async for msg in ws:
                if msg.type == WSMsgType.ERROR:
                    break
        finally:
            self._clients.discard(ws)
        return ws

    # -- broadcasting --------------------------------------------------------
    def set_caption(self, caption: dict[str, Any] | None) -> None:
        self._caption = caption
        if caption is None:
            self._broadcast({"type": "clear"})
        else:
            self._broadcast({"type": "caption", **caption})

    def set_config(self, config: dict[str, Any]) -> None:
        self._config = dict(config)
        self._broadcast({"type": "config", "config": self._config})

    def _broadcast(self, payload: dict[str, Any]) -> None:
        if not self._loop:
            return
        asyncio.run_coroutine_threadsafe(self._send_all(payload), self._loop)

    async def _send_all(self, payload: dict[str, Any]) -> None:
        dead: list[web.WebSocketResponse] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)
