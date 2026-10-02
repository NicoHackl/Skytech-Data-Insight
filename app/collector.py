"""Aufzeichnung der HA-Werte in `skytech.messwert` und Berechnung der Minutenwerte.

Ablauf:
1. Zustandswechsel kommen vom HAClient; je betroffenem Sensor wird der Wert
   (Zustand oder Attribut) umgesetzt und nur bei echter Änderung gepuffert.
2. Der Puffer wird alle FLUSH_INTERVAL_S gebündelt geschrieben. Ist die
   Datenbank weg, bleibt er erhalten – bis MAX_BUFFER, dann fallen die ältesten
   Werte weg (mit Warnung).
3. Jede Minute werden die Minutenwerte der abgeschlossenen Minute(n) berechnet
   (app/minute_values.py). Verspätete Werte lösen eine Neuberechnung aus.
4. Nach jeder (Neu-)Verbindung zu HA: aktuellen Zustand abgleichen und die Lücke
   seit dem letzten gespeicherten Wert aus dem HA-Verlauf nachladen.

Änderungen an der Sensorliste (Oberfläche oder SQL) kommen per LISTEN/NOTIFY.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg

import minute_values
from ha_client import HAClient, HAError, parse_timestamp
from values import StoredValue, convert

log = logging.getLogger(__name__)

FLUSH_INTERVAL_S = 2.0
MAX_BUFFER = 100_000
# Minutenberechnung kurz nach Minutenwechsel, damit späte Meldungen noch zählen.
MINUTE_DELAY_S = 5.0
# Weiter als so zurück lädt der Collector selbst nicht nach; der HA-Recorder
# hält standardmäßig 10 Tage. Ältere Daten: Import (M3b).
MAX_BACKFILL = timedelta(days=10)
# Verspätete Live-Werte lösen höchstens so weit zurück eine Neuberechnung aus.
MAX_LATE_RECOMPUTE = timedelta(hours=1)

_INSERT_SQL = """
INSERT INTO skytech.messwert (zeit, sensor_id, wert, text_wert)
SELECT * FROM unnest($1::timestamptz[], $2::integer[], $3::double precision[], $4::text[])
ON CONFLICT (sensor_id, zeit) DO NOTHING
"""


@dataclass(frozen=True)
class SensorConfig:
    id: int
    entity_id: str
    attribute: str | None
    active: bool


@dataclass(frozen=True)
class Reading:
    time: datetime
    sensor_id: int
    value: StoredValue


def extract(sensor: SensorConfig, state: dict[str, Any]) -> tuple[datetime | None, StoredValue]:
    """Zeitpunkt und Wert eines Sensors aus einem HA-Zustandsobjekt.

    Zustand: gilt seit `last_changed`. Attribut: kann sich ohne Zustandswechsel
    ändern, deshalb `last_updated`. Fehlt das Attribut, ist der Wert leer.
    """
    if sensor.attribute is None:
        moment = parse_timestamp(state.get("last_changed")) or parse_timestamp(state.get("last_updated"))
        return moment, convert(state.get("state"))
    moment = parse_timestamp(state.get("last_updated")) or parse_timestamp(state.get("last_changed"))
    attributes = state.get("attributes") or {}
    return moment, convert(attributes.get(sensor.attribute))


class Collector:
    def __init__(self, app_pool: asyncpg.Pool, collector_pool: asyncpg.Pool) -> None:
        self._app_pool = app_pool
        self._pool = collector_pool
        self.ha: HAClient | None = None
        self._sensors: dict[int, SensorConfig] = {}
        self._by_entity: dict[str, list[SensorConfig]] = {}
        self._last: dict[int, tuple[datetime, StoredValue]] = {}
        self._buffer: deque[Reading] = deque()
        self._flush_lock = asyncio.Lock()
        self._watermark: datetime | None = None
        self._late: dict[int, datetime] = {}
        self._written: deque[tuple[float, int]] = deque()
        self._listener_connection: asyncpg.Connection | None = None
        self._tasks: list[asyncio.Task] = []
        self.last_write: datetime | None = None
        self.last_error: str | None = None
        # Getrennt von last_error: ein erfolgreiches Schreiben der Rohwerte darf
        # einen Fehler der Minutenberechnung nicht überdecken.
        self.minute_error: str | None = None
        self.dropped = 0

    # ------------------------------------------------------------------
    # Lebenszyklus
    # ------------------------------------------------------------------

    async def start(self) -> None:
        await self.reload_sensors()
        await self._load_last_values()
        self._watermark = await self._initial_watermark()
        self._listener_connection = await self._app_pool.acquire()
        await self._listener_connection.add_listener("skytech_sensor", self._on_notify)
        self._tasks = [
            asyncio.create_task(self._flush_loop(), name="collector-flush"),
            asyncio.create_task(self._minute_loop(), name="collector-minute"),
        ]
        for task in self._tasks:
            task.add_done_callback(self._task_ended)

    def _task_ended(self, task: asyncio.Task) -> None:
        """Endet eine Schleife unerwartet, muss das sichtbar werden – nicht erst beim Beenden."""
        if task.cancelled():
            return
        exc = task.exception()
        self.last_error = f"Aufzeichnung gestoppt ({task.get_name()}): {exc or 'unerwartet beendet'}"
        log.error("Aufgabe %s beendet: %r", task.get_name(), exc)

    def minutes_lagging(self, now: datetime) -> bool:
        """Stehen die Minutenwerte? Normal ist höchstens eine Minute plus Verzögerung Rückstand."""
        return self._watermark is not None and now - self._watermark > timedelta(minutes=3)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.flush()
        if self._listener_connection is not None:
            await self._listener_connection.remove_listener("skytech_sensor", self._on_notify)
            await self._app_pool.release(self._listener_connection)

    # ------------------------------------------------------------------
    # Sensorliste
    # ------------------------------------------------------------------

    def _on_notify(self, *_args: Any) -> None:
        asyncio.get_running_loop().create_task(self._reload_after_change())

    async def _reload_after_change(self) -> None:
        previous = {sensor_id for sensor_id, s in self._sensors.items() if s.active}
        await self.reload_sensors()
        added = [s for s in self._sensors.values() if s.active and s.id not in previous]
        # Neu aktivierte Sensoren sofort mit dem aktuellen Zustand beginnen.
        if added and self.ha is not None:
            for sensor in added:
                state = self.ha.states.get(sensor.entity_id)
                if state is not None:
                    self._record(sensor, state, is_live=False)

    async def reload_sensors(self) -> None:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch("SELECT id, entity_id, attribut, aktiv FROM skytech.sensor")
        sensors = {row["id"]: SensorConfig(row["id"], row["entity_id"], row["attribut"], row["aktiv"]) for row in rows}
        by_entity: dict[str, list[SensorConfig]] = {}
        for sensor in sensors.values():
            if sensor.active:
                by_entity.setdefault(sensor.entity_id, []).append(sensor)
        self._sensors, self._by_entity = sensors, by_entity
        log.info("%d Sensoren aktiv.", sum(len(v) for v in by_entity.values()))

    @property
    def active_sensor_ids(self) -> list[int]:
        return [s.id for s in self._sensors.values() if s.active]

    async def _load_last_values(self) -> None:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch("""
                SELECT s.id AS sensor_id, l.zeit, l.wert, l.text_wert
                FROM skytech.sensor s
                CROSS JOIN LATERAL (
                    SELECT zeit, wert, text_wert FROM skytech.messwert m
                    WHERE m.sensor_id = s.id ORDER BY zeit DESC LIMIT 1
                ) l
            """)
        self._last = {row["sensor_id"]: (row["zeit"], StoredValue(row["wert"], row["text_wert"])) for row in rows}

    async def _initial_watermark(self) -> datetime:
        async with self._pool.acquire() as connection:
            last_minute = await connection.fetchval("SELECT max(zeit) FROM skytech.messwert_1min")
        if last_minute is not None:
            return last_minute + timedelta(minutes=1)
        return minute_values.floor_minute(datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Werte aufnehmen
    # ------------------------------------------------------------------

    def on_state_changed(self, state: dict[str, Any]) -> None:
        for sensor in self._by_entity.get(state.get("entity_id", ""), ()):
            self._record(sensor, state, is_live=True)

    def _record(self, sensor: SensorConfig, state: dict[str, Any], is_live: bool) -> None:
        moment, value = extract(sensor, state)
        if moment is None:
            return
        previous = self._last.get(sensor.id)
        if previous is not None:
            previous_time, previous_value = previous
            # Nur echte Änderungen – und nie rückwärts hinter den letzten Wert.
            if previous_value == value or moment <= previous_time:
                return
        self._append(Reading(moment, sensor.id, value))
        if is_live and self._watermark is not None and moment < self._watermark:
            self._mark_late(sensor.id, max(moment, self._watermark - MAX_LATE_RECOMPUTE))

    def _append(self, reading: Reading) -> None:
        self._last[reading.sensor_id] = (reading.time, reading.value)
        self._buffer.append(reading)
        if len(self._buffer) > MAX_BUFFER:
            self._buffer.popleft()
            self.dropped += 1
            if self.dropped % 1000 == 1:
                log.warning("Schreibpuffer voll – ältere Werte werden verworfen (bisher %d).", self.dropped)

    def _mark_late(self, sensor_id: int, moment: datetime) -> None:
        current = self._late.get(sensor_id)
        self._late[sensor_id] = moment if current is None else min(current, moment)

    # ------------------------------------------------------------------
    # Schreiben
    # ------------------------------------------------------------------

    async def flush(self) -> None:
        """Schreibt den Puffer. Schreib- und Minutenschleife rufen das beide auf –
        deshalb gesperrt und mit Tausch des Puffers statt Abzählen: Werte, die
        während des Schreibens eingehen, landen im neuen Puffer und gehen nie
        verloren (Fehler bis 0.4.1: „pop from an empty deque")."""
        async with self._flush_lock:
            if not self._buffer:
                return
            batch, self._buffer = self._buffer, deque()
            try:
                async with self._pool.acquire() as connection:
                    await connection.execute(
                        _INSERT_SQL,
                        [r.time for r in batch], [r.sensor_id for r in batch],
                        [r.value.number for r in batch], [r.value.text for r in batch],
                    )
            except (asyncpg.PostgresError, OSError) as exc:
                self._restore_batch(batch)
                self.last_error = f"Schreiben fehlgeschlagen: {exc}"
                log.warning("%s – %d Werte bleiben im Puffer.", self.last_error, len(self._buffer))
                return
            except BaseException:
                self._restore_batch(batch)
                raise
            self._written.append((asyncio.get_running_loop().time(), len(batch)))
            self.last_write = datetime.now(timezone.utc)
            self.last_error = None

    def _restore_batch(self, batch: deque) -> None:
        """Nicht geschriebene Werte zurück an den Anfang; Obergrenze wie beim Anhängen."""
        batch.extend(self._buffer)
        self._buffer = batch
        while len(self._buffer) > MAX_BUFFER:
            self._buffer.popleft()
            self.dropped += 1

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            try:
                await self.flush()
            except Exception:  # noqa: BLE001 – die Schleife darf nie still enden
                self.last_error = "Schreiben fehlgeschlagen (Details im Protokoll)."
                log.exception("Schreiben der Rohwerte fehlgeschlagen.")

    def values_last_minute(self) -> int:
        now = asyncio.get_running_loop().time()
        while self._written and self._written[0][0] < now - 60:
            self._written.popleft()
        return sum(count for _, count in self._written)

    @property
    def buffered(self) -> int:
        return len(self._buffer)

    @property
    def minutes_until(self) -> datetime | None:
        return self._watermark

    # ------------------------------------------------------------------
    # Minutenwerte
    # ------------------------------------------------------------------

    async def _minute_loop(self) -> None:
        while True:
            now = datetime.now(timezone.utc)
            next_run = minute_values.floor_minute(now) + timedelta(minutes=1, seconds=MINUTE_DELAY_S)
            await asyncio.sleep((next_run - now).total_seconds())
            try:
                await self.flush()
                await self.compute_minutes(datetime.now(timezone.utc))
                self.minute_error = None
            except Exception as exc:  # noqa: BLE001 – eine Ausnahme beendete sonst die Schleife still (0.4.1)
                self.minute_error = f"Minutenwerte fehlgeschlagen: {exc or type(exc).__name__}"
                log.exception("Berechnung der Minutenwerte fehlgeschlagen.")

    async def compute_minutes(self, now: datetime) -> None:
        """Berechnet alle abgeschlossenen Minuten seit dem letzten Lauf."""
        end = minute_values.floor_minute(now)
        late, self._late = self._late, {}
        async with self._pool.acquire() as connection:
            # Verspätete Werte: nur die betroffenen Sensoren neu rechnen.
            by_start: dict[datetime, list[int]] = {}
            for sensor_id, moment in late.items():
                by_start.setdefault(minute_values.floor_minute(moment), []).append(sensor_id)
            for start, sensor_ids in by_start.items():
                await minute_values.compute(connection, start, self._watermark or end, sensor_ids)
            if self._watermark is not None and self._watermark < end:
                await minute_values.compute(connection, self._watermark, end, self.active_sensor_ids)
        self._watermark = end

    # ------------------------------------------------------------------
    # Abgleich nach Verbindung mit HA
    # ------------------------------------------------------------------

    async def on_connected(self) -> None:
        """Aktuellen Zustand übernehmen und die Lücke seit dem letzten Wert nachladen."""
        assert self.ha is not None
        now = datetime.now(timezone.utc)
        gaps: dict[str, datetime] = {}
        for sensor_id in self.active_sensor_ids:
            sensor = self._sensors[sensor_id]
            last = self._last.get(sensor_id)
            if last is not None and now - last[0] > timedelta(seconds=5):
                start = max(last[0], now - MAX_BACKFILL)
                gaps[sensor.entity_id] = min(start, gaps.get(sensor.entity_id, start))
        if gaps:
            await self.backfill(gaps, now)
        # Danach den aktuellen Zustand – bei neuen Sensoren der erste Wert.
        for sensor_id in self.active_sensor_ids:
            sensor = self._sensors[sensor_id]
            state = self.ha.states.get(sensor.entity_id)
            if state is not None:
                self._record(sensor, state, is_live=False)
        await self.flush()

    async def backfill(self, gaps: dict[str, datetime], end: datetime) -> None:
        """Lädt den HA-Verlauf je Entität ab dem angegebenen Zeitpunkt nach."""
        assert self.ha is not None
        start = min(gaps.values())
        try:
            history = await self.ha.history(sorted(gaps), start, end)
        except HAError as exc:
            log.warning("Nachladen aus dem HA-Verlauf fehlgeschlagen: %s", exc)
            return
        loaded = 0
        for entity_id, states in history.items():
            for sensor in self._by_entity.get(entity_id, ()):
                for state in states:
                    before = self._last.get(sensor.id)
                    self._record(sensor, state, is_live=False)
                    if self._last.get(sensor.id) is not before:
                        loaded += 1
                # Die Minutenwerte ab Beginn der Lücke neu rechnen – auch die
                # Minuten vor dem ersten nachgeladenen Wert waren bisher offen.
                gap_start = gaps[entity_id]
                if self._watermark is not None and gap_start < self._watermark:
                    self._mark_late(sensor.id, gap_start)
        if loaded:
            log.info("%d Werte aus dem HA-Verlauf nachgeladen.", loaded)
        await self.flush()
