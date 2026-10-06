"""Zugänge im LAN: Status anzeigen, Secrets neu erzeugen oder sperren (D-025).

Gespeichert wird in den Add-on-Optionen über die Supervisor-API – dieselbe
Quelle wie die Konfigurationsseite, damit es keine zweite Wahrheit gibt.
Danach wirkt die Änderung ohne Neustart des Add-ons:

- Datenbank: `ALTER ROLE … PASSWORD` als postgres (set_password.sql),
- Grafana: `grafana cli admin reset-admin-password`,
- MCP: Neustart nur des MCP-Dienstes; er liest die Option beim Start über die
  Supervisor-API, weil /data/options.json erst beim nächsten Add-on-Start
  neu geschrieben wird.

Ein Secret verlässt diesen Dienst genau einmal: in der Antwort auf „neu
erzeugen“. Es steht nie in Logs, im Protokoll oder in einer Kommandozeile.
"""

import asyncio
import logging
import os
import secrets
from dataclasses import dataclass
from typing import Any

import backup
from supervisor_client import SupervisorClient

log = logging.getLogger(__name__)

SET_PASSWORD_SQL = "/usr/share/skytech/set_password.sql"
GRAFANA_HOME = "/usr/share/grafana"
GRAFANA_CONFIG = "/run/skytech/grafana/grafana.ini"
MCP_SERVICE = "/run/service/mcp"
MCP_MIN_TOKEN = 16
_APPLY_TIMEOUT_S = 60


@dataclass(frozen=True)
class Access:
    key: str
    label: str
    option: str
    port: str
    user: str | None
    role: str | None = None


ACCESSES = (
    Access("datenbank", "Datenbank – Vollzugriff", "db_password", "5432/tcp", "skytech_admin", "skytech_admin"),
    Access("datenbank_lesen", "Datenbank – nur lesen", "db_readonly_password", "5432/tcp", "skytech_reader", "skytech_reader"),
    Access("grafana", "Grafana im LAN", "grafana_admin_password", "3000/tcp", "admin"),
    Access("mcp", "MCP-Server", "mcp_token", "8765/tcp", None),
)
BY_KEY = {access.key: access for access in ACCESSES}


class AccessError(RuntimeError):
    """Gespeichert oder angewendet werden konnte nicht; Text für die Oberfläche."""


def new_secret() -> str:
    """32 Zeichen aus Buchstaben, Ziffern, „-“ und „_“ – in URLs und Shells ohne Maskierung nutzbar."""
    return secrets.token_urlsafe(24)


def is_set(access: Access, value: Any) -> bool:
    text = value if isinstance(value, str) else ""
    return len(text) >= MCP_MIN_TOKEN if access.key == "mcp" else bool(text)


def primary_address(network: dict[str, Any]) -> str | None:
    """IPv4-Adresse der primären Schnittstelle des HA-Hosts, ohne Präfixlänge."""
    for interface in network.get("interfaces") or []:
        if not interface.get("primary"):
            continue
        addresses = (interface.get("ipv4") or {}).get("address") or []
        if addresses:
            return str(addresses[0]).split("/", 1)[0]
    return None


async def overview(supervisor: SupervisorClient) -> dict[str, Any]:
    """Status je Zugang. Ohne Supervisor (lokaler Test): `verfuegbar = False`."""
    if not supervisor.available:
        return {"verfuegbar": False, "host": None,
                "zugaenge": [_describe(access, None, None) for access in ACCESSES]}
    info = await supervisor.self_info()
    try:
        host = primary_address(await supervisor.network_info())
    except RuntimeError as exc:
        log.info("Adresse des HA-Hosts nicht ermittelbar: %s", exc)
        host = None
    options = info.get("options") or {}
    ports = info.get("network") or {}
    return {"verfuegbar": True, "host": host,
            "zugaenge": [_describe(access, is_set(access, options.get(access.option)), ports.get(access.port))
                         for access in ACCESSES]}


def _describe(access: Access, configured: bool | None, host_port: Any) -> dict[str, Any]:
    return {"schluessel": access.key, "bezeichnung": access.label, "option": access.option,
            "benutzer": access.user, "gesetzt": configured,
            "port": host_port if isinstance(host_port, int) else None}


async def change(supervisor: SupervisorClient, key: str, secret: str) -> None:
    """Setzt (oder leert mit `""`) das Secret eines Zugangs und wendet es an."""
    access = BY_KEY[key]
    info = await supervisor.self_info()
    # Immer die vollständigen Optionen schicken – der Supervisor ersetzt sie als Ganzes.
    options = {**(info.get("options") or {}), access.option: secret}
    await supervisor.validate_options(options)
    await supervisor.save_options(options)
    try:
        await _apply(access, secret)
    except AccessError as exc:
        raise AccessError(f"{exc} Gespeichert ist die Änderung trotzdem – sie wirkt nach einem Neustart des Add-ons.") from exc


async def _apply(access: Access, secret: str) -> None:
    if access.role:
        command = backup.as_postgres(["psql", "--no-psqlrc", "--quiet", "--host=/run/postgresql", "--username=postgres",
                                      "--dbname=skytech", f"--file={SET_PASSWORD_SQL}"])
        await _run(command, f"Passwort von {access.role}", env={"SKYTECH_ROLE": access.role, "SKYTECH_PASSWORD": secret})
    elif access.key == "grafana":
        # Leer = gesperrt: wie beim Start ein Zufallspasswort, das niemand kennt.
        password = secret or new_secret() + new_secret()
        command = ["s6-setuidgid", "grafana", "grafana", "cli", "--homepath", GRAFANA_HOME, "--config", GRAFANA_CONFIG,
                   "admin", "reset-admin-password", "--password-from-stdin"]
        await _run(command, "Grafana-Passwort", stdin=password)
    elif access.key == "mcp":
        await _run(["s6-svc", "-r", MCP_SERVICE], "Neustart des MCP-Servers")


async def _run(command: list[str], what: str, env: dict[str, str] | None = None, stdin: str | None = None) -> None:
    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL, env={**os.environ, **(env or {})})
    except OSError as exc:
        log.error("%s: %s nicht ausführbar (%s).", what, command[0], exc.strerror)
        raise AccessError(f"{what} ließ sich nicht setzen.") from exc
    try:
        await asyncio.wait_for(process.communicate(stdin.encode() if stdin is not None else None), _APPLY_TIMEOUT_S)
    except asyncio.TimeoutError as exc:
        process.kill()
        raise AccessError(f"{what}: Zeitlimit überschritten.") from exc
    if process.returncode != 0:
        # Ausgabe bewusst verworfen: psql kann die fehlgeschlagene Anweisung samt Passwort wiederholen.
        log.error("%s fehlgeschlagen (Rückgabewert %s).", what, process.returncode)
        raise AccessError(f"{what} ließ sich nicht setzen.")
