"""Verwaltungsdienst des Add-ons: liefert Oberfläche und API.

Läuft nur auf 127.0.0.1:8100 und ist ausschließlich über nginx erreichbar
(Ingress-Port 8099, siehe docs/architektur.md).
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from aiohttp import web

import health
from display_time import format_berlin

_STATIC_DIR = Path(__file__).parent / "static"
_LISTEN_HOST = "127.0.0.1"
_LISTEN_PORT = 8100

_LOG_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}

log = logging.getLogger("skytech")


class AdminService:
    """HTTP-Routen der Verwaltungsoberfläche."""

    def __init__(self, ingress_entry: str, version: str) -> None:
        self._ingress_entry = ingress_entry
        self._version = version
        self._session: aiohttp.ClientSession | None = None

    async def _on_startup(self, _app: web.Application) -> None:
        self._session = aiohttp.ClientSession()

    async def _on_cleanup(self, _app: web.Application) -> None:
        if self._session is not None:
            await self._session.close()

    async def handle_index(self, _request: web.Request) -> web.StreamResponse:
        index = _STATIC_DIR / "index.html"
        if not index.exists():
            return web.Response(status=503, text="Oberfläche nicht gebaut (cd web && npm run build).")
        return web.FileResponse(index)

    async def handle_status(self, _request: web.Request) -> web.Response:
        session = self._session
        if session is None:
            return web.json_response({"error": "Dienst startet noch."}, status=503)
        services = await health.collect([
            health.probe_database,
            lambda: health.probe_grafana(session, self._ingress_entry),
        ])
        now = datetime.now(timezone.utc)
        return web.json_response({
            "version": self._version,
            "services": [service.to_json() for service in services],
            "checked_at": format_berlin(now),
            "checked_at_iso": now.isoformat(),
        })

    def build_app(self) -> web.Application:
        app = web.Application()
        app.on_startup.append(self._on_startup)
        app.on_cleanup.append(self._on_cleanup)
        app.router.add_get("/", self.handle_index)
        app.router.add_get("/index.html", self.handle_index)
        app.router.add_get("/api/status", self.handle_status)
        assets = _STATIC_DIR / "assets"
        if assets.is_dir():
            app.router.add_static("/assets/", assets, name="assets")
        return app


async def _run() -> None:
    service = AdminService(
        ingress_entry=os.environ.get("SKYTECH_INGRESS_ENTRY", ""),
        version=os.environ.get("SKYTECH_VERSION", "dev"),
    )
    runner = web.AppRunner(service.build_app(), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, _LISTEN_HOST, _LISTEN_PORT).start()
    log.info("Verwaltungsdienst hört auf %s:%s", _LISTEN_HOST, _LISTEN_PORT)
    await asyncio.Event().wait()


def main() -> None:
    level = _LOG_LEVELS.get(os.environ.get("SKYTECH_LOG_LEVEL", "info"), logging.INFO)
    logging.basicConfig(level=level, format="[app] %(levelname)s %(name)s: %(message)s")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
