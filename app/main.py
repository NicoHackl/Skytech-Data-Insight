"""Verwaltungsdienst des Add-ons: Oberfläche, API, Migrationen und Collector.

Läuft nur auf 127.0.0.1:8100 und ist ausschließlich über nginx erreichbar
(Ingress-Port 8099, siehe docs/architektur.md).
"""

import asyncio
import json
import logging
import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp
import asyncpg
from aiohttp import web

import backup
import database
import health
import migration_runner
import sensor_service
from collector import Collector
from display_time import BERLIN, format_berlin
from ha_client import HAClient, connection_settings
from suggestions import suggest
from values import is_numeric_attribute

_STATIC_DIR = Path(__file__).parent / "static"
_LISTEN_HOST = "127.0.0.1"
_LISTEN_PORT = 8100
_DB_RETRY_DELAYS_S = (1, 2, 3, 5, 5, 10)

_LOG_LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}

log = logging.getLogger("skytech")


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def json_response(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, dumps=lambda obj: json.dumps(obj, default=_json_default))


def error_response(message: str, status: int, field_errors: dict[str, str] | None = None) -> web.Response:
    body: dict[str, Any] = {"error": message}
    if field_errors:
        body["field_errors"] = field_errors
    return json_response(body, status=status)


def request_user(request: web.Request) -> str | None:
    """HA-Benutzer aus den Ingress-Headern des Supervisors (für das Protokoll)."""
    return request.headers.get("X-Remote-User-Display-Name") or request.headers.get("X-Remote-User-Name")


