-- 0001 Grundschema: Sensor-Stammdaten, Rohwerte, Minutenwerte, Aggregate,
-- Fachsichten, Einstellungen und Änderungsprotokoll.
-- Läuft als skytech_app in einer Transaktion (app/migration_runner.py).
-- Namen sind deutsch: sie sind der Datenvertrag für SQL, Grafana und MCP
-- (eiserne Regel 2, docs/datenmodell.md).

CREATE SCHEMA skytech;
CREATE SCHEMA skytech_config;

-- ---------------------------------------------------------------------------
-- Kataloge: erweiterbar per INSERT, ohne Schemaänderung
-- ---------------------------------------------------------------------------

CREATE TABLE skytech.kategorie (
    schluessel  text PRIMARY KEY CHECK (schluessel ~ '^[a-z][a-z0-9_]*$'),
    bezeichnung text NOT NULL,
    reihenfolge integer NOT NULL DEFAULT 100
);
COMMENT ON TABLE skytech.kategorie IS 'Fachbereich eines Sensors (PV, Heizung, Speicher …).';

INSERT INTO skytech.kategorie (schluessel, bezeichnung, reihenfolge) VALUES
    ('pv',          'PV',          10),
    ('speicher',    'Speicher',    20),
    ('netz',        'Netz',        30),
    ('heizung',     'Heizung',     40),
    ('verbraucher', 'Verbraucher', 50),
    ('sonstiges',   'Sonstiges',   90);

CREATE TABLE skytech.groesse (
    schluessel  text PRIMARY KEY CHECK (schluessel ~ '^[a-z][a-z0-9_]*$'),
    bezeichnung text NOT NULL,
    reihenfolge integer NOT NULL DEFAULT 100
);
COMMENT ON TABLE skytech.groesse IS 'Physikalische Größe eines Sensors (Leistung, Energie …).';

INSERT INTO skytech.groesse (schluessel, bezeichnung, reihenfolge) VALUES
    ('leistung',     'Leistung',     10),
    ('energie',      'Energie',      20),
    ('ladezustand',  'Ladezustand',  30),
    ('temperatur',   'Temperatur',   40),
    ('spannung',     'Spannung',     50),
    ('strom',        'Strom',        60),
    ('zustand',      'Zustand',      70),
    ('sonstiges',    'Sonstiges',    90);

-- ---------------------------------------------------------------------------
-- Sensor-Stammdaten
-- ---------------------------------------------------------------------------

CREATE TABLE skytech.sensor (
    id              integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_id       text NOT NULL CHECK (entity_id ~ '^[a-z_]+\.[a-z0-9_]+$'),
    -- NULL = Zustand der Entität, sonst Name des aufgezeichneten Attributs.
    attribut        text CHECK (attribut IS NULL OR attribut <> ''),
    name            text NOT NULL CHECK (name <> ''),
    kategorie       text NOT NULL REFERENCES skytech.kategorie ON UPDATE CASCADE,
    groesse         text NOT NULL REFERENCES skytech.groesse ON UPDATE CASCADE,
    rolle           text CHECK (rolle IN ('ist', 'soll')),
    -- Sensoren mit gleichem Paarnamen bilden ein Soll/Ist-Paar (v_soll_ist).
    soll_ist_paar   text CHECK (soll_ist_paar IS NULL OR soll_ist_paar <> ''),
    einheit         text,
    anlage          text CHECK (anlage IS NULL OR anlage <> ''),
    -- Zählerstand (state_class total/total_increasing): Minutenwerte tragen den Zuwachs.
    energie_zaehler boolean NOT NULL DEFAULT false,
    aktiv           boolean NOT NULL DEFAULT true,
    quelle          text NOT NULL DEFAULT 'ha' CHECK (quelle IN ('ha', 'hems', 'extern')),
    erstellt_am     timestamptz NOT NULL DEFAULT now(),
    geaendert_am    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT soll_ist_paar_braucht_rolle CHECK (soll_ist_paar IS NULL OR rolle IS NOT NULL)
);
-- Zustand und jedes Attribut einer Entität höchstens einmal.
CREATE UNIQUE INDEX sensor_quelle_eindeutig ON skytech.sensor (entity_id, coalesce(attribut, ''));
-- Je Paar höchstens ein Soll und ein Ist.
CREATE UNIQUE INDEX sensor_paar_eindeutig ON skytech.sensor (soll_ist_paar, rolle) WHERE soll_ist_paar IS NOT NULL;
COMMENT ON TABLE skytech.sensor IS 'Aufgezeichnete HA-Entitäten bzw. Attribute mit fachlicher Einordnung.';

