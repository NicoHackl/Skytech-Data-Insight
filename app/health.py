"""Zustand der Dienste im Container: Datenbank und Grafana.

Jede Prüfung hat ein eigenes Timeout und wirft nie – ein ausgefallener Dienst
ist ein Ergebnis, kein Fehler des Verwaltungsdienstes.
"""

import asyncio
import logging
from dataclasses import asdict, dataclass
from typing import Awaitable, Callable

import aiohttp
import asyncpg

log = logging.getLogger(__name__)

PROBE_TIMEOUT_S = 3.0
POSTGRES_SOCKET_DIR = "/run/postgresql"
POSTGRES_DATABASE = "skytech"
POSTGRES_USER = "skytech_app"
GRAFANA_BASE_URL = "http://127.0.0.1:3001"


@dataclass
class ServiceHealth:
    """Ergebnis einer Dienstprüfung, so wie es die Oberfläche anzeigt."""

    key: str
    label: str
    is_ok: bool
    detail: str

    def to_json(self) -> dict:
        return asdict(self)


async def probe_database() -> ServiceHealth:
    """Verbindet sich über den lokalen Socket und liest die Versionen."""
    label = "Datenbank"
    try:
        connection = await asyncpg.connect(
            host=POSTGRES_SOCKET_DIR,
            user=POSTGRES_USER,
            database=POSTGRES_DATABASE,
            timeout=PROBE_TIMEOUT_S,
        )
    except (OSError, asyncpg.PostgresError, asyncio.TimeoutError) as exc:
        log.warning("Datenbank nicht erreichbar: %s", exc)
        return ServiceHealth("database", label, False, "Nicht erreichbar")
    try:
        server_version = await connection.fetchval("SHOW server_version")
        timescale_version = await connection.fetchval(
            "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
        )
    except asyncpg.PostgresError as exc:
        log.warning("Datenbankabfrage fehlgeschlagen: %s", exc)
        return ServiceHealth("database", label, False, "Abfrage fehlgeschlagen")
    finally:
        await connection.close()
    return describe_database(server_version, timescale_version)


def describe_database(server_version: str, timescale_version: str | None) -> ServiceHealth:
    """Baut das Ergebnis aus den gelesenen Versionen."""
    # `SHOW server_version` liefert z. B. „17.11 (Debian 17.11-1.pgdg12+2)".
    postgres = server_version.split(" ", 1)[0]
    if not timescale_version:
        return ServiceHealth("database", "Datenbank", False, f"PostgreSQL {postgres}, TimescaleDB fehlt")
    return ServiceHealth(
        "database", "Datenbank", True, f"PostgreSQL {postgres} · TimescaleDB {timescale_version}"
    )


async def probe_grafana(session: aiohttp.ClientSession, ingress_entry: str) -> ServiceHealth:
    """Fragt den Health-Endpunkt von Grafana unter dessen Sub-Pfad ab."""
    url = f"{GRAFANA_BASE_URL}{ingress_entry}/grafana/api/health"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=PROBE_TIMEOUT_S)) as response:
            payload = await response.json(content_type=None) if response.status == 200 else None
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        log.warning("Grafana nicht erreichbar: %s", exc)
        return ServiceHealth("grafana", "Grafana", False, "Nicht erreichbar")
    return describe_grafana(payload)


def describe_grafana(payload: dict | None) -> ServiceHealth:
    """Bewertet die Antwort von `/api/health`."""
    if not isinstance(payload, dict):
        return ServiceHealth("grafana", "Grafana", False, "Ungültige Antwort")
    version = payload.get("version") or "unbekannt"
    if payload.get("database") != "ok":
        return ServiceHealth("grafana", "Grafana", False, f"Version {version}, interne Datenbank gestört")
    return ServiceHealth("grafana", "Grafana", True, f"Version {version}")


async def collect(probes: list[Callable[[], Awaitable[ServiceHealth]]]) -> list[ServiceHealth]:
    """Führt alle Prüfungen parallel aus; die Reihenfolge bleibt erhalten."""
    return list(await asyncio.gather(*(probe() for probe in probes)))
