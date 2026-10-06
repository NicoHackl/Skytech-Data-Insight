"""Aufbewahrung und Speicherplatz – gemeinsam für Oberfläche und MCP.

Die Aufbewahrung steht in `skytech_config.einstellung` und wird von
`skytech_config.aufbewahrung_anwenden()` umgesetzt (docs/datenmodell.md).
Sicherung und Protokoll übernimmt der Aufrufer, weil sich Art der Sicherung und
Quelle des Protokolleintrags zwischen Oberfläche und MCP unterscheiden.
"""

import json
from typing import Any

import asyncpg

MIN_MINUTE_DAYS = 31
_RAW_KEY = "aufbewahrung_rohwerte_tage"
_MINUTE_KEY = "aufbewahrung_minutenwerte_tage"

# Hypertables und Verdichtungen; Letztere liegen als interne Hypertable vor,
# die timescaledb_information.hypertables nicht aufführt.
_STORAGE_SQL = """
WITH t AS (
    SELECT hypertable_name AS name, hypertable_schema AS schema_name, hypertable_name AS table_name
    FROM timescaledb_information.hypertables WHERE hypertable_schema = 'skytech'
    UNION ALL
    SELECT view_name, materialization_hypertable_schema, materialization_hypertable_name
    FROM timescaledb_information.continuous_aggregates WHERE view_schema = 'skytech'
)
SELECT t.name,
       hypertable_size(format('%I.%I', t.schema_name, t.table_name)::regclass) AS bytes,
       count(c.chunk_name) AS chunks,
       count(c.chunk_name) FILTER (WHERE c.is_compressed) AS komprimiert
FROM t
LEFT JOIN timescaledb_information.chunks c
       ON c.hypertable_schema = t.schema_name AND c.hypertable_name = t.table_name
GROUP BY t.name, t.schema_name, t.table_name
ORDER BY array_position(ARRAY['messwert', 'messwert_1min', 'messwert_15min', 'messwert_1h', 'messwert_1d'], t.name::text)
         NULLS LAST, t.name
"""

# Rohwerte je Berliner Tag: die letzten sieben vollständigen Tage plus heute.
_DAILY_SQL = """
SELECT to_char(date_trunc('day', zeit AT TIME ZONE 'Europe/Berlin'), 'DD.MM.YYYY') AS tag,
       count(*) AS rohwerte,
       date_trunc('day', zeit AT TIME ZONE 'Europe/Berlin') = date_trunc('day', now() AT TIME ZONE 'Europe/Berlin') AS heute
FROM skytech.messwert
WHERE zeit >= (date_trunc('day', now() AT TIME ZONE 'Europe/Berlin') - interval '7 days') AT TIME ZONE 'Europe/Berlin'
GROUP BY date_trunc('day', zeit AT TIME ZONE 'Europe/Berlin')
ORDER BY date_trunc('day', zeit AT TIME ZONE 'Europe/Berlin')
"""


class RetentionError(ValueError):
    """Ungültige oder nicht anwendbare Aufbewahrung; `field_errors` wie in der API."""

    def __init__(self, message: str, field_errors: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.field_errors = field_errors or {}


def _days(value: Any, field: str, minimum: int, errors: dict[str, str]) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        errors[field] = "Ganze Zahl in Tagen oder leer für „nie löschen“."
        return None
    if value < minimum:
        errors[field] = f"Mindestens {minimum} Tag{'e' if minimum > 1 else ''} oder leer für „nie löschen“."
    return value


def validate_retention(raw_days: Any, minute_days: Any) -> tuple[int | None, int | None]:
    """Prüft beide Werte; `None` heißt „nie löschen“."""
    errors: dict[str, str] = {}
    raw = _days(raw_days, "rohwerte_tage", 1, errors)
    minute = _days(minute_days, "minutenwerte_tage", MIN_MINUTE_DAYS, errors)
    if errors:
        raise RetentionError("Aufbewahrung ungültig.", errors)
    return raw, minute


async def read_retention(connection: asyncpg.Connection) -> dict[str, int | None]:
    rows = await connection.fetch(
        "SELECT schluessel, wert FROM skytech_config.einstellung WHERE schluessel = ANY($1::text[])",
        [_RAW_KEY, _MINUTE_KEY])
    values = {row["schluessel"]: json.loads(row["wert"]) for row in rows}
    return {"rohwerte_tage": values.get(_RAW_KEY), "minutenwerte_tage": values.get(_MINUTE_KEY)}


async def set_retention(connection: asyncpg.Connection, raw_days: int | None, minute_days: int | None) -> None:
    """Speichert und wendet an – ganz oder gar nicht."""
    try:
        async with connection.transaction():
            for key, value in ((_RAW_KEY, raw_days), (_MINUTE_KEY, minute_days)):
                await connection.execute(
                    "UPDATE skytech_config.einstellung SET wert = $1::jsonb, geaendert_am = now() WHERE schluessel = $2",
                    json.dumps(value), key)
            await connection.execute("SELECT skytech_config.aufbewahrung_anwenden()")
    except asyncpg.PostgresError as exc:
        raise RetentionError(f"Aufbewahrung nicht geändert: {exc}") from exc


async def storage(connection: asyncpg.Connection) -> dict[str, Any]:
    """Größe der Datenbank, je Tabelle und Verdichtung, Wachstum der Rohwerte."""
    database_bytes = await connection.fetchval("SELECT pg_database_size(current_database())")
    tables = [dict(row) for row in await connection.fetch(_STORAGE_SQL)]
    daily = [dict(row) for row in await connection.fetch(_DAILY_SQL)]
    # Hochrechnung aus den vollständigen Tagen (ohne heute); Größe je Rohwert aus der Tabelle selbst.
    complete = [row for row in daily if not row["heute"]] or daily
    per_day = sum(row["rohwerte"] for row in complete) / len(complete) if complete else 0
    raw_rows = await connection.fetchval("SELECT approximate_row_count('skytech.messwert')")
    raw_bytes = next((row["bytes"] for row in tables if row["name"] == "messwert"), 0)
    bytes_per_row = raw_bytes / raw_rows if raw_rows else 0
    return {
        "datenbank_bytes": database_bytes,
        "tabellen": tables,
        "rohwerte_je_tag": daily,
        "rohwerte_tag_mittel": round(per_day),
        "rohwerte_bytes_jahr": round(per_day * 365 * bytes_per_row),
    }
