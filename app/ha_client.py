"""Einzige Stelle mit Zugriff auf Home Assistant: WebSocket-API über den Supervisor.

Der Client hält eine Verbindung, meldet sich an, abonniert `state_changed`,
führt ein Zustandsabbild aller Entitäten und verbindet sich nach Abbrüchen mit
wachsender Wartezeit neu. Nach jeder (Neu-)Verbindung ruft er `on_connected`
auf – dort gleicht der Collector Zustände ab und lädt Lücken nach.

Referenz: https://developers.home-assistant.io/docs/api/websocket
"""

import asyncio
import itertools
import logging
import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import aiohttp

log = logging.getLogger(__name__)

SUPERVISOR_WS_URL = "ws://supervisor/core/websocket"
CALL_TIMEOUT_S = 60
_RECONNECT_DELAYS_S = (1, 2, 5, 10, 30)

StateCallback = Callable[[dict[str, Any]], None]
ConnectedCallback = Callable[[], Awaitable[None]]


class HAError(RuntimeError):
    """Home Assistant hat einen Befehl abgelehnt oder ist nicht verbunden."""


def connection_settings() -> tuple[str, str] | None:
    """URL und Token: im Add-on über den Supervisor, lokal über SKYTECH_HA_URL/_TOKEN."""
    url = os.environ.get("SKYTECH_HA_URL")
    token = os.environ.get("SKYTECH_HA_TOKEN")
    if url and token:
        return url, token
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
    if supervisor_token:
        return SUPERVISOR_WS_URL, supervisor_token
    return None


def parse_timestamp(raw: Any) -> datetime | None:
    """HA liefert ISO-Zeichenketten (Ereignisse) oder Epoch-Sekunden (Verlauf)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    try:
        moment = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def normalize_history(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bringt Verlaufseinträge in die Form eines Zustandsobjekts.

    Der Verlauf kommt verdichtet (`s`, `a`, `lc`, `lu`); `lc` fehlt, wenn es
    `lu` gleicht, und `a` fehlt, wenn sich die Attribute nicht geändert haben.
    """
    normalized = []
    attributes: dict[str, Any] = {}
    for entry in entries:
        if "s" in entry or "lu" in entry:
            last_updated = entry.get("lu")
            last_changed = entry.get("lc", last_updated)
            state = entry.get("s")
            if "a" in entry:
                attributes = entry["a"] or {}
        else:
            last_updated = entry.get("last_updated")
            last_changed = entry.get("last_changed", last_updated)
            state = entry.get("state")
            if "attributes" in entry:
                attributes = entry["attributes"] or {}
        normalized.append({
            "state": state,
            "attributes": attributes,
            "last_changed": parse_timestamp(last_changed),
            "last_updated": parse_timestamp(last_updated),
        })
    return normalized


class HAClient:
    def __init__(self, url: str, token: str, on_state_changed: StateCallback,
                 on_connected: ConnectedCallback) -> None:
        self._url = url
        self._token = token
        self._on_state_changed = on_state_changed
        self._on_connected = on_connected
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._websocket: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self.states: dict[str, dict[str, Any]] = {}
        self.connected = False
        self.last_error: str | None = None

    async def run(self) -> None:
        """Hält die Verbindung dauerhaft aufrecht. Endet nur durch Abbruch."""
        self._session = aiohttp.ClientSession()
        attempt = 0
        try:
            while True:
                try:
                    await self._connect_and_listen()
                    attempt = 0
                except asyncio.CancelledError:
                    raise
                except (aiohttp.ClientError, HAError, asyncio.TimeoutError, OSError) as exc:
                    self.last_error = str(exc) or type(exc).__name__
                    log.warning("Verbindung zu Home Assistant getrennt: %s", self.last_error)
                finally:
                    self._disconnected()
                delay = _RECONNECT_DELAYS_S[min(attempt, len(_RECONNECT_DELAYS_S) - 1)]
                attempt += 1
                await asyncio.sleep(delay)
        finally:
            await self._session.close()

    def _disconnected(self) -> None:
        self.connected = False
        self._websocket = None
        for future in self._pending.values():
            if not future.done():
                future.set_exception(HAError("Verbindung zu Home Assistant getrennt."))
        self._pending.clear()

    async def _connect_and_listen(self) -> None:
        assert self._session is not None
        async with self._session.ws_connect(self._url, heartbeat=30, max_msg_size=0) as websocket:
            await self._authenticate(websocket)
            self._websocket = websocket
            self.connected = True
            self.last_error = None
            log.info("Mit Home Assistant verbunden.")
            startup = asyncio.create_task(self._after_connect())
            try:
                async for message in websocket:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        self._dispatch(message.json())
                    elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
            finally:
                startup.cancel()
        raise HAError("Home Assistant hat die Verbindung beendet.")

    async def _authenticate(self, websocket: aiohttp.ClientWebSocketResponse) -> None:
        greeting = await websocket.receive_json(timeout=CALL_TIMEOUT_S)
        if greeting.get("type") != "auth_required":
            raise HAError(f"Unerwartete Begrüßung von Home Assistant: {greeting.get('type')}")
        await websocket.send_json({"type": "auth", "access_token": self._token})
        answer = await websocket.receive_json(timeout=CALL_TIMEOUT_S)
        if answer.get("type") != "auth_ok":
            raise HAError("Anmeldung bei Home Assistant abgelehnt.")

    async def _after_connect(self) -> None:
        try:
            states = await self.call("get_states")
            self.states = {state["entity_id"]: state for state in states}
            await self.call("subscribe_events", event_type="state_changed")
            await self._on_connected()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 – Fehler des Abgleichs dürfen die Verbindung nicht beenden
            log.exception("Abgleich nach dem Verbinden fehlgeschlagen.")

    def _dispatch(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "result":
            future = self._pending.pop(message.get("id"), None)
            if future is None or future.done():
                return
            if message.get("success"):
                future.set_result(message.get("result"))
            else:
                error = message.get("error") or {}
                future.set_exception(HAError(error.get("message") or "Befehl abgelehnt."))
        elif kind == "event":
            event = message.get("event") or {}
            if event.get("event_type") != "state_changed":
                return
            data = event.get("data") or {}
            new_state = data.get("new_state")
            entity_id = data.get("entity_id")
            if new_state is None:
                self.states.pop(entity_id, None)
                return
            self.states[entity_id] = new_state
            try:
                self._on_state_changed(new_state)
            except Exception:  # noqa: BLE001 – ein fehlerhaftes Ereignis darf den Empfang nicht stoppen
                log.exception("Verarbeitung eines Zustandswechsels von %s fehlgeschlagen.", entity_id)

    async def call(self, command: str, **payload: Any) -> Any:
        """Sendet einen Befehl und wartet auf das Ergebnis."""
        websocket = self._websocket
        if websocket is None or websocket.closed:
            raise HAError("Nicht mit Home Assistant verbunden.")
        message_id = next(self._ids)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[message_id] = future
        await websocket.send_json({"id": message_id, "type": command, **payload})
        try:
            return await asyncio.wait_for(future, CALL_TIMEOUT_S)
        finally:
            self._pending.pop(message_id, None)

    async def history(self, entity_ids: list[str], start: datetime, end: datetime) -> dict[str, list[dict]]:
        """Verlauf ab `start` (inklusive des dann gültigen Zustands), normalisiert."""
        result = await self.call(
            "history/history_during_period",
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            entity_ids=entity_ids,
            include_start_time_state=True,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=False,
        )
        return {entity_id: normalize_history(entries) for entity_id, entries in (result or {}).items()}
