"""Sicherungen und Wiederherstellung (M2, D-023).

- `create()`: pg_dump-Archiv unter /data/backup (automatisch vor MCP-Änderungen,
  von Hand, vor einer Wiederherstellung).
- `build_archive()`: Download-Paket (.tar) mit Datenbank, Grafana-Datenbank und
  Beschreibung – unabhängig von Home Assistant nutzbar.
- `inspect()`: prüft eine hochgeladene Datei (.tar oder .dump), bevor sie
  irgendetwas ersetzt.
- `Restorer`: spielt eine Sicherung ein. Die Datenbank ersetzt
  `/usr/lib/skytech/restore-db.sh`; danach starten Verwaltungsdienst und
  MCP-Server neu, damit keine Verbindung auf die alte Datenbank zeigt.

Die Sicherung vor einem HA-Backup schreibt `/usr/bin/skytech-backup-pre`.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import sqlite3
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from display_time import format_berlin

log = logging.getLogger(__name__)

BACKUP_DIR = Path(os.environ.get("SKYTECH_BACKUP_DIR", "/data/backup"))
GRAFANA_DB = Path("/data/grafana/grafana.db")
RESTORE_SCRIPT = "/usr/lib/skytech/restore-db.sh"
STATE_FILE_NAME = "wiederherstellung.json"
DUMP_TIMEOUT_S = 1800
RESTORE_TIMEOUT_S = 3600

# Wie viele Sicherungen je Art liegen bleiben; ältere werden gelöscht.
KEEP = {"mcp": 20, "manuell": 20, "vor_aenderung": 10, "vor_wiederherstellung": 5, "upload": 5,
        "ha_wiederhergestellt": 3}
KEEP_PER_PREFIX = 20

KINDS = {
    "mcp": "Vor MCP-Änderung",
    "manuell": "Manuell",
    "vor_aenderung": "Vor Änderung in der Oberfläche",
    "vor_wiederherstellung": "Vor Wiederherstellung",
    "upload": "Hochgeladen",
    "ha_wiederhergestellt": "Aus HA-Backup eingespielt",
    "ha_snapshot": "HA-Backup (in Arbeit)",
}
FILE_NAME = re.compile(r"^([a-z_]+?)_(\d{8}_\d{6}(?:_\d+)?)\.(dump|tar)$")
ARCHIVE_DB = "datenbank.dump"
ARCHIVE_GRAFANA = "grafana.db"
ARCHIVE_MANIFEST = "sicherung.json"


class BackupError(RuntimeError):
    """Sicherung oder Wiederherstellung ist fehlgeschlagen."""


@dataclass(frozen=True)
class BackupFile:
    name: str
    size_bytes: int
    created: datetime

    @property
    def kind(self) -> str:
        match = FILE_NAME.match(self.name)
        return match.group(1) if match else "unbekannt"

    def to_json(self) -> dict:
        return {"datei": self.name, "art": self.kind, "art_text": KINDS.get(self.kind, "Sonstige"),
                "groesse_bytes": self.size_bytes, "erstellt": format_berlin(self.created),
                "erstellt_iso": self.created.isoformat()}


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _as_postgres(command: list[str]) -> list[str]:
    return ["s6-setuidgid", "postgres", *command] if os.geteuid() == 0 else command


def dump_command(target: Path) -> list[str]:
    """pg_dump als Betriebssystem-Benutzer postgres über den lokalen Socket."""
    return _as_postgres(["pg_dump", "--format=custom", "--no-password", f"--file={target}",
                         "--host=/run/postgresql", "--username=postgres", "skytech"])


async def _run(command: list[str], timeout: float) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout)
    except asyncio.TimeoutError as exc:
        process.kill()
        raise BackupError("Zeitlimit überschritten.") from exc
    return process.returncode or 0, output.decode("utf-8", "replace")


def _last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else "unbekannter Fehler"


def _file(path: Path) -> BackupFile:
    stat = path.stat()
    return BackupFile(path.name, stat.st_size, datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc))


async def create(prefix: str, directory: Path = BACKUP_DIR) -> BackupFile:
    """Legt eine Sicherung an und räumt ältere mit gleichem Präfix auf."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{prefix}_{_stamp()}.dump"
    code, output = await _run(dump_command(target), DUMP_TIMEOUT_S)
    if code != 0:
        target.unlink(missing_ok=True)
        raise BackupError(f"Sicherung fehlgeschlagen: {_last_line(output)}")
    prune(prefix, directory)
    log.info("Sicherung %s angelegt (%d Bytes).", target.name, target.stat().st_size)
    return _file(target)


