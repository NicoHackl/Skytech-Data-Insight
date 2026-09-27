"""MCP-Server des Add-ons: Datenbank, Sensoren und Grafana für LLMs (Claude, GPT …).

Transport: Streamable HTTP unter `/mcp` auf Port 8765, zustandslos, JSON-Antworten.
Anmeldung: `Authorization: Bearer <mcp_token>` (Add-on-Option). Ohne Token
startet der Dienst nicht (s6-Dienst `mcp`). Die Fachlogik liegt in mcp_tools.py.
"""

import asyncio
import contextlib
import hmac
import json
import logging
import os
from typing import Any

import aiohttp
import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

import database
from grafana_client import GrafanaClient
from mcp_tools import McpTools, ToolError

log = logging.getLogger("skytech.mcp")

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8765

INSTRUCTIONS = """\
Skytech Data Insight: Langzeitablage von Energiedaten aus Home Assistant in TimescaleDB (PostgreSQL 17)
mit Grafana. Alle Namen sind deutsch.

Datenmodell (Details: Werkzeug schema_anzeigen):
- skytech.sensor: aufgezeichnete HA-Entitäten/Attribute mit kategorie (pv, speicher, netz, heizung,
  verbraucher, sonstiges), groesse (leistung, energie, ladezustand, temperatur, spannung, strom,
  zustand, sonstiges), rolle (ist/soll), soll_ist_paar, einheit, anlage, energie_zaehler, aktiv.
- skytech.messwert: Rohwerte bei jeder Änderung (zeit, sensor_id, wert, text_wert). on/off = 1/0.
- skytech.messwert_1min: zeitgewichtete Minutenwerte (mittel, minimum, maximum, letzter, zuwachs,
  anzahl, abdeckung_s). zuwachs = Zählerzuwachs je Minute bei energie_zaehler-Sensoren (z. B. kWh).
- skytech.messwert_15min / _1h / _1d: Verdichtungen mit denselben Spalten (1d = Berliner Kalendertag).
- Sichten mit Stammdaten: skytech.v_messwert, v_messwert_1min/_15min/_1h/_1d, v_pv, v_speicher,
  v_netz, v_heizung, v_verbraucher (Minutenwerte je Kategorie), v_soll_ist (zeit, paar, soll, ist,
  abweichung).
- Zeitstempel sind timestamptz in UTC. Für Menschen immer Europe/Berlin, Datum TT.MM.JJJJ.

Grafana:
- Datenquelle uid "skytech-db" (Typ grafana-postgresql-datasource). In Panels
  {"type": "grafana-postgresql-datasource", "uid": "skytech-db"} verwenden.
- Zeitreihen-Abfragen: SELECT zeit AS time, mittel AS value, name AS metric FROM skytech.v_messwert_1min
  WHERE $__timeFilter(zeit) AND ... ORDER BY 1 (format "time_series"). Für lange Zeiträume die
  Stufen _15min/_1h/_1d nehmen. Energie pro Tag: sum(zuwachs) aus v_messwert_1d.
- Dashboard-Zeitzone "Europe/Berlin", Sprache deutsch. Dashboards landen im Ordner "Skytech".

Regeln:
- Lesen mit sql_abfrage (schreibgeschützt). Schreiben mit sql_ausfuehren oder, für dauerhafte
  Schemaänderungen, mit migration_anlegen. Vor jeder schreibenden Aktion legt der Server automatisch
  eine Sicherung an und protokolliert die Aktion.
- Vor Schemaänderungen den Benutzer fragen. Keine Messdaten löschen, ohne dass der Benutzer es
  ausdrücklich verlangt.
"""

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)


def _text(result: Any) -> str:
    return json.dumps(result, ensure_ascii=False, indent=1, default=str)


