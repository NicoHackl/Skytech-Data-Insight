"""Aufzeichnung der HA-Werte in `skytech.messwert` und Berechnung der Minutenwerte.

Ablauf:
1. Zustandswechsel kommen vom HAClient; je betroffenem Sensor wird der Wert
   (Zustand oder Attribut) umgesetzt und nur bei echter Änderung gepuffert.
2. Der Puffer wird alle FLUSH_INTERVAL_S gebündelt geschrieben. Ist die
   Datenbank weg, bleibt er erhalten – bis MAX_BUFFER, dann fallen die ältesten
   Werte weg (mit Warnung).
3. Jede Minute werden die Minutenwerte der abgeschlossenen Minute(n) berechnet
   (app/minute_values.py). Verspätete Werte lösen eine Neuberechnung aus.
4. Nach jeder (Neu-)Verbindung zu HA: aktuellen Zustand übernehmen und die Zeit
   seit dem letzten gespeicherten Wert als Lücke in skytech_config.nachlade_luecke
   eintragen. Eine Hintergrundschleife lädt offene Lücken in kleinen Stücken
   (höchstens 1 h, höchstens 5 Entitäten je Aufruf) aus dem HA-Verlauf nach und
   versucht es bei Fehlern mit wachsender Wartezeit erneut – auch nach einem
   weiteren Neustart, weil der Stand in der Datenbank steht.

Änderungen an der Sensorliste (Oberfläche oder SQL) kommen per LISTEN/NOTIFY.

Sensoren mit `quelle = 'hems'` schreibt SkytechHEMS selbst (Vertrag
contract_hems_data_insight). Für sie holt der Collector nichts aus HA; neue
Werte meldet die Datenbankfunktion per NOTIFY `skytech_hems_werte`, damit die
Minutenwerte ab dem frühesten neuen Zeitpunkt neu gerechnet werden. Weil eine
Meldung während eines Neustarts verloren geht, gleicht der Collector beim Start
und alle 15 min selbst ab: Rohwerte ohne Minutenwert werden nachgerechnet.
"""

import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg

import minute_values
from display_time import format_berlin
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
# Nachladen: kleine Stücke, damit HA die Antwort nicht verwirft (0.7.1: ein Aufruf
# über Tage mit Attributen → „Verbindung getrennt“).
BACKFILL_WINDOW = timedelta(hours=1)
BACKFILL_GROUP = 5
BACKFILL_RETRY_S = (30.0, 60.0, 120.0, 300.0, 600.0)
BACKFILL_IDLE_S = 60.0
# Kürzere Ausfälle sind keine Lücke (normale Ruhe zwischen zwei Werten).
GAP_MIN = timedelta(seconds=5)
# Abgleich der HEMS-Reihen ohne Meldung.
HEMS_RECHECK = timedelta(minutes=15)

