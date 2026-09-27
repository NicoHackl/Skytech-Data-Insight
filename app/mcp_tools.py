"""Fachlogik der MCP-Werkzeuge – ohne MCP-Protokoll, damit sie direkt testbar ist.

Voller Zugriff (Umsetzungsplan): Lesen ist frei; jede schreibende Aktion legt
vorher eine Sicherung an (backup.py) und landet im Änderungsprotokoll mit
Quelle `mcp`. Scheitert die Sicherung, läuft die Aktion nicht.
"""

import json
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg

import backup
import migration_runner
import sensor_service
from display_time import format_berlin
from grafana_client import GrafanaClient

QUERY_TIMEOUT_MS = 30_000
WRITE_TIMEOUT_MS = 300_000
MAX_ROWS_LIMIT = 5000
SITE_MIGRATION_START = 1000
DASHBOARD_FOLDER = "Skytech"
_NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")

# Nicht angezeigt: Systemschemas und die internen Schemas von TimescaleDB.
_HIDDEN_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast", "public",
                   "_timescaledb_catalog", "_timescaledb_internal", "_timescaledb_cache",
                   "_timescaledb_config", "_timescaledb_functions", "_timescaledb_debug",
                   "timescaledb_information", "timescaledb_experimental")


class ToolError(RuntimeError):
    """Verständliche Fehlermeldung für das LLM."""