-- Jede Änderung an der Sensorliste meldet sich beim Collector, damit neue oder
-- deaktivierte Sensoren sofort wirken – auch bei Änderungen per SQL.
CREATE FUNCTION skytech.sensor_geaendert() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        NEW.geaendert_am := now();
    END IF;
    PERFORM pg_notify('skytech_sensor', TG_OP);
    RETURN COALESCE(NEW, OLD);
END
$$;
CREATE TRIGGER sensor_geaendert_zeile BEFORE UPDATE ON skytech.sensor
    FOR EACH ROW EXECUTE FUNCTION skytech.sensor_geaendert();
CREATE TRIGGER sensor_geaendert_satz AFTER INSERT OR DELETE ON skytech.sensor
    FOR EACH STATEMENT EXECUTE FUNCTION skytech.sensor_geaendert();

-- ---------------------------------------------------------------------------
-- Rohwerte: jede Änderung, so wie Home Assistant sie meldet
-- ---------------------------------------------------------------------------

CREATE TABLE skytech.messwert (
    zeit      timestamptz NOT NULL,
    sensor_id integer NOT NULL REFERENCES skytech.sensor ON DELETE CASCADE,
    -- Zahl, on/off als 1/0; NULL bei Text, unknown und unavailable.
    wert      double precision,
    -- Originaltext, wenn der Zustand keine reine Zahl ist.
    text_wert text,
    PRIMARY KEY (sensor_id, zeit)
);
SELECT create_hypertable('skytech.messwert', by_range('zeit', INTERVAL '7 days'));
COMMENT ON TABLE skytech.messwert IS 'Rohwerte: jede Zustandsänderung eines Sensors (Zeit in UTC).';

-- ---------------------------------------------------------------------------
-- Minutenwerte: zeitgewichtet aus den Rohwerten berechnet (D-015)
-- ---------------------------------------------------------------------------

CREATE TABLE skytech.messwert_1min (
    zeit        timestamptz NOT NULL,
    sensor_id   integer NOT NULL REFERENCES skytech.sensor ON DELETE CASCADE,
    mittel      double precision,
    minimum     double precision,
    maximum     double precision,
    letzter     double precision,
    -- Zuwachs eines Zählers in dieser Minute (Neustart des Zählers berücksichtigt).
    zuwachs     double precision,
    -- Anzahl Rohwerte, die in dieser Minute eingingen.
    anzahl      integer NOT NULL,
    -- Sekunden der Minute, für die ein Zahlenwert bekannt war (0–60).
    abdeckung_s double precision NOT NULL,
    PRIMARY KEY (sensor_id, zeit)
);
SELECT create_hypertable('skytech.messwert_1min', by_range('zeit', INTERVAL '30 days'));
COMMENT ON TABLE skytech.messwert_1min IS 'Minutenwerte je Sensor: zeitgewichtetes Mittel, Min, Max, letzter Wert, Zählerzuwachs.';

-- Rohwerte und Minutenwerte werden nach 7 Tagen spaltenweise komprimiert.
ALTER TABLE skytech.messwert SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'sensor_id',
    timescaledb.compress_orderby = 'zeit DESC'
);
SELECT add_compression_policy('skytech.messwert', INTERVAL '7 days');
ALTER TABLE skytech.messwert_1min SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'sensor_id',
    timescaledb.compress_orderby = 'zeit DESC'
);
SELECT add_compression_policy('skytech.messwert_1min', INTERVAL '7 days');

-- ---------------------------------------------------------------------------
-- Verdichtungen aus den Minutenwerten (Continuous Aggregates)
-- ---------------------------------------------------------------------------
-- Das Mittel wird mit der Abdeckung gewichtet, damit Minuten mit Lücken nicht
-- zu stark zählen. Tageswerte laufen nach Berliner Kalendertag.

CREATE MATERIALIZED VIEW skytech.messwert_15min
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket(INTERVAL '15 minutes', zeit) AS zeit,
       sensor_id,
       sum(mittel * abdeckung_s) / nullif(sum(abdeckung_s), 0) AS mittel,
       min(minimum) AS minimum,
       max(maximum) AS maximum,
       last(letzter, zeit) AS letzter,
       sum(zuwachs) AS zuwachs,
       sum(anzahl)::integer AS anzahl,
       sum(abdeckung_s) AS abdeckung_s
FROM skytech.messwert_1min
GROUP BY 1, 2
WITH NO DATA;

CREATE MATERIALIZED VIEW skytech.messwert_1h
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket(INTERVAL '1 hour', zeit) AS zeit,
       sensor_id,
       sum(mittel * abdeckung_s) / nullif(sum(abdeckung_s), 0) AS mittel,
       min(minimum) AS minimum,
       max(maximum) AS maximum,
       last(letzter, zeit) AS letzter,
       sum(zuwachs) AS zuwachs,
       sum(anzahl)::integer AS anzahl,
       sum(abdeckung_s) AS abdeckung_s