def list_backups(directory: Path = BACKUP_DIR) -> list[BackupFile]:
    """Alle Sicherungen, neueste zuerst."""
    if not directory.is_dir():
        return []
    files = [_file(path) for path in directory.iterdir() if path.is_file() and FILE_NAME.match(path.name)]
    return sorted(files, key=lambda item: item.created, reverse=True)


def prune(prefix: str, directory: Path = BACKUP_DIR, keep: int | None = None) -> list[str]:
    """Löscht die ältesten Sicherungen eines Präfixes über `keep` hinaus."""
    keep = KEEP.get(prefix, KEEP_PER_PREFIX) if keep is None else keep
    matching = sorted((p for p in directory.glob(f"{prefix}_*") if FILE_NAME.match(p.name)
                       and FILE_NAME.match(p.name).group(1) == prefix), key=lambda p: p.name, reverse=True)
    removed = []
    for path in matching[keep:]:
        path.unlink(missing_ok=True)
        removed.append(path.name)
    return removed


def resolve(name: str, directory: Path = BACKUP_DIR) -> Path:
    """Dateiname aus einer Anfrage → Pfad. Nur bekannte Namensmuster, kein Pfad."""
    if not FILE_NAME.match(name):
        raise BackupError("Unbekannte Sicherung.")
    path = directory / name
    if not path.is_file():
        raise BackupError("Sicherung nicht gefunden.")
    return path


def copy_grafana_db(target: Path, source: Path = GRAFANA_DB) -> bool:
    """Konsistente Kopie der Grafana-Datenbank (SQLite-Online-Backup)."""
    if not source.is_file():
        return False
    reader = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    writer = sqlite3.connect(target)
    try:
        reader.backup(writer)
    finally:
        writer.close()
        reader.close()
    return True