def to_json_value(value: Any) -> Any:
    """Macht Datenbankwerte JSON-fähig. Zeitpunkte: ISO in UTC (Maschinenformat)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: to_json_value(item) for key, item in value.items()}
    if isinstance(value, (bytes, memoryview)):
        return f"<{len(bytes(value))} Bytes>"
    return str(value)


def next_site_migration_number(existing: list[int]) -> int:
    """Nächste freie Nummer für eine Anlagen-Migration (ab 1000)."""
    site = [number for number in existing if number >= SITE_MIGRATION_START]
    return max(site, default=SITE_MIGRATION_START - 1) + 1


class McpTools:
    def __init__(self, pool: asyncpg.Pool, grafana: GrafanaClient, site_dir: Path = migration_runner.SITE_DIR,
                 backup_dir: Path = backup.BACKUP_DIR) -> None:
        self._pool = pool
        self._grafana = grafana
        self._site_dir = site_dir
        self._backup_dir = backup_dir

    async def _backup_before(self, action: str) -> str:
        try:
            created = await backup.create("mcp", self._backup_dir)
        except backup.BackupError as exc:
            raise ToolError(f"{exc} – „{action}“ wurde deshalb nicht ausgeführt.") from exc
        return created.name

    async def _log(self, action: str, details: dict[str, Any]) -> None:
        async with self._pool.acquire() as connection:
            await sensor_service.log_change(connection, "mcp", action, details, source="mcp")

    # ------------------------------------------------------------------
    # Lesen
    # ------------------------------------------------------------------

    async def schema(self, schema_name: str | None = None) -> dict[str, Any]:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT c.table_schema AS schema, c.table_name AS objekt,
                       CASE t.table_type WHEN 'VIEW' THEN 'view' ELSE 'tabelle' END AS art,
                       obj_description(format('%I.%I', c.table_schema, c.table_name)::regclass) AS beschreibung,
                       json_agg(json_build_object('spalte', c.column_name, 'typ', c.data_type,
                                                  'null', c.is_nullable = 'YES')
                                ORDER BY c.ordinal_position) AS spalten
                FROM information_schema.columns c
                JOIN information_schema.tables t USING (table_schema, table_name)
                WHERE c.table_schema <> ALL($1::text[]) AND ($2::text IS NULL OR c.table_schema = $2)
                GROUP BY 1, 2, 3
                ORDER BY 1, 3, 2
                """,
                list(_HIDDEN_SCHEMAS), schema_name,
            )
            aggregates = await connection.fetch(
                "SELECT view_schema, view_name FROM timescaledb_information.continuous_aggregates")
        continuous = {(row["view_schema"], row["view_name"]) for row in aggregates}
        objects = []
        for row in rows:
            kind = "continuous_aggregate" if (row["schema"], row["objekt"]) in continuous else row["art"]
            objects.append({"schema": row["schema"], "name": row["objekt"], "art": kind,
                            "beschreibung": row["beschreibung"], "spalten": json.loads(row["spalten"])})
        return {"objekte": objects}

    async def query(self, sql: str, max_rows: int = 500) -> dict[str, Any]:
        """Führt eine Abfrage in einer schreibgeschützten Transaktion aus."""
        max_rows = max(1, min(int(max_rows), MAX_ROWS_LIMIT))
        async with self._pool.acquire() as connection:
            try:
                async with connection.transaction(readonly=True):
                    await connection.execute(f"SET LOCAL statement_timeout = {QUERY_TIMEOUT_MS}")
                    statement = await connection.prepare(sql)
                    columns = [attribute.name for attribute in statement.get_attributes()]
                    records = await statement.fetch()
            except asyncpg.PostgresError as exc:
                raise ToolError(f"Abfrage fehlgeschlagen: {exc}") from exc
        truncated = len(records) > max_rows
        return {
            "spalten": columns,
            "zeilen": [[to_json_value(value) for value in record] for record in records[:max_rows]],
            "anzahl": len(records),
            "abgeschnitten": truncated,
            "hinweis": "Zeitpunkte in UTC (ISO 8601). Für Menschen: AT TIME ZONE 'Europe/Berlin'.",
        }

    async def statistics(self) -> dict[str, Any]:
        async with self._pool.acquire() as connection:
            sensors = await connection.fetch("""
                SELECT s.id, s.name, s.entity_id, s.attribut, s.kategorie, s.groesse, s.einheit, s.aktiv,
                       r.anzahl AS rohwerte, r.erster, r.letzter,
                       (SELECT count(*) FROM skytech.messwert_1min m WHERE m.sensor_id = s.id) AS minutenwerte
                FROM skytech.sensor s
                LEFT JOIN LATERAL (
                    SELECT count(*) AS anzahl, min(zeit) AS erster, max(zeit) AS letzter
                    FROM skytech.messwert m WHERE m.sensor_id = s.id
                ) r ON true
                ORDER BY s.kategorie, s.name
            """)
            size = await connection.fetchval("SELECT pg_database_size(current_database())")
            settings = await connection.fetch("SELECT schluessel, wert FROM skytech_config.einstellung ORDER BY 1")
        return {
            "datenbank_bytes": size,
            "einstellungen": {row["schluessel"]: json.loads(row["wert"]) for row in settings},
            "sensoren": [{key: to_json_value(value) for key, value in dict(row).items()} for row in sensors],
        }

    async def list_sensors(self) -> list[dict[str, Any]]:
        async with self._pool.acquire() as connection:
            rows = await sensor_service.list_sensors(connection)
        return [{key: to_json_value(value) for key, value in row.items()} for row in rows]

    async def catalog(self) -> dict[str, Any]:
        async with self._pool.acquire() as connection:
            return await sensor_service.catalog(connection)

    # ------------------------------------------------------------------
    # Schreiben (immer mit Sicherung und Protokoll)
    # ------------------------------------------------------------------

    async def execute(self, sql: str, reason: str) -> dict[str, Any]:
        """Führt beliebiges SQL in einer Transaktion aus."""
        if not reason.strip():
            raise ToolError("Bitte eine Begründung angeben – sie steht im Änderungsprotokoll.")
        backup_name = await self._backup_before("SQL ausführen")
        async with self._pool.acquire() as connection:
            try:
                async with connection.transaction():
                    await connection.execute(f"SET LOCAL statement_timeout = {WRITE_TIMEOUT_MS}")
                    status = await connection.execute(sql)
            except asyncpg.PostgresError as exc:
                raise ToolError(f"SQL fehlgeschlagen, nichts geändert (Sicherung: {backup_name}): {exc}") from exc
        await self._log("sql_ausgefuehrt", {"sql": sql, "begruendung": reason, "ergebnis": status,
                                            "sicherung": backup_name})
        return {"ergebnis": status, "sicherung": backup_name}

    async def create_migration(self, name: str, sql: str, reason: str) -> dict[str, Any]:
        """Legt eine Anlagen-Migration an und wendet sie an. Scheitert sie, bleibt nichts zurück."""
        if not _NAME_PATTERN.match(name):
            raise ToolError("Name nur aus Kleinbuchstaben, Ziffern und _ (z. B. wallbox_tabelle).")
        if not reason.strip():
            raise ToolError("Bitte eine Begründung angeben.")
        existing = [m.version for m in migration_runner.discover(site_dir=self._site_dir)]
        number = next_site_migration_number(existing)
        backup_name = await self._backup_before("Migration")
        self._site_dir.mkdir(parents=True, exist_ok=True)
        path = self._site_dir / f"{number:04d}_{name}.sql"
        path.write_text(f"-- {reason.strip()}\n-- Angelegt über MCP am {format_berlin(datetime.now().astimezone())}\n\n{sql.strip()}\n",
                        encoding="utf-8")
        try:
            async with self._pool.acquire() as connection:
                # Objekte gehören wie alle anderen skytech_app (Mitglied: skytech_admin).
                await connection.execute("SET ROLE skytech_app")
                try:
                    applied = await migration_runner.migrate(connection, migration_runner.discover(site_dir=self._site_dir))
                finally:
                    await connection.execute("RESET ROLE")
        except migration_runner.MigrationError as exc:
            path.unlink(missing_ok=True)
            raise ToolError(f"{exc} – Datei wieder entfernt, nichts geändert.") from exc
        await self._log("migration_angewendet", {"datei": path.name, "begruendung": reason, "sicherung": backup_name})
        return {"datei": path.name, "angewendet": [m.path.name for m in applied], "sicherung": backup_name}

    async def add_sensors(self, sensors: list[dict[str, Any]]) -> dict[str, Any]:
        backup_name = await self._backup_before("Sensoren anlegen")
        async with self._pool.acquire() as connection:
            try:
                ids = await sensor_service.create_sensors(connection, sensors, "mcp", source="mcp")
            except sensor_service.ValidationError as exc:
                raise ToolError(f"{exc} {exc.field_errors}") from exc
        return {"ids": ids, "sicherung": backup_name}

    async def update_sensor(self, sensor_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        backup_name = await self._backup_before("Sensor ändern")
        async with self._pool.acquire() as connection:
            try:
                await sensor_service.update_sensor(connection, sensor_id, changes, "mcp", source="mcp")
            except sensor_service.ValidationError as exc:
                raise ToolError(f"{exc} {exc.field_errors}") from exc
            except sensor_service.NotFoundError as exc:
                raise ToolError(f"Sensor {sensor_id} nicht gefunden.") from exc
        return {"ok": True, "sicherung": backup_name}

    async def set_retention(self, raw_days: int | None, minute_days: int | None) -> dict[str, Any]:
        for label, days in (("Rohwerte", raw_days), ("Minutenwerte", minute_days)):
            if days is not None and days < 1:
                raise ToolError(f"{label}: mindestens 1 Tag oder null für „nie löschen“.")
        backup_name = await self._backup_before("Aufbewahrung ändern")
        async with self._pool.acquire() as connection:
            try:
                async with connection.transaction():
                    await connection.execute(
                        "UPDATE skytech_config.einstellung SET wert = $1::jsonb, geaendert_am = now() "
                        "WHERE schluessel = 'aufbewahrung_rohwerte_tage'", json.dumps(raw_days))
                    await connection.execute(
                        "UPDATE skytech_config.einstellung SET wert = $1::jsonb, geaendert_am = now() "
                        "WHERE schluessel = 'aufbewahrung_minutenwerte_tage'", json.dumps(minute_days))
                    await connection.execute("SELECT skytech_config.aufbewahrung_anwenden()")
            except asyncpg.PostgresError as exc:
                raise ToolError(f"Aufbewahrung nicht geändert: {exc}") from exc
        await self._log("aufbewahrung_geaendert", {"rohwerte_tage": raw_days, "minutenwerte_tage": minute_days,
                                                   "sicherung": backup_name})
        return {"rohwerte_tage": raw_days, "minutenwerte_tage": minute_days, "sicherung": backup_name}

    # ------------------------------------------------------------------
    # Sicherungen
    # ------------------------------------------------------------------

    async def create_backup(self) -> dict[str, Any]:
        try:
            created = await backup.create("manuell", self._backup_dir)
        except backup.BackupError as exc:
            raise ToolError(str(exc)) from exc
        return created.to_json()

    def list_backups(self) -> list[dict[str, Any]]:
        return [item.to_json() for item in backup.list_backups(self._backup_dir)]

    # ------------------------------------------------------------------
    # Grafana
    # ------------------------------------------------------------------

    async def grafana_datasources(self) -> list[dict[str, Any]]:
        return [{key: source.get(key) for key in ("uid", "name", "type", "isDefault")}
                for source in await self._grafana.datasources()]

    async def grafana_dashboards(self, query: str = "") -> list[dict[str, Any]]:
        return [{key: item.get(key) for key in ("uid", "title", "folderTitle", "url", "tags")}
                for item in await self._grafana.search_dashboards(query)]

    async def grafana_dashboard(self, uid: str) -> dict[str, Any]:
        return await self._grafana.dashboard(uid)

    async def grafana_save_dashboard(self, dashboard: dict[str, Any], message: str,
                                     folder: str | None = DASHBOARD_FOLDER) -> dict[str, Any]:
        if not isinstance(dashboard, dict) or not dashboard.get("title"):
            raise ToolError("Dashboard-JSON mit mindestens „title“ erwartet.")
        dashboard = {**dashboard}
        dashboard.pop("id", None)  # Grafana ordnet über die uid zu
        folder_uid = await self._grafana.ensure_folder(folder) if folder else None
        result = await self._grafana.save_dashboard(dashboard, folder_uid, message or "Über MCP gespeichert")
        await self._log("dashboard_gespeichert", {"uid": result.get("uid"), "titel": dashboard.get("title"),
                                                  "version": result.get("version"), "nachricht": message})
        return {key: result.get(key) for key in ("uid", "url", "version", "status")}

    async def grafana_delete_dashboard(self, uid: str) -> dict[str, Any]:
        result = await self._grafana.delete_dashboard(uid)
        await self._log("dashboard_geloescht", {"uid": uid})
        return result