def build_server(tools: McpTools) -> MCPServer:
    server = MCPServer(name="Skytech Data Insight", instructions=INSTRUCTIONS,
                       version=os.environ.get("SKYTECH_VERSION", "dev"))

    async def run(coroutine) -> str:
        try:
            return _text(await coroutine)
        except ToolError as exc:
            # Als Text zurück, damit das Modell die Ursache sieht und korrigieren kann.
            return _text({"fehler": str(exc)})

    @server.tool(name="schema_anzeigen", annotations=READ_ONLY)
    async def schema_anzeigen(schema: str | None = None) -> str:
        """Tabellen, Sichten und Verdichtungen mit Spalten. Optional auf ein Schema begrenzen (z. B. skytech)."""
        return await run(tools.schema(schema))

    @server.tool(name="sql_abfrage", annotations=READ_ONLY)
    async def sql_abfrage(sql: str, max_zeilen: int = 500) -> str:
        """Führt eine lesende SQL-Abfrage aus (schreibgeschützte Transaktion, 30 s Zeitlimit)."""
        return await run(tools.query(sql, max_zeilen))

    @server.tool(name="statistik", annotations=READ_ONLY)
    async def statistik() -> str:
        """Überblick: Datenbankgröße, Einstellungen, je Sensor Anzahl Roh-/Minutenwerte und Zeitraum."""
        return await run(tools.statistics())

    @server.tool(name="sensoren_auflisten", annotations=READ_ONLY)
    async def sensoren_auflisten() -> str:
        """Alle Sensoren mit Stammdaten und letztem Wert."""
        return await run(tools.list_sensors())

    @server.tool(name="katalog_anzeigen", annotations=READ_ONLY)
    async def katalog_anzeigen() -> str:
        """Zulässige Kategorien und Größen sowie vorhandene Anlagen und Soll/Ist-Paare."""
        return await run(tools.catalog())

    @server.tool(name="sql_ausfuehren", annotations=WRITES)
    async def sql_ausfuehren(sql: str, begruendung: str) -> str:
        """Führt schreibendes SQL (DML/DDL) in einer Transaktion aus. Legt vorher eine Sicherung an."""
        return await run(tools.execute(sql, begruendung))

    @server.tool(name="migration_anlegen", annotations=WRITES)
    async def migration_anlegen(name: str, sql: str, begruendung: str) -> str:
        """Dauerhafte Schemaänderung als Anlagen-Migration (/data/migrations, Nummer ab 1000) anlegen und
        anwenden. name: nur a-z, 0-9, _. Scheitert sie, wird nichts geändert. Legt vorher eine Sicherung an."""
        return await run(tools.create_migration(name, sql, begruendung))

    @server.tool(name="sensoren_anlegen", annotations=WRITES)
    async def sensoren_anlegen(sensoren: list[dict[str, Any]]) -> str:
        """Legt Sensoren an (Aufzeichnung beginnt sofort). Je Eintrag Pflicht: entity_id, name, kategorie,
        groesse; optional attribut, einheit, anlage, rolle, soll_ist_paar, energie_zaehler, aktiv."""
        return await run(tools.add_sensors(sensoren))

    @server.tool(name="sensor_aendern", annotations=WRITES)
    async def sensor_aendern(sensor_id: int, aenderungen: dict[str, Any]) -> str:
        """Ändert Felder eines Sensors (name, kategorie, groesse, rolle, soll_ist_paar, einheit, anlage,
        energie_zaehler, aktiv)."""
        return await run(tools.update_sensor(sensor_id, aenderungen))

    @server.tool(name="aufbewahrung_setzen", annotations=WRITES)
    async def aufbewahrung_setzen(rohwerte_tage: int | None, minutenwerte_tage: int | None) -> str:
        """Aufbewahrung in Tagen; null = nie löschen. Minutenwerte mindestens 31 Tage."""
        return await run(tools.set_retention(rohwerte_tage, minutenwerte_tage))

    @server.tool(name="backup_erstellen", annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False))
    async def backup_erstellen() -> str:
        """Legt sofort eine Sicherung der Datenbank an (pg_dump)."""
        return await run(tools.create_backup())

    @server.tool(name="backups_auflisten", annotations=READ_ONLY)
    async def backups_auflisten() -> str:
        """Vorhandene Sicherungen, neueste zuerst."""
        return _text(tools.list_backups())

    @server.tool(name="grafana_datenquellen", annotations=READ_ONLY)
    async def grafana_datenquellen() -> str:
        """Datenquellen in Grafana (die Skytech-Datenbank hat uid skytech-db)."""
        return await run(tools.grafana_datasources())

    @server.tool(name="grafana_dashboards_auflisten", annotations=READ_ONLY)
    async def grafana_dashboards_auflisten(suche: str = "") -> str:
        """Dashboards in Grafana, optional nach Titel gefiltert."""
        return await run(tools.grafana_dashboards(suche))

    @server.tool(name="grafana_dashboard_lesen", annotations=READ_ONLY)
    async def grafana_dashboard_lesen(uid: str) -> str:
        """Vollständiges Dashboard-JSON samt Metadaten."""
        return await run(tools.grafana_dashboard(uid))

    @server.tool(name="grafana_dashboard_speichern", annotations=WRITES)
    async def grafana_dashboard_speichern(dashboard: dict[str, Any], nachricht: str, ordner: str = "Skytech") -> str:
        """Legt ein Dashboard an oder überschreibt es (Zuordnung über dashboard.uid). Grafana führt eine
        Versionsgeschichte. Datenquelle: {"type": "grafana-postgresql-datasource", "uid": "skytech-db"}."""
        return await run(tools.grafana_save_dashboard(dashboard, nachricht, ordner or None))

    @server.tool(name="grafana_dashboard_loeschen", annotations=WRITES)
    async def grafana_dashboard_loeschen(uid: str) -> str:
        """Löscht ein Dashboard. Nur auf ausdrücklichen Wunsch des Benutzers."""
        return await run(tools.grafana_delete_dashboard(uid))

    return server