async def build_archive(version: str, directory: Path = BACKUP_DIR, grafana_db: Path = GRAFANA_DB) -> Path:
    """Download-Paket: Datenbank-Dump, Grafana-Datenbank, Beschreibung. Aufrufer löscht es."""
    dump = await create("download", directory)
    work = directory / f"download_{_stamp()}.tmp"
    work.mkdir()
    try:
        has_grafana = copy_grafana_db(work / ARCHIVE_GRAFANA, grafana_db)
        manifest = {"format": 1, "addon": "Skytech Data Insight", "version": version,
                    "erstellt": format_berlin(dump.created), "erstellt_iso": dump.created.isoformat(),
                    "inhalt": [ARCHIVE_DB] + ([ARCHIVE_GRAFANA] if has_grafana else [])}
        (work / ARCHIVE_MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        archive = directory / f"download_{_stamp()}.tar"
        with tarfile.open(archive, "w") as tar:
            tar.add(work / ARCHIVE_MANIFEST, ARCHIVE_MANIFEST)
            tar.add(directory / dump.name, ARCHIVE_DB)
            if has_grafana:
                tar.add(work / ARCHIVE_GRAFANA, ARCHIVE_GRAFANA)
        return archive
    finally:
        shutil.rmtree(work, ignore_errors=True)
        (directory / dump.name).unlink(missing_ok=True)


async def validate_dump(path: Path) -> None:
    code, output = await _run(_as_postgres(["pg_restore", "--list", str(path)]), 300)
    if code != 0:
        raise BackupError(f"Keine gültige Datenbanksicherung: {_last_line(output)}")


async def inspect(path: Path) -> dict[str, Any]:
    """Prüft eine Sicherung (.dump oder .tar aus dem Download) und beschreibt sie."""
    info: dict[str, Any] = {"datei": path.name, "groesse_bytes": path.stat().st_size, "grafana": False, "beschreibung": None}
    if path.suffix == ".tar":
        try:
            with tarfile.open(path) as tar:
                names = set(tar.getnames())
                if ARCHIVE_DB not in names:
                    raise BackupError(f"Im Paket fehlt {ARCHIVE_DB}.")
                info["grafana"] = ARCHIVE_GRAFANA in names
                if ARCHIVE_MANIFEST in names:
                    member = tar.extractfile(ARCHIVE_MANIFEST)
                    info["beschreibung"] = json.load(member) if member else None
        except tarfile.TarError as exc:
            raise BackupError(f"Kein gültiges Sicherungspaket: {exc}") from exc
        return info
    await validate_dump(path)
    return info


def read_state(directory: Path = BACKUP_DIR) -> dict[str, Any] | None:
    path = directory / STATE_FILE_NAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_state(state: dict[str, Any], directory: Path = BACKUP_DIR) -> None:
    path = directory / STATE_FILE_NAME
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


class Restorer:
    """Spielt eine Sicherung ein. Genau ein Auftrag gleichzeitig."""

    def __init__(self, directory: Path = BACKUP_DIR, grafana_db: Path = GRAFANA_DB,
                 run: Callable[[list[str], float], Awaitable[tuple[int, str]]] = _run) -> None:
        self._directory = directory
        self._grafana_db = grafana_db
        self._run = run
        self._lock = asyncio.Lock()

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    async def restore(self, source: Path, user: str | None, before_restore: Callable[[], Awaitable[None]]) -> dict:
        """Sicherung vorher, Dienste anhalten, Datenbank (und Grafana) ersetzen, Zustand festhalten."""
        if self._lock.locked():
            raise BackupError("Es läuft bereits eine Wiederherstellung.")
        async with self._lock:
            state = {"status": "laeuft", "datei": source.name, "benutzer": user,
                     "gestartet": format_berlin(datetime.now(timezone.utc)), "meldung": None, "protokolliert": False}
            write_state(state, self._directory)
            work = self._directory / f"wiederherstellung_{_stamp()}.tmp"
            try:
                safety = await create("vor_wiederherstellung", self._directory)
                state["sicherung_vorher"] = safety.name
                dump, grafana = self._unpack(source, work)
                await before_restore()
                code, output = await self._run(["/usr/lib/skytech/restore-db.sh", str(dump)], RESTORE_TIMEOUT_S)
                if code != 0:
                    raise BackupError(f"Einspielen fehlgeschlagen: {_last_line(output)}")
                if grafana is not None:
                    await self._replace_grafana(grafana)
                state.update(status="erfolgreich", meldung="Sicherung eingespielt.")
            except Exception as exc:  # noqa: BLE001 – jeder Fehler muss im Zustand landen, sonst bleibt „läuft" stehen
                state.update(status="fehlgeschlagen", meldung=str(exc) or type(exc).__name__)
                log.exception("Wiederherstellung fehlgeschlagen.")
            finally:
                shutil.rmtree(work, ignore_errors=True)
                state["beendet"] = format_berlin(datetime.now(timezone.utc))
                write_state(state, self._directory)
            return state

    def _unpack(self, source: Path, work: Path) -> tuple[Path, Path | None]:
        if source.suffix != ".tar":
            return source, None
        work.mkdir()
        with tarfile.open(source) as tar:
            names = tar.getnames()
            for name in (ARCHIVE_DB, ARCHIVE_GRAFANA):
                if name not in names:
                    continue
                # Nur die bekannten Einträge und nur als Datei auspacken –
                # kein tar.extract(), damit Pfade im Archiv keine Rolle spielen.
                member = tar.extractfile(name)
                if member is None:
                    raise BackupError(f"{name} im Paket ist keine Datei.")
                with member, (work / name).open("wb") as target:
                    shutil.copyfileobj(member, target)
        # restore-db.sh liest den Dump als postgres.
        if os.geteuid() == 0:
            shutil.chown(work, "postgres")
        grafana = work / ARCHIVE_GRAFANA
        return work / ARCHIVE_DB, grafana if grafana.is_file() else None

    async def _replace_grafana(self, source: Path) -> None:
        """Grafana anhalten, Datenbank tauschen, wieder starten."""
        await self._run(["s6-svc", "-d", "/run/service/grafana"], 60)
        await self._run(["s6-svwait", "-D", "-t", "30000", "/run/service/grafana"], 40)
        shutil.copyfile(source, self._grafana_db)
        if os.geteuid() == 0:
            shutil.chown(self._grafana_db, "grafana", "grafana")
        await self._run(["s6-svc", "-u", "/run/service/grafana"], 60)


async def restart_services() -> None:
    """Startet MCP-Server und Verwaltungsdienst neu (dieser Prozess endet dabei)."""
    for service in ("mcp", "app"):
        process = await asyncio.create_subprocess_exec("s6-svc", "-r", f"/run/service/{service}")
        await process.wait()
