"""Sicherungen der Datenbank als `pg_dump`-Archiv unter /data/backup.

Stand M5-Vorzug: automatische Sicherung vor jeder schreibenden MCP-Aktion
(Präfix `mcp_`) und von Hand über MCP (`manuell_`). Die HA-Backup-Anbindung,
Download und Wiederherstellung folgen mit M2 auf derselben Grundlage.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from display_time import format_berlin

log = logging.getLogger(__name__)

BACKUP_DIR = Path(os.environ.get("SKYTECH_BACKUP_DIR", "/data/backup"))
# So viele automatische Sicherungen je Präfix bleiben liegen; ältere werden gelöscht.
KEEP_PER_PREFIX = 20
DUMP_TIMEOUT_S = 1800


class BackupError(RuntimeError):
    """pg_dump ist fehlgeschlagen – die auslösende Aktion darf dann nicht laufen."""


@dataclass(frozen=True)
class BackupFile:
    name: str
    size_bytes: int
    created: datetime

    def to_json(self) -> dict:
        return {"datei": self.name, "groesse_bytes": self.size_bytes,
                "erstellt": format_berlin(self.created), "erstellt_iso": self.created.isoformat()}


def dump_command(target: Path) -> list[str]:
    """pg_dump als Betriebssystem-Benutzer postgres über den lokalen Socket."""
    command = ["pg_dump", "--format=custom", "--no-password", f"--file={target}",
               "--host=/run/postgresql", "--username=postgres", "skytech"]
    if os.geteuid() == 0:
        command = ["s6-setuidgid", "postgres", *command]
    return command


async def create(prefix: str, directory: Path = BACKUP_DIR) -> BackupFile:
    """Legt eine Sicherung an und räumt ältere mit gleichem Präfix auf."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    target = directory / f"{prefix}_{stamp}.dump"
    process = await asyncio.create_subprocess_exec(
        *dump_command(target), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), DUMP_TIMEOUT_S)
    except asyncio.TimeoutError as exc:
        process.kill()
        raise BackupError("Sicherung dauerte zu lange und wurde abgebrochen.") from exc
    if process.returncode != 0:
        target.unlink(missing_ok=True)
        message = stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["unbekannter Fehler"]
        raise BackupError(f"Sicherung fehlgeschlagen: {message[0]}")
    prune(prefix, directory)
    stat = target.stat()
    log.info("Sicherung %s angelegt (%d Bytes).", target.name, stat.st_size)
    return BackupFile(target.name, stat.st_size, datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc))


def list_backups(directory: Path = BACKUP_DIR) -> list[BackupFile]:
    """Alle Sicherungen, neueste zuerst."""
    if not directory.is_dir():
        return []
    files = []
    for path in directory.glob("*.dump"):
        stat = path.stat()
        files.append(BackupFile(path.name, stat.st_size, datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)))
    return sorted(files, key=lambda item: item.created, reverse=True)


def prune(prefix: str, directory: Path = BACKUP_DIR, keep: int = KEEP_PER_PREFIX) -> list[str]:
    """Löscht die ältesten Sicherungen eines Präfixes über `keep` hinaus."""
    matching = sorted(directory.glob(f"{prefix}_*.dump"), key=lambda path: path.name, reverse=True)
    removed = []
    for path in matching[keep:]:
        path.unlink(missing_ok=True)
        removed.append(path.name)
    return removed
