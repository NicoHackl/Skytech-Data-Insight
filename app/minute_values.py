"""Minutenwerte aus den Rohwerten berechnen (D-015).

Home Assistant meldet Werte nur bei Änderung. Ein einfacher Mittelwert über die
Rohwerte wäre deshalb verzerrt: zehn schnelle Meldungen in einer Sekunde zählten
zehnmal, eine Stunde ohne Änderung einmal. Gerechnet wird darum zeitgewichtet
mit „letzter Wert gilt fort": jeder Rohwert gilt, bis der nächste kommt. Der
Wert vor Beginn des Fensters (Anker) setzt die erste Minute fort.

Die Berechnung ist ein einziges SQL-Statement und wiederholbar: dieselben
Rohwerte ergeben dieselben Minutenwerte (Upsert). Nachgeladene oder verspätete
Rohwerte werden durch Neuberechnen des betroffenen Fensters eingearbeitet.
"""

from datetime import datetime, timedelta

import asyncpg

# Längstes Fenster je Berechnung. Größere Bereiche (Nachladen, Import) werden
# in solche Scheiben zerlegt, damit ein Statement nicht beliebig wächst.
MAX_WINDOW = timedelta(days=1)

# $1 = Fensterbeginn, $2 = Fensterende (beide auf volle Minuten), $3 = Sensor-IDs
MINUTE_VALUES_SQL = """
WITH sensoren AS (
    SELECT id, energie_zaehler FROM skytech.sensor WHERE id = ANY($3::integer[])
),
anker AS (
    -- Letzter Rohwert vor dem Fenster: gilt fort bis zur ersten Änderung.
    SELECT s.id AS sensor_id, $1::timestamptz AS zeit, a.wert, true AS ist_anker
    FROM sensoren s
    CROSS JOIN LATERAL (
        SELECT m.wert FROM skytech.messwert m
        WHERE m.sensor_id = s.id AND m.zeit < $1
        ORDER BY m.zeit DESC LIMIT 1
    ) a
),
punkte AS (
    SELECT sensor_id, zeit, wert, ist_anker FROM anker
    UNION ALL
    SELECT m.sensor_id, m.zeit, m.wert, false
    FROM skytech.messwert m
    WHERE m.sensor_id = ANY($3::integer[]) AND m.zeit >= $1 AND m.zeit < $2
),
segmente AS (
    SELECT sensor_id, zeit AS beginn, wert, ist_anker,
           lead(zeit, 1, $2::timestamptz) OVER (PARTITION BY sensor_id ORDER BY zeit, ist_anker DESC) AS ende
    FROM punkte
),
stuecke AS (
    -- Jedes Segment auf die Minuten verteilen, die es überdeckt.
    SELECT g.sensor_id, g.minute, g.wert,
           extract(epoch FROM least(g.ende, g.minute + interval '1 minute') - greatest(g.beginn, g.minute)) AS dauer_s,
           greatest(g.beginn, g.minute) AS stueck_beginn,
           (NOT g.ist_anker AND g.beginn >= g.minute) AS ist_meldung
    FROM (
        SELECT s.*, minute
        FROM segmente s
        CROSS JOIN LATERAL generate_series(
            date_trunc('minute', s.beginn), s.ende - interval '1 microsecond', interval '1 minute') AS minute
        WHERE s.ende > s.beginn
    ) g
),
zuwaechse AS (
    -- Zählerzuwachs je Rohwert gegenüber dem letzten bekannten Zahlenwert.
    -- Sinkt der Zähler, gilt das wie in Home Assistant als Neustart ab 0.
    SELECT p.sensor_id, date_trunc('minute', p.zeit) AS minute,
           sum(CASE WHEN p.vorher IS NULL THEN 0
                    WHEN p.wert >= p.vorher THEN p.wert - p.vorher
                    ELSE p.wert END) AS zuwachs
    FROM (
        SELECT pk.sensor_id, pk.zeit, pk.wert, pk.ist_anker,
               lag(pk.wert) OVER (PARTITION BY pk.sensor_id ORDER BY pk.zeit, pk.ist_anker DESC) AS vorher
        FROM punkte pk
        JOIN sensoren s ON s.id = pk.sensor_id AND s.energie_zaehler
        WHERE pk.wert IS NOT NULL
    ) p
    WHERE NOT p.ist_anker
    GROUP BY 1, 2
),
minuten AS (
    SELECT st.sensor_id, st.minute AS zeit,
           sum(st.wert * st.dauer_s) FILTER (WHERE st.wert IS NOT NULL)
               / nullif(sum(st.dauer_s) FILTER (WHERE st.wert IS NOT NULL), 0) AS mittel,
           min(st.wert) AS minimum,
           max(st.wert) AS maximum,
           last(st.wert, st.stueck_beginn) AS letzter,
           count(*) FILTER (WHERE st.ist_meldung)::integer AS anzahl,
           coalesce(sum(st.dauer_s) FILTER (WHERE st.wert IS NOT NULL), 0) AS abdeckung_s
    FROM stuecke st
    GROUP BY 1, 2
)
INSERT INTO skytech.messwert_1min AS z
    (zeit, sensor_id, mittel, minimum, maximum, letzter, zuwachs, anzahl, abdeckung_s)
SELECT mi.zeit, mi.sensor_id, mi.mittel, mi.minimum, mi.maximum, mi.letzter,
       CASE WHEN s.energie_zaehler THEN coalesce(zw.zuwachs, 0) END,
       mi.anzahl, mi.abdeckung_s
FROM minuten mi
JOIN sensoren s ON s.id = mi.sensor_id
LEFT JOIN zuwaechse zw ON zw.sensor_id = mi.sensor_id AND zw.minute = mi.zeit
-- Minuten ganz ohne Zahlenwert (Textsensor, dauerhaft unavailable) entfallen.
WHERE mi.abdeckung_s > 0
ON CONFLICT (sensor_id, zeit) DO UPDATE SET
    mittel = EXCLUDED.mittel, minimum = EXCLUDED.minimum, maximum = EXCLUDED.maximum,
    letzter = EXCLUDED.letzter, zuwachs = EXCLUDED.zuwachs, anzahl = EXCLUDED.anzahl,
    abdeckung_s = EXCLUDED.abdeckung_s
"""


def floor_minute(moment: datetime) -> datetime:
    """Rundet auf den Beginn der Minute ab."""
    return moment.replace(second=0, microsecond=0)


def split_window(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Zerlegt [start, end) in Scheiben von höchstens MAX_WINDOW."""
    slices = []
    cursor = start
    while cursor < end:
        slice_end = min(cursor + MAX_WINDOW, end)
        slices.append((cursor, slice_end))
        cursor = slice_end
    return slices


async def compute(connection: asyncpg.Connection, start: datetime, end: datetime, sensor_ids: list[int]) -> None:
    """Berechnet die Minutenwerte für [start, end) und schreibt sie per Upsert."""
    start, end = floor_minute(start), floor_minute(end)
    if not sensor_ids or start >= end:
        return
    for slice_start, slice_end in split_window(start, end):
        await connection.execute(MINUTE_VALUES_SQL, slice_start, slice_end, sensor_ids)