_HEMS_WITHOUT_MINUTES_SQL = """
SELECT m.sensor_id, min(m.zeit) AS ab
FROM skytech.messwert m
JOIN skytech.sensor s ON s.id = m.sensor_id AND s.quelle = 'hems' AND s.aktiv
WHERE m.zeit >= $1 AND m.zeit < $2
  AND NOT EXISTS (SELECT 1 FROM skytech.messwert_1min x
                  WHERE x.sensor_id = m.sensor_id AND x.zeit = date_trunc('minute', m.zeit) AND x.anzahl > 0)
GROUP BY m.sensor_id
"""

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
    # False: Werte schreibt SkytechHEMS selbst (quelle = 'hems'), nicht Home Assistant.
    from_ha: bool = True


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
        # Offene Lücke mit Fehlversuchen – erscheint in der Kachel „Aufzeichnung“.
        self.backfill_status: str | None = None
        self._backfill_wakeup = asyncio.Event()
        self._last_hems_recheck: datetime | None = None
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
        await self._listener_connection.add_listener("skytech_hems_werte", self._on_hems_values)
        await self.recheck_hems_series(datetime.now(timezone.utc))
        self._tasks = [
            asyncio.create_task(self._flush_loop(), name="collector-flush"),
            asyncio.create_task(self._minute_loop(), name="collector-minute"),
            asyncio.create_task(self._backfill_loop(), name="collector-backfill"),
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
            await self._listener_connection.remove_listener("skytech_hems_werte", self._on_hems_values)
            await self._app_pool.release(self._listener_connection)

    # ------------------------------------------------------------------
    # Sensorliste
    # ------------------------------------------------------------------

    def _on_notify(self, *_args: Any) -> None:
        asyncio.get_running_loop().create_task(self._reload_after_change())

    def _on_hems_values(self, _connection: Any, _pid: int, _channel: str, payload: str) -> None:
        """SkytechHEMS hat Werte geschrieben – oft für einen schon gerechneten Slot."""
        try:
            data = json.loads(payload)
            sensor_id = int(data["sensor_id"])
            start = parse_timestamp(data["ab"])
        except (ValueError, KeyError, TypeError):
            log.warning("Unlesbare Meldung skytech_hems_werte: %r", payload)
            return
        self.mark_hems_values(sensor_id, start)

    def mark_hems_values(self, sensor_id: int, start: datetime | None) -> None:
        """Minutenwerte ab `start` neu rechnen, höchstens MAX_BACKFILL zurück."""
        if start is None or self._watermark is None or start >= self._watermark:
            return
        self._mark_late(sensor_id, max(start, self._watermark - MAX_BACKFILL))

    async def _reload_after_change(self) -> None:
        previous = {sensor_id for sensor_id, s in self._sensors.items() if s.active}
        await self.reload_sensors()
        added = [s for s in self._sensors.values() if s.active and s.from_ha and s.id not in previous]
        # Neu aktivierte Sensoren sofort mit dem aktuellen Zustand beginnen.
        if added and self.ha is not None:
            for sensor in added:
                state = self.ha.states.get(sensor.entity_id)
                if state is not None:
                    self._record(sensor, state, is_live=False)

    async def reload_sensors(self) -> None:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch("SELECT id, entity_id, attribut, aktiv, quelle FROM skytech.sensor")
        sensors = {row["id"]: SensorConfig(row["id"], row["entity_id"], row["attribut"], row["aktiv"],
                                           row["quelle"] != "hems") for row in rows}
        by_entity: dict[str, list[SensorConfig]] = {}
        for sensor in sensors.values():
            if sensor.active and sensor.from_ha:
                by_entity.setdefault(sensor.entity_id, []).append(sensor)
        self._sensors, self._by_entity = sensors, by_entity
        log.info("%d Sensoren aktiv.", sum(len(v) for v in by_entity.values()))

    @property
    def active_sensor_ids(self) -> list[int]:
        """Alle aktiven Sensoren – auch die HEMS-Reihen, deren Minutenwerte hier entstehen."""
        return [s.id for s in self._sensors.values() if s.active]

    @property
    def ha_sensor_ids(self) -> list[int]:
        """Aktive Sensoren, deren Werte aus Home Assistant kommen."""
        return [s.id for s in self._sensors.values() if s.active and s.from_ha]

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

    def _append(self, reading: Reading, update_last: bool = True) -> None:
        if update_last:
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
                now = datetime.now(timezone.utc)
                if self._last_hems_recheck is None or now - self._last_hems_recheck >= HEMS_RECHECK:
                    await self.recheck_hems_series(now)
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
        """Aktuellen Zustand übernehmen; die Zeit seit dem letzten Wert als Lücke eintragen.

        Nachgeladen wird im Hintergrund (`_backfill_loop`) – der Start wartet nicht darauf.
        """
        assert self.ha is not None
        now = datetime.now(timezone.utc)
        ha_ids = set(self.ha_sensor_ids)
        latest = max((moment for sensor_id, (moment, _) in self._last.items() if sensor_id in ha_ids), default=None)
        if latest is not None and now - latest > GAP_MIN:
            await self.open_gap(max(latest, now - MAX_BACKFILL), now)
        for sensor_id in self.ha_sensor_ids:
            sensor = self._sensors[sensor_id]
            state = self.ha.states.get(sensor.entity_id)
            if state is not None:
                self._record(sensor, state, is_live=False)
        await self.flush()
        self._backfill_wakeup.set()

    async def open_gap(self, start: datetime, end: datetime) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO skytech_config.nachlade_luecke (von, bis) VALUES ($1, $2)", start, end)
        log.info("Lücke %s bis %s wird aus dem HA-Verlauf nachgeladen.", format_berlin(start), format_berlin(end))

    # ------------------------------------------------------------------
    # Nachladen aus dem HA-Verlauf
    # ------------------------------------------------------------------

    async def _backfill_loop(self) -> None:
        failures = 0
        while True:
            try:
                await self.process_gaps()
                failures = 0
                wait = BACKFILL_IDLE_S
            except (HAError, asyncpg.PostgresError, OSError, asyncio.TimeoutError) as exc:
                wait = BACKFILL_RETRY_S[min(failures, len(BACKFILL_RETRY_S) - 1)]
                failures += 1
                log.warning("Nachladen aus dem HA-Verlauf fehlgeschlagen (%s) – neuer Versuch in %d s.", exc, wait)
            except Exception:  # noqa: BLE001 – die Schleife darf nie still enden
                wait = BACKFILL_RETRY_S[-1]
                log.exception("Nachladen aus dem HA-Verlauf fehlgeschlagen.")
            self._backfill_wakeup.clear()
            try:
                await asyncio.wait_for(self._backfill_wakeup.wait(), wait)
            except asyncio.TimeoutError:
                pass

    async def process_gaps(self) -> None:
        """Arbeitet alle offenen Lücken ab; wirft bei einem Fehler, der Stand bleibt gespeichert."""
        if self.ha is None or not self.ha.connected:
            return
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as connection:
            gaps = await connection.fetch(
                "SELECT id, von, bis, versuche FROM skytech_config.nachlade_luecke "
                "WHERE erledigt_am IS NULL ORDER BY von")
        for gap in gaps:
            if gap["bis"] <= now - MAX_BACKFILL:
                await self._finish_gap(gap["id"], "zu alt – HA hält den Verlauf höchstens 10 Tage")
                continue
            try:
                await self._load_gap(gap["id"], max(gap["von"], now - MAX_BACKFILL), gap["bis"])
            except (HAError, asyncpg.PostgresError, OSError, asyncio.TimeoutError) as exc:
                async with self._pool.acquire() as connection:
                    await connection.execute(
                        "UPDATE skytech_config.nachlade_luecke SET versuche = versuche + 1, letzter_fehler = $2 "
                        "WHERE id = $1", gap["id"], str(exc)[:500])
                self.backfill_status = (f"Nachladen offen seit {format_berlin(gap['von'])} "
                                        f"({gap['versuche'] + 1} Versuche): {exc}")
                raise
        self.backfill_status = None

    async def _load_gap(self, gap_id: int, start: datetime, end: datetime) -> None:
        sensors = [self._sensors[sensor_id] for sensor_id in self.ha_sensor_ids]
        plain = sorted({s.entity_id for s in sensors} - {s.entity_id for s in sensors if s.attribute})
        with_attributes = sorted({s.entity_id for s in sensors if s.attribute})
        groups = ([(plain[i:i + BACKFILL_GROUP], True) for i in range(0, len(plain), BACKFILL_GROUP)]
                  + [(with_attributes[i:i + BACKFILL_GROUP], False)
                     for i in range(0, len(with_attributes), BACKFILL_GROUP)])
        loaded = 0
        window_start = start
        try:
            while window_start < end:
                window_end = min(window_start + BACKFILL_WINDOW, end)
                for entity_ids, no_attributes in groups:
                    history = await self.ha.history(entity_ids, window_start, window_end, no_attributes=no_attributes)
                    for entity_id, states in history.items():
                        for sensor in self._by_entity.get(entity_id, ()):
                            loaded += self._store_history(sensor, states, window_start)
                await self.flush()
                if window_end < end:
                    # Fortschritt sichern; das letzte Fenster schließt die Lücke unten ab.
                    async with self._pool.acquire() as connection:
                        await connection.execute(
                            "UPDATE skytech_config.nachlade_luecke SET von = $2 WHERE id = $1", gap_id, window_end)
                window_start = window_end
        finally:
            # Die Minutenwerte ab Lückenbeginn neu rechnen – auch bei Abbruch für das schon Geladene.
            if window_start > start and self._watermark is not None:
                for sensor in sensors:
                    if start < self._watermark:
                        self._mark_late(sensor.id, start)
        await self._finish_gap(gap_id, None)
        log.info("Lücke ab %s nachgeladen: %d Werte.", format_berlin(start), loaded)

    async def _finish_gap(self, gap_id: int, reason: str | None) -> None:
        async with self._pool.acquire() as connection:
            await connection.execute(
                "UPDATE skytech_config.nachlade_luecke SET erledigt_am = now(), "
                "letzter_fehler = coalesce($2, letzter_fehler) WHERE id = $1", gap_id, reason)

    def _store_history(self, sensor: SensorConfig, states: list[dict[str, Any]], after: datetime) -> int:
        """Historische Werte direkt in den Puffer – an `_record` vorbei, der alles vor dem
        letzten Live-Wert verwirft. Der mitgelieferte Startzustand (bis `after`) ist schon
        gespeichert: Die Lücke beginnt beim letzten Rohwert, die Fenster schließen aneinander
        an. Doppelte Zeitpunkte verwirft die Datenbank."""
        previous: StoredValue | None = None
        stored = 0
        for state in states:
            moment, value = extract(sensor, state)
            if moment is None or moment <= after or value == previous:
                continue
            previous = value
            self._append(Reading(moment, sensor.id, value), update_last=False)
            stored += 1
        return stored

    # ------------------------------------------------------------------
    # HEMS-Reihen ohne Meldung
    # ------------------------------------------------------------------

    async def recheck_hems_series(self, now: datetime) -> None:
        """HEMS-Rohwerte der letzten 10 Tage ohne Minutenwert nachrechnen (verlorene Meldung)."""
        self._last_hems_recheck = now
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(_HEMS_WITHOUT_MINUTES_SQL, now - MAX_BACKFILL,
                                          self._watermark or minute_values.floor_minute(now))
        for row in rows:
            self.mark_hems_values(row["sensor_id"], row["ab"])
        if rows:
            log.info("%d HEMS-Reihe(n) ohne Minutenwerte – werden nachgerechnet.", len(rows))