class BearerAuth:
    """Lässt nur Anfragen mit dem richtigen Bearer-Token durch (Vergleich in konstanter Zeit)."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            header = dict(scope.get("headers") or []).get(b"authorization", b"")
            if not hmac.compare_digest(header, self._expected):
                response = JSONResponse({"error": "Nicht angemeldet – Authorization: Bearer <mcp_token> fehlt oder ist falsch."},
                                        status_code=401, headers={"WWW-Authenticate": "Bearer"})
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


def build_app(tools: McpTools, token: str) -> Starlette:
    server = build_server(tools)
    app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        host=LISTEN_HOST,
        # Erreichbar über die LAN-Adresse des HA-Hosts; geschützt wird über das Token.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    app.add_middleware(BearerAuth, token=token)
    return app


async def _main() -> None:
    token = os.environ.get("SKYTECH_MCP_TOKEN", "")
    if len(token) < 16:
        raise SystemExit("MCP-Token fehlt oder ist kürzer als 16 Zeichen.")
    pool = None
    for delay in (1, 2, 3, 5, 5, 10, 10, 30):
        try:
            pool = await database.create_pool(database.ADMIN_ROLE)
            break
        except OSError as exc:
            log.info("Datenbank noch nicht bereit (%s) – neuer Versuch in %d s.", exc, delay)
            await asyncio.sleep(delay)
    if pool is None:
        raise SystemExit("Datenbank nicht erreichbar.")
    async with aiohttp.ClientSession() as session:
        tools = McpTools(pool, GrafanaClient(session))
        config = uvicorn.Config(build_app(tools, token), host=LISTEN_HOST, port=LISTEN_PORT,
                                log_level="warning", access_log=False)
        log.info("MCP-Server hört auf %s:%d/mcp", LISTEN_HOST, LISTEN_PORT)
        with contextlib.suppress(asyncio.CancelledError):
            await uvicorn.Server(config).serve()
    await pool.close()


def main() -> None:
    level = os.environ.get("SKYTECH_LOG_LEVEL", "info").upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format="[mcp] %(levelname)s %(name)s: %(message)s")
    asyncio.run(_main())


if __name__ == "__main__":
    main()