FROM skytech.messwert_1min
GROUP BY 1, 2
WITH NO DATA;

CREATE MATERIALIZED VIEW skytech.messwert_1d
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket(INTERVAL '1 day', zeit, 'Europe/Berlin') AS zeit,
       sensor_id,
       sum(mittel * abdeckung_s) / nullif(sum(abdeckung_s), 0) AS mittel,
       min(minimum) AS minimum,
       max(maximum) AS maximum,
       last(letzter, zeit) AS letzter,
       sum(zuwachs) AS zuwachs,
       sum(anzahl)::integer AS anzahl,
       sum(abdeckung_s) AS abdeckung_s
FROM skytech.messwert_1min
GROUP BY 1, 2
WITH NO DATA;

-- Das Aktualisierungsfenster (30 Tage) muss kürzer bleiben als jede
-- Aufbewahrung der Minutenwerte, sonst löschte eine Aktualisierung Aggregate.
SELECT add_continuous_aggregate_policy('skytech.messwert_15min',
    start_offset => INTERVAL '30 days', end_offset => INTERVAL '15 minutes', schedule_interval => INTERVAL '5 minutes');
SELECT add_continuous_aggregate_policy('skytech.messwert_1h',
    start_offset => INTERVAL '30 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '15 minutes');
SELECT add_continuous_aggregate_policy('skytech.messwert_1d',
    start_offset => INTERVAL '30 days', end_offset => INTERVAL '1 day', schedule_interval => INTERVAL '1 hour');

-- ---------------------------------------------------------------------------
-- Sichten mit Stammdaten
-- ---------------------------------------------------------------------------

CREATE VIEW skytech.v_messwert AS
SELECT m.zeit, s.id AS sensor_id, s.name, s.entity_id, s.attribut, s.kategorie, s.groesse, s.rolle,
       s.einheit, s.anlage, m.wert, m.text_wert
FROM skytech.messwert m
JOIN skytech.sensor s ON s.id = m.sensor_id;
COMMENT ON VIEW skytech.v_messwert IS 'Rohwerte mit Sensor-Stammdaten.';

CREATE VIEW skytech.v_messwert_1min AS
SELECT m.zeit, s.id AS sensor_id, s.name, s.entity_id, s.attribut, s.kategorie, s.groesse, s.rolle,
       s.einheit, s.anlage, m.mittel, m.minimum, m.maximum, m.letzter, m.zuwachs, m.anzahl, m.abdeckung_s
FROM skytech.messwert_1min m
JOIN skytech.sensor s ON s.id = m.sensor_id;
COMMENT ON VIEW skytech.v_messwert_1min IS 'Minutenwerte mit Sensor-Stammdaten.';

CREATE VIEW skytech.v_messwert_15min AS
SELECT m.zeit, s.id AS sensor_id, s.name, s.entity_id, s.attribut, s.kategorie, s.groesse, s.rolle,
       s.einheit, s.anlage, m.mittel, m.minimum, m.maximum, m.letzter, m.zuwachs, m.anzahl, m.abdeckung_s
FROM skytech.messwert_15min m
JOIN skytech.sensor s ON s.id = m.sensor_id;

CREATE VIEW skytech.v_messwert_1h AS
SELECT m.zeit, s.id AS sensor_id, s.name, s.entity_id, s.attribut, s.kategorie, s.groesse, s.rolle,
       s.einheit, s.anlage, m.mittel, m.minimum, m.maximum, m.letzter, m.zuwachs, m.anzahl, m.abdeckung_s
FROM skytech.messwert_1h m
JOIN skytech.sensor s ON s.id = m.sensor_id;

CREATE VIEW skytech.v_messwert_1d AS
SELECT m.zeit, s.id AS sensor_id, s.name, s.entity_id, s.attribut, s.kategorie, s.groesse, s.rolle,
       s.einheit, s.anlage, m.mittel, m.minimum, m.maximum, m.letzter, m.zuwachs, m.anzahl, m.abdeckung_s
FROM skytech.messwert_1d m
JOIN skytech.sensor s ON s.id = m.sensor_id;

-- Fachsichten auf Minutenbasis
CREATE VIEW skytech.v_pv AS SELECT * FROM skytech.v_messwert_1min WHERE kategorie = 'pv';
CREATE VIEW skytech.v_speicher AS SELECT * FROM skytech.v_messwert_1min WHERE kategorie = 'speicher';
CREATE VIEW skytech.v_netz AS SELECT * FROM skytech.v_messwert_1min WHERE kategorie = 'netz';
CREATE VIEW skytech.v_heizung AS SELECT * FROM skytech.v_messwert_1min WHERE kategorie = 'heizung';
CREATE VIEW skytech.v_verbraucher AS SELECT * FROM skytech.v_messwert_1min WHERE kategorie = 'verbraucher';

CREATE VIEW skytech.v_soll_ist AS
SELECT i.zeit,
       sist.soll_ist_paar AS paar,
       sist.anlage,
       sist.groesse,
       sist.einheit,
       so.mittel AS soll,
       i.mittel AS ist,
       i.mittel - so.mittel AS abweichung
FROM skytech.sensor sist
JOIN skytech.sensor ssoll ON ssoll.soll_ist_paar = sist.soll_ist_paar AND ssoll.rolle = 'soll'
JOIN skytech.messwert_1min i ON i.sensor_id = sist.id
JOIN skytech.messwert_1min so ON so.sensor_id = ssoll.id AND so.zeit = i.zeit
WHERE sist.rolle = 'ist';
COMMENT ON VIEW skytech.v_soll_ist IS 'Soll/Ist-Paare je Minute (Paar über sensor.soll_ist_paar).';

-- ---------------------------------------------------------------------------
-- Einstellungen, Migrationen, Änderungsprotokoll
-- ---------------------------------------------------------------------------

CREATE TABLE skytech_config.einstellung (
    schluessel   text PRIMARY KEY,
    wert         jsonb NOT NULL,
    beschreibung text NOT NULL,
    geaendert_am timestamptz NOT NULL DEFAULT now()
);

INSERT INTO skytech_config.einstellung (schluessel, wert, beschreibung) VALUES
    ('aufbewahrung_rohwerte_tage', '365', 'Rohwerte (skytech.messwert) werden nach so vielen Tagen gelöscht; null = nie.'),
    ('aufbewahrung_minutenwerte_tage', 'null', 'Minutenwerte (skytech.messwert_1min) werden nach so vielen Tagen gelöscht; null = nie. Mindestens 31, weil die Verdichtungen 30 Tage rückwirkend aktualisiert werden.');

CREATE TABLE skytech_config.migration (
    version       integer PRIMARY KEY,
    name          text NOT NULL,
    quelle        text NOT NULL CHECK (quelle IN ('system', 'anlage')),
    checksumme    text NOT NULL,
    angewendet_am timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE skytech_config.aenderungsprotokoll (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zeit     timestamptz NOT NULL DEFAULT now(),
    quelle   text NOT NULL CHECK (quelle IN ('ui', 'mcp', 'system')),
    benutzer text,
    aktion   text NOT NULL,
    details  jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX aenderungsprotokoll_zeit ON skytech_config.aenderungsprotokoll (zeit DESC);

-- Wendet die Aufbewahrung aus skytech_config.einstellung an. Wird vom
-- Verwaltungsdienst beim Start und nach jeder Änderung aufgerufen.
CREATE FUNCTION skytech_config.aufbewahrung_anwenden() RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    rohwerte_tage integer := (SELECT (wert #>> '{}')::integer FROM skytech_config.einstellung
                              WHERE schluessel = 'aufbewahrung_rohwerte_tage');
    minuten_tage  integer := (SELECT (wert #>> '{}')::integer FROM skytech_config.einstellung
                              WHERE schluessel = 'aufbewahrung_minutenwerte_tage');
BEGIN
    IF minuten_tage IS NOT NULL AND minuten_tage < 31 THEN
        RAISE EXCEPTION 'Minutenwerte müssen mindestens 31 Tage aufbewahrt werden (eingestellt: %).', minuten_tage;
    END IF;
    PERFORM remove_retention_policy('skytech.messwert', if_exists => true);
    IF rohwerte_tage IS NOT NULL THEN
        PERFORM add_retention_policy('skytech.messwert', make_interval(days => rohwerte_tage));
    END IF;
    PERFORM remove_retention_policy('skytech.messwert_1min', if_exists => true);
    IF minuten_tage IS NOT NULL THEN
        PERFORM add_retention_policy('skytech.messwert_1min', make_interval(days => minuten_tage));
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- Rechte (Rollen legt bootstrap.sql an)
-- ---------------------------------------------------------------------------

GRANT USAGE ON SCHEMA skytech, skytech_config TO skytech_collector, skytech_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA skytech, skytech_config TO skytech_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA skytech, skytech_config GRANT SELECT ON TABLES TO skytech_reader;

GRANT SELECT ON skytech.sensor TO skytech_collector;
GRANT SELECT, INSERT ON skytech.messwert TO skytech_collector;
GRANT SELECT, INSERT, UPDATE ON skytech.messwert_1min TO skytech_collector;