class AdminService:
    """Startablauf und HTTP-Routen."""

    def __init__(self, ingress_entry: str, version: str, start_backend: bool = True) -> None:
        self._ingress_entry = ingress_entry
        self._version = version
        self._start_backend = start_backend
        self._session: aiohttp.ClientSession | None = None
        self.app_pool: asyncpg.Pool | None = None
        self.collector_pool: asyncpg.Pool | None = None
        self.collector: Collector | None = None
        self.ha: HAClient | None = None
        self.startup_error: str | None = None
        self._tasks: list[asyncio.Task] = []
        self.restorer = backup.Restorer()

    # ------------------------------------------------------------------
    # Lebenszyklus
    # ------------------------------------------------------------------

    async def _on_startup(self, _app: web.Application) -> None:
        self._session = aiohttp.ClientSession()
        if self._start_backend:
            self._tasks.append(asyncio.create_task(self._start_backend_services(), name="backend-start"))

    async def _on_cleanup(self, _app: web.Application) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self.collector is not None:
            await self.collector.stop()
        for pool in (self.collector_pool, self.app_pool):
            if pool is not None:
                await pool.close()
        if self._session is not None:
            await self._session.close()

    async def _connect_pools(self) -> None:
        for attempt, delay in enumerate((*_DB_RETRY_DELAYS_S, None)):
            try:
                self.app_pool = await database.create_pool(database.APP_ROLE)
                self.collector_pool = await database.create_pool(database.COLLECTOR_ROLE)
                return
            except (OSError, asyncpg.PostgresError, asyncio.TimeoutError) as exc:
                if delay is None:
                    raise
                log.info("Datenbank noch nicht bereit (%s) – neuer Versuch in %d s.", exc, delay)
                await asyncio.sleep(delay)

    async def _start_backend_services(self) -> None:
        try:
            await self._connect_pools()
            assert self.app_pool is not None and self.collector_pool is not None
            async with self.app_pool.acquire() as connection:
                applied = await migration_runner.migrate(connection, migration_runner.discover())
                if applied:
                    log.info("%d Migration(en) angewendet.", len(applied))
                await connection.execute("SELECT skytech_config.aufbewahrung_anwenden()")
                await self._log_finished_restore(connection)
            self.collector = Collector(self.app_pool, self.collector_pool)
            await self.collector.start()
        except (migration_runner.MigrationError, asyncpg.PostgresError, OSError, asyncio.TimeoutError) as exc:
            self.startup_error = str(exc)
            log.error("Start der Datenaufzeichnung fehlgeschlagen: %s", exc)
            return

        settings = connection_settings()
        if settings is None:
            log.warning("Keine Verbindung zu Home Assistant konfiguriert – es wird nichts aufgezeichnet.")
            return
        url, token = settings
        self.ha = HAClient(url, token, self.collector.on_state_changed, self.collector.on_connected)
        self.collector.ha = self.ha
        self._tasks.append(asyncio.create_task(self.ha.run(), name="ha-client"))

    @staticmethod
    async def _log_finished_restore(connection: asyncpg.Connection) -> None:
        """Nach dem Neustart: eine gerade beendete Wiederherstellung ins (neue) Protokoll schreiben."""
        state = backup.read_state()
        if not state or state.get("protokolliert") or state.get("status") == "laeuft":
            return
        await sensor_service.log_change(connection, state.get("benutzer"), "sicherung_wiederhergestellt", state)
        backup.write_state({**state, "protokolliert": True})

    # ------------------------------------------------------------------
    # Routen
    # ------------------------------------------------------------------

    def _require_database(self) -> asyncpg.Pool:
        if self.app_pool is None:
            raise web.HTTPServiceUnavailable(
                text='{"error": "Datenbank noch nicht bereit."}', content_type="application/json"
            )
        return self.app_pool

    async def handle_index(self, _request: web.Request) -> web.StreamResponse:
        index = _STATIC_DIR / "index.html"
        if not index.exists():
            return web.Response(status=503, text="Oberfläche nicht gebaut (cd web && npm run build).")
        # Nach einem Add-on-Update muss der Browser das neue Bundle laden; die
        # Assets tragen ohnehin einen Hash im Namen.
        return web.FileResponse(index, headers={"Cache-Control": "no-cache"})

    async def _collector_health(self) -> health.ServiceHealth:
        if self.startup_error:
            return health.ServiceHealth("collector", "Aufzeichnung", False, self.startup_error)
        if self.collector is None:
            return health.ServiceHealth("collector", "Aufzeichnung", False, "Startet …")
        if self.ha is None:
            return health.ServiceHealth("collector", "Aufzeichnung", False, "Keine Verbindung zu Home Assistant konfiguriert")
        if not self.ha.connected:
            return health.ServiceHealth("collector", "Aufzeichnung", False,
                                        f"Home Assistant nicht verbunden{': ' + self.ha.last_error if self.ha.last_error else ''}")
        if self.collector.last_error:
            return health.ServiceHealth("collector", "Aufzeichnung", False, self.collector.last_error)
        return health.ServiceHealth(
            "collector", "Aufzeichnung", True,
            f"{len(self.collector.active_sensor_ids)} Sensoren · {self.collector.values_last_minute()} Werte/min",
        )

    async def handle_status(self, _request: web.Request) -> web.Response:
        session = self._session
        if session is None:
            return error_response("Dienst startet noch.", 503)
        services = await health.collect([
            health.probe_database,
            lambda: health.probe_grafana(session, self._ingress_entry),
            self._collector_health,
        ])
        now = datetime.now(timezone.utc)
        recording: dict[str, Any] | None = None
        if self.collector is not None:
            minutes_until = self.collector.minutes_until
            recording = {
                "sensoren_aktiv": len(self.collector.active_sensor_ids),
                "werte_letzte_minute": self.collector.values_last_minute(),
                "puffer": self.collector.buffered,
                "verworfen": self.collector.dropped,
                "letzte_schreibung": format_berlin(self.collector.last_write) if self.collector.last_write else None,
                "minutenwerte_bis": format_berlin(minutes_until) if minutes_until else None,
            }
        database_size = None
        if self.app_pool is not None:
            try:
                async with self.app_pool.acquire(timeout=3) as connection:
                    database_size = await connection.fetchval("SELECT pg_database_size(current_database())")
            except (asyncpg.PostgresError, OSError, asyncio.TimeoutError):
                database_size = None
        return json_response({
            "version": self._version,
            "services": [service.to_json() for service in services],
            "aufzeichnung": recording,
            "datenbank_bytes": database_size,
            "checked_at": format_berlin(now),
            "checked_at_iso": now.isoformat(),
        })

    async def handle_catalog(self, _request: web.Request) -> web.Response:
        async with self._require_database().acquire() as connection:
            return json_response(await sensor_service.catalog(connection))

    async def handle_sensors(self, _request: web.Request) -> web.Response:
        async with self._require_database().acquire() as connection:
            rows = await sensor_service.list_sensors(connection)
        for row in rows:
            row["letzte_zeit_text"] = format_berlin(row["letzte_zeit"]) if row["letzte_zeit"] else None
        return json_response({"sensors": rows})

    async def handle_create_sensors(self, request: web.Request) -> web.Response:
        body = await self._json_body(request)
        items = body.get("sensors") if isinstance(body, dict) else None
        if not isinstance(items, list):
            return error_response("Erwartet: {\"sensors\": [...]}", 400)
        try:
            async with self._require_database().acquire() as connection:
                ids = await sensor_service.create_sensors(connection, items, request_user(request))
        except sensor_service.ValidationError as exc:
            return error_response(str(exc), 422, exc.field_errors)
        return json_response({"ids": ids}, status=201)

    async def handle_update_sensor(self, request: web.Request) -> web.Response:
        sensor_id = int(request.match_info["sensor_id"])
        body = await self._json_body(request)
        if not isinstance(body, dict):
            return error_response("JSON-Objekt erwartet.", 400)
        try:
            async with self._require_database().acquire() as connection:
                await sensor_service.update_sensor(connection, sensor_id, body, request_user(request))
        except sensor_service.ValidationError as exc:
            return error_response(str(exc), 422, exc.field_errors)
        except sensor_service.NotFoundError:
            return error_response("Sensor nicht gefunden.", 404)
        return json_response({"ok": True})

    async def handle_delete_sensor(self, request: web.Request) -> web.Response:
        sensor_id = int(request.match_info["sensor_id"])
        try:
            async with self._require_database().acquire() as connection:
                await sensor_service.delete_sensor(connection, sensor_id, request_user(request))
        except sensor_service.NotFoundError:
            return error_response("Sensor nicht gefunden.", 404)
        return json_response({"ok": True})

    async def handle_entities(self, _request: web.Request) -> web.Response:
        """HA-Entitäten mit Vorschlag und Hinweis, was davon schon aufgezeichnet wird."""
        if self.ha is None or not self.ha.connected:
            return error_response("Keine Verbindung zu Home Assistant.", 503)
        async with self._require_database().acquire() as connection:
            recorded_rows = await connection.fetch("SELECT entity_id, attribut FROM skytech.sensor")
        recorded: dict[str, set[str | None]] = {}
        for row in recorded_rows:
            recorded.setdefault(row["entity_id"], set()).add(row["attribut"])

        entities = []
        for entity_id, state in sorted(self.ha.states.items()):
            attributes = state.get("attributes") or {}
            numeric_attributes = [
                {"name": name, "wert": value, "erfasst": name in recorded.get(entity_id, set()),
                 "vorschlag": suggest(entity_id, attributes, name)}
                for name, value in attributes.items()
                if name not in ("friendly_name",) and is_numeric_attribute(value)
            ]
            entities.append({
                "entity_id": entity_id,
                "name": attributes.get("friendly_name") or entity_id,
                "domain": entity_id.split(".", 1)[0],
                "state": state.get("state"),
                "einheit": attributes.get("unit_of_measurement"),
                "device_class": attributes.get("device_class"),
                "state_class": attributes.get("state_class"),
                "erfasst": None in recorded.get(entity_id, set()),
                "vorschlag": suggest(entity_id, attributes),
                "attribute": numeric_attributes,
            })
        return json_response({"entities": entities})

    # ------------------------------------------------------------------
    # Sicherungen (M2)
    # ------------------------------------------------------------------

    async def handle_backups(self, _request: web.Request) -> web.Response:
        state = backup.read_state()
        if state and state.get("status") == "laeuft" and not self.restorer.busy:
            # Der Prozess wurde während einer Wiederherstellung neu gestartet.
            state = {**state, "status": "unklar",
                     "meldung": "Der Dienst wurde während der Wiederherstellung neu gestartet – Ergebnis prüfen."}
        return json_response({"sicherungen": [item.to_json() for item in backup.list_backups()],
                              "wiederherstellung": state, "laeuft": self.restorer.busy})

    async def handle_create_backup(self, request: web.Request) -> web.Response:
        try:
            created = await backup.create("manuell")
        except backup.BackupError as exc:
            return error_response(str(exc), 500)
        await self._log(request, "sicherung_erstellt", {"datei": created.name})
        return json_response(created.to_json(), status=201)

    async def handle_download_archive(self, request: web.Request) -> web.StreamResponse:
        """Komplettpaket (Datenbank + Grafana) als .tar – wird nach dem Senden gelöscht."""
        try:
            archive = await backup.build_archive(self._version)
        except backup.BackupError as exc:
            return error_response(str(exc), 500)
        stamp = datetime.now(BERLIN).strftime("%Y-%m-%d_%H%M")
        response = web.StreamResponse(headers={
            "Content-Type": "application/x-tar",
            "Content-Disposition": f'attachment; filename="skytech-data-insight_{stamp}.tar"',
            "Content-Length": str(archive.stat().st_size),
        })
        try:
            await response.prepare(request)
            with archive.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    await response.write(chunk)
            await response.write_eof()
        finally:
            archive.unlink(missing_ok=True)
        await self._log(request, "sicherung_heruntergeladen", {})
        return response

    async def handle_download_file(self, request: web.Request) -> web.StreamResponse:
        try:
            path = backup.resolve(request.match_info["name"])
        except backup.BackupError as exc:
            return error_response(str(exc), 404)
        return web.FileResponse(path, headers={"Content-Disposition": f'attachment; filename="{path.name}"'})

    async def handle_delete_backup(self, request: web.Request) -> web.Response:
        try:
            path = backup.resolve(request.match_info["name"])
        except backup.BackupError as exc:
            return error_response(str(exc), 404)
        path.unlink()
        await self._log(request, "sicherung_geloescht", {"datei": path.name})
        return json_response({"ok": True})

    async def handle_upload(self, request: web.Request) -> web.Response:
        """Nimmt eine Sicherung als Rohdaten entgegen (PUT, Body = Datei) und prüft sie."""
        original = request.query.get("name", "")
        suffix = ".tar" if original.lower().endswith(".tar") else ".dump"
        backup.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        target = backup.BACKUP_DIR / f"upload_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}{suffix}"
        try:
            with target.open("wb") as handle:
                async for chunk in request.content.iter_chunked(1024 * 1024):
                    handle.write(chunk)
            info = await backup.inspect(target)
        except (backup.BackupError, OSError) as exc:
            target.unlink(missing_ok=True)
            return error_response(str(exc), 422)
        backup.prune("upload")
        return json_response({**info, "original": original}, status=201)

    async def handle_restore(self, request: web.Request) -> web.Response:
        body = await self._json_body(request)
        if not isinstance(body, dict) or body.get("bestaetigung") != "WIEDERHERSTELLEN":
            return error_response("Bestätigung fehlt.", 400)
        try:
            path = backup.resolve(request.match_info["name"])
        except backup.BackupError as exc:
            return error_response(str(exc), 404)
        if self.restorer.busy:
            return error_response("Es läuft bereits eine Wiederherstellung.", 409)
        self._tasks.append(asyncio.create_task(self._restore(path, request_user(request)), name="restore"))
        return json_response({"ok": True, "datei": path.name}, status=202)

    async def _restore(self, path: Path, user: str | None) -> None:
        async def stop_writers() -> None:
            # Letzte Werte noch schreiben, dann alle Verbindungen zur alten Datenbank schließen.
            if self.collector is not None:
                await self.collector.stop()
                self.collector = None
            for pool in (self.collector_pool, self.app_pool):
                if pool is not None:
                    await pool.close()
            self.app_pool = self.collector_pool = None

        try:
            await self.restorer.restore(path, user, stop_writers)
        finally:
            # Neustart immer – auch nach einem Fehler sind die Verbindungen geschlossen.
            await backup.restart_services()

    async def _log(self, request: web.Request, action: str, details: dict[str, Any]) -> None:
        if self.app_pool is None:
            return
        async with self.app_pool.acquire() as connection:
            await sensor_service.log_change(connection, request_user(request), action, details)

    @staticmethod
    async def _json_body(request: web.Request) -> Any:
        try:
            return await request.json()
        except ValueError:
            raise web.HTTPBadRequest(text='{"error": "Ungültiges JSON."}', content_type="application/json")

    def build_app(self) -> web.Application:
        app = web.Application()
        app.on_startup.append(self._on_startup)
        app.on_cleanup.append(self._on_cleanup)
        app.router.add_get("/", self.handle_index)
        app.router.add_get("/index.html", self.handle_index)
        app.router.add_get("/api/status", self.handle_status)
        app.router.add_get("/api/catalog", self.handle_catalog)
        app.router.add_get("/api/sensors", self.handle_sensors)
        app.router.add_post("/api/sensors", self.handle_create_sensors)
        app.router.add_put(r"/api/sensors/{sensor_id:\d+}", self.handle_update_sensor)
        app.router.add_delete(r"/api/sensors/{sensor_id:\d+}", self.handle_delete_sensor)
        app.router.add_get("/api/ha/entities", self.handle_entities)
        app.router.add_get("/api/backups", self.handle_backups)
        app.router.add_post("/api/backups", self.handle_create_backup)
        app.router.add_get("/api/backups/download", self.handle_download_archive)
        app.router.add_put("/api/backups/upload", self.handle_upload)
        app.router.add_get("/api/backups/{name}", self.handle_download_file)
        app.router.add_delete("/api/backups/{name}", self.handle_delete_backup)
        app.router.add_post("/api/backups/{name}/restore", self.handle_restore)
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
    # s6 beendet mit SIGTERM: sauber herunterfahren, damit der Puffer noch geschrieben wird.
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signal_number, stop.set)
    try:
        await stop.wait()
    finally:
        log.info("Verwaltungsdienst wird beendet …")
        await runner.cleanup()


def main() -> None:
    level = _LOG_LEVELS.get(os.environ.get("SKYTECH_LOG_LEVEL", "info"), logging.INFO)
    logging.basicConfig(level=level, format="[app] %(levelname)s %(name)s: %(message)s")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
