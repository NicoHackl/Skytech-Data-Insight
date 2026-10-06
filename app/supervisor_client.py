"""Zugriff auf die EIGENEN Add-on-Optionen über die Supervisor-API (D-025).

Übernommen aus Skytech HEMS. `/data/options.json` wird nie beschrieben;
geschrieben wird über `http://supervisor/addons/self/…` – dieselbe Quelle, die
auch die Konfigurationsseite des Add-ons bedient. Das Schreiben der eigenen
Optionen braucht die Supervisor-Rolle `manager` (`hassio_role` in config.yaml).

Token, Header und Optionswerte erscheinen nie in Logs oder Fehlermeldungen –
die Optionen enthalten Passwörter.
"""

import logging
import os
from typing import Any

import aiohttp

log = logging.getLogger(__name__)

_TIMEOUT_S = 10


class SupervisorUnavailable(RuntimeError):
    """Kein Supervisor: lokaler Test oder Supervisor nicht erreichbar."""


class SupervisorRejected(RuntimeError):
    """Der Supervisor hat die Anfrage fachlich abgelehnt."""


class SupervisorPermissionDenied(SupervisorRejected):
    """Der Supervisor verweigert den Aufruf wegen der Add-on-Rolle."""


class SupervisorClient:
    def __init__(self, session: aiohttp.ClientSession, token: str | None = None, base_url: str | None = None) -> None:
        self._session = session
        self._token = os.environ.get("SUPERVISOR_TOKEN", "") if token is None else token
        self._base_url = (base_url or os.environ.get("SUPERVISOR_URL", "http://supervisor")).rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self._token)

    async def self_info(self) -> dict[str, Any]:
        """Add-on-Informationen inklusive Optionen und Portzuordnung (`network`)."""
        return await self._request("GET", "/addons/self/info")

    async def network_info(self) -> dict[str, Any]:
        return await self._request("GET", "/network/info")

    async def validate_options(self, options: dict[str, Any]) -> None:
        """Prüft gegen das Schema aus config.yaml; der Endpunkt erwartet die rohen Optionen."""
        data = await self._request("POST", "/addons/self/options/validate", options)
        if not data.get("valid", False):
            raise SupervisorRejected(str(data.get("message") or "Optionen ungültig."))

    async def save_options(self, options: dict[str, Any]) -> None:
        """Speichert die vollständigen Optionen. Startet das Add-on NICHT neu."""
        await self._request("POST", "/addons/self/options", {"options": options})

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.available:
            raise SupervisorUnavailable("Kein Supervisor – das Add-on läuft außerhalb von Home Assistant.")
        try:
            async with self._session.request(
                method, f"{self._base_url}{path}", json=payload,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=aiohttp.ClientTimeout(total=_TIMEOUT_S),
            ) as response:
                try:
                    body = await response.json(content_type=None)
                except ValueError:
                    body = {}
                body = body if isinstance(body, dict) else {}
                if response.status == 403:
                    log.warning("Supervisor %s %s wegen fehlender Berechtigung abgelehnt.", method, path)
                    raise SupervisorPermissionDenied(
                        "Der Supervisor verweigert den Zugriff: dem Add-on fehlt die Rolle „manager“. "
                        "Add-on aktualisieren und neu starten.")
                if response.status >= 400 or body.get("result") == "error":
                    message = str(body.get("message") or f"HTTP {response.status}")
                    # Nur die Meldung, nie der gesendete Rumpf – er enthält Passwörter.
                    log.warning("Supervisor %s %s abgelehnt: %s", method, path, message)
                    raise SupervisorRejected(message)
                data = body.get("data")
                return data if isinstance(data, dict) else {}
        except aiohttp.ClientError as exc:
            log.error("Supervisor %s %s nicht erreichbar: %s", method, path, exc)
            raise SupervisorUnavailable("Der Supervisor ist nicht erreichbar.") from exc
