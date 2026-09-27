"""Migrationen der Datenbank.

Zwei Quellen, gemeinsam nummeriert:
- System-Migrationen im Image (`app/sql/NNNN_name.sql`),
- Anlagen-Migrationen in `/data/migrations/NNNN_name.sql` (von Hand, später per
  Oberfläche oder MCP angelegt; liegen in `/data` und damit im Backup).

Jede Datei läuft genau einmal, in einer eigenen Transaktion, als skytech_app.
Die Prüfsumme wird gespeichert: ändert sich eine bereits angewendete Datei,
bricht der Lauf ab, statt still einen anderen Stand anzunehmen.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import asyncpg

log = logging.getLogger(__name__)

SYSTEM_DIR = Path(__file__).parent / "sql"
SITE_DIR = Path("/data/migrations")
_FILE_PATTERN = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


class MigrationError(RuntimeError):
    """Eine Migration ist fehlgeschlagen oder passt nicht zum gespeicherten Stand."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    source: str
    path: Path

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def discover(system_dir: Path = SYSTEM_DIR, site_dir: Path = SITE_DIR) -> list[Migration]:
    """Findet alle Migrationen, sortiert nach Nummer. Doppelte Nummern sind ein Fehler."""
    found: dict[int, Migration] = {}
    for source, directory in (("system", system_dir), ("anlage", site_dir)):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            match = _FILE_PATTERN.match(path.name)
            if not match:
                if path.suffix == ".sql":
                    log.warning("Migrationsdatei %s ignoriert: Name muss NNNN_name.sql lauten.", path)
                continue
            version = int(match.group(1))
            if version in found:
                raise MigrationError(
                    f"Migrationsnummer {version:04d} doppelt: {found[version].path} und {path}."
                )
            found[version] = Migration(version, match.group(2), source, path)
    return [found[version] for version in sorted(found)]


async def _applied(connection: asyncpg.Connection) -> dict[int, str]:
    exists = await connection.fetchval("SELECT to_regclass('skytech_config.migration') IS NOT NULL")
    if not exists:
        return {}
    rows = await connection.fetch("SELECT version, checksumme FROM skytech_config.migration")
    return {row["version"]: row["checksumme"] for row in rows}


async def migrate(connection: asyncpg.Connection, migrations: list[Migration]) -> list[Migration]:
    """Wendet alle offenen Migrationen an und gibt sie zurück."""
    applied = await _applied(connection)
    for migration in migrations:
        stored = applied.get(migration.version)
        if stored is not None and stored != migration.checksum:
            raise MigrationError(
                f"Migration {migration.path.name} wurde nach dem Anwenden verändert. "
                "Angewendete Migrationen dürfen nicht geändert werden – Änderung als neue Migration anlegen."
            )
    pending = [m for m in migrations if m.version not in applied]
    for migration in pending:
        log.info("Wende Migration %s an …", migration.path.name)
        try:
            async with connection.transaction():
                await connection.execute(migration.sql)
                await connection.execute(
                    "INSERT INTO skytech_config.migration (version, name, quelle, checksumme) VALUES ($1, $2, $3, $4)",
                    migration.version, migration.name, migration.source, migration.checksum,
                )
        except asyncpg.PostgresError as exc:
            raise MigrationError(f"Migration {migration.path.name} fehlgeschlagen: {exc}") from exc
    return pending
