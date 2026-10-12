-- 0003 Anbindung von SkytechHEMS (D-027, Vertrag contract_hems_data_insight 0.2).
-- Läuft als skytech_app. Die Rolle skytech_hems legt bootstrap.sql an.
--
-- Das HEMS schreibt ausschließlich über die Funktionen hems_* (SECURITY DEFINER).
-- Sie prüfen jede Eingabe, schreiben das Änderungsprotokoll und melden neue
-- Messwerte dem Collector. Die Rolle selbst hat nur EXECUTE und SELECT.

-- ---------------------------------------------------------------------------
-- Vom HEMS verwaltete Sensoren
-- ---------------------------------------------------------------------------

ALTER TABLE skytech.sensor
    ADD COLUMN verwaltet_von text CHECK (verwaltet_von IN ('hems'));
COMMENT ON COLUMN skytech.sensor.verwaltet_von IS
    'NULL = in Data Insight frei bearbeitbar; hems = über den Vertrag von SkytechHEMS verwaltet und gesperrt.';

-- Sperre: Verwaltete Sensoren ändert oder löscht nur das HEMS über seine
-- Funktionen. Sie setzen dafür transaktionslokal skytech.hems_verwaltung = an.
-- Gilt gleichermaßen für Oberfläche, MCP und direktes SQL.
CREATE FUNCTION skytech.sensor_verwaltung_schuetzen() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.verwaltet_von IS NOT NULL
       AND coalesce(current_setting('skytech.hems_verwaltung', true), '') <> 'an' THEN
        RAISE EXCEPTION 'Sensor % (%) wird über den Vertrag von Skytech HEMS verwaltet und lässt sich nur dort ändern.',
            OLD.id, OLD.entity_id
            USING ERRCODE = 'SKY01',
                  HINT = 'Im HEMS-Tab „Dynamischer Strompreis“ ändern.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER sensor_verwaltung_schutz BEFORE UPDATE OR DELETE ON skytech.sensor
    FOR EACH ROW EXECUTE FUNCTION skytech.sensor_verwaltung_schuetzen();

-- ---------------------------------------------------------------------------
-- Rolle → Sensor (nur ergänzt, nie geändert)
-- ---------------------------------------------------------------------------

CREATE TABLE skytech.hems_zuordnung (
    rolle      text        NOT NULL CHECK (rolle ~ '^[a-z_]+(:[a-z0-9_]+)?$'),
    sensor_id  integer     NOT NULL REFERENCES skytech.sensor(id),
    gueltig_ab timestamptz NOT NULL,
    PRIMARY KEY (rolle, gueltig_ab)
);
COMMENT ON TABLE skytech.hems_zuordnung IS
    'Welcher Sensor hinter einer HEMS-Rolle steht, ab wann. Die erste Zuordnung einer Rolle gilt ab -infinity.';

CREATE VIEW skytech.v_hems_zuordnung AS
SELECT z.rolle, z.sensor_id, s.entity_id, s.attribut, s.name, z.gueltig_ab,
       lead(z.gueltig_ab) OVER (PARTITION BY z.rolle ORDER BY z.gueltig_ab) AS gueltig_bis
FROM skytech.hems_zuordnung z
JOIN skytech.sensor s ON s.id = z.sensor_id;
COMMENT ON VIEW skytech.v_hems_zuordnung IS 'HEMS-Rollen mit Sensor und Gültigkeit; gueltig_bis NULL = aktuell.';

CREATE VIEW skytech.v_hems_rolle_15min AS
SELECT z.rolle, m.zeit, z.sensor_id, s.einheit, m.mittel, m.minimum, m.maximum, m.letzter, m.zuwachs,
       m.anzahl, m.abdeckung_s
FROM skytech.v_hems_zuordnung z
JOIN skytech.messwert_15min m
  ON m.sensor_id = z.sensor_id AND m.zeit >= z.gueltig_ab AND (z.gueltig_bis IS NULL OR m.zeit < z.gueltig_bis)
JOIN skytech.sensor s ON s.id = z.sensor_id;
COMMENT ON VIEW skytech.v_hems_rolle_15min IS '15-min-Werte je HEMS-Rolle, über Sensorwechsel hinweg zusammengesetzt.';

-- ---------------------------------------------------------------------------
-- Prognose- und Auswertungsläufe
-- ---------------------------------------------------------------------------

CREATE TABLE skytech.prognose_lauf (
    id          bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    art         text        NOT NULL CHECK (art IN ('preis', 'pv', 'verbrauch', 'auswertung')),
    quelle      text        NOT NULL CHECK (quelle <> ''),
    erstellt    timestamptz NOT NULL,
    raster_min  smallint    NOT NULL CHECK (raster_min IN (15, 60)),
    gueltig_ab  timestamptz NOT NULL,
    gueltig_bis timestamptz NOT NULL,
    einheit     text        NOT NULL,
    methode     text,
    details     jsonb       NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(details) = 'object'),
    CHECK (gueltig_bis > gueltig_ab)
);
CREATE INDEX prognose_lauf_art_erstellt ON skytech.prognose_lauf (art, erstellt DESC);
COMMENT ON TABLE skytech.prognose_lauf IS 'Ein Prognose-, Preis- oder Auswertungslauf des HEMS; wird nie geändert.';

CREATE TABLE skytech.prognose_wert (
    lauf_id bigint           NOT NULL REFERENCES skytech.prognose_lauf(id) ON DELETE CASCADE,
    zeit    timestamptz      NOT NULL,
    wert    double precision NOT NULL,
    p10     double precision,
    p90     double precision,
    PRIMARY KEY (lauf_id, zeit)
);
SELECT create_hypertable('skytech.prognose_wert', by_range('zeit', INTERVAL '30 days'));
CREATE INDEX prognose_wert_zeit ON skytech.prognose_wert (zeit DESC);
COMMENT ON TABLE skytech.prognose_wert IS 'Werte eines Laufs je Slot (zeit = Slot-Beginn, UTC).';

CREATE VIEW skytech.v_prognose_aktuell AS
SELECT DISTINCT ON (l.art, w.zeit)
       l.art, w.zeit, w.zeit + make_interval(mins => l.raster_min) AS bis, w.wert, w.p10, w.p90, l.einheit,
       l.id AS lauf_id, l.erstellt, l.quelle, l.details ->> 'ist_rolle' AS ist_rolle
FROM skytech.prognose_wert w
JOIN skytech.prognose_lauf l ON l.id = w.lauf_id
ORDER BY l.art, w.zeit, l.erstellt DESC, l.id DESC;
COMMENT ON VIEW skytech.v_prognose_aktuell IS 'Je Art und Slot der Wert aus dem jüngsten Lauf.';

CREATE VIEW skytech.v_prognose_vortag AS
SELECT DISTINCT ON (l.art, w.zeit)
       l.art, w.zeit, w.zeit + make_interval(mins => l.raster_min) AS bis, w.wert, w.p10, w.p90, l.einheit,
       l.id AS lauf_id, l.erstellt, l.quelle, l.details ->> 'ist_rolle' AS ist_rolle
FROM skytech.prognose_wert w
JOIN skytech.prognose_lauf l ON l.id = w.lauf_id
WHERE l.erstellt <= w.zeit - INTERVAL '24 hours'
ORDER BY l.art, w.zeit, l.erstellt DESC, l.id DESC;
COMMENT ON VIEW skytech.v_prognose_vortag IS 'Je Art und Slot der jüngste Lauf, der mindestens 24 h vor dem Slot erstellt wurde.';

CREATE VIEW skytech.v_preis AS
SELECT zeit, bis, wert AS preis_eur_kwh, lauf_id, erstellt
FROM skytech.v_prognose_aktuell
WHERE art = 'preis';
COMMENT ON VIEW skytech.v_preis IS 'Aktuelle Endpreiskurve in €/kWh.';

CREATE VIEW skytech.v_prognose_vs_ist AS
SELECT a.art, a.zeit, a.wert AS prognose, a.p10, a.p90,
       v.wert AS prognose_vortag, v.p10 AS p10_vortag, v.p90 AS p90_vortag,
       i.mittel AS ist, a.einheit, a.ist_rolle
FROM skytech.v_prognose_aktuell a
LEFT JOIN skytech.v_prognose_vortag v ON v.art = a.art AND v.zeit = a.zeit
LEFT JOIN skytech.v_hems_rolle_15min i ON i.rolle = a.ist_rolle AND i.zeit = a.zeit
WHERE a.art IN ('pv', 'verbrauch');
COMMENT ON VIEW skytech.v_prognose_vs_ist IS 'PV- und Verbrauchsprognose (aktuell und Vortag) neben dem Ist in W je 15 min.';

CREATE VIEW skytech.v_prognose_guete_tag AS
SELECT time_bucket(INTERVAL '1 day', zeit, 'Europe/Berlin') AS tag,
       art,
       count(*) AS slots,
       avg(abs(prognose_vortag - ist)) AS mittlerer_fehler_w,
       sum(prognose_vortag) * 0.25 / 1000 AS prognose_kwh,
       sum(ist) * 0.25 / 1000 AS ist_kwh,
       sum(prognose_vortag - ist) * 0.25 / 1000 AS energiefehler_kwh,
       avg(CASE WHEN ist BETWEEN p10_vortag AND p90_vortag THEN 1.0 ELSE 0.0 END)
           FILTER (WHERE p10_vortag IS NOT NULL AND p90_vortag IS NOT NULL) AS anteil_im_band
FROM skytech.v_prognose_vs_ist
WHERE ist IS NOT NULL AND prognose_vortag IS NOT NULL
GROUP BY 1, 2;
COMMENT ON VIEW skytech.v_prognose_guete_tag IS 'Prognosegüte (Vortagsprognose gegen Ist) je Berliner Tag und Art.';

CREATE VIEW skytech.v_hems_vertrag AS SELECT '0.2'::text AS version;
COMMENT ON VIEW skytech.v_hems_vertrag IS 'Version des Vertrags contract_hems_data_insight, die diese Datenbank erfüllt.';

-- ---------------------------------------------------------------------------
-- Änderungsprotokoll: Quelle hems
-- ---------------------------------------------------------------------------

ALTER TABLE skytech_config.aenderungsprotokoll DROP CONSTRAINT aenderungsprotokoll_quelle_check;
ALTER TABLE skytech_config.aenderungsprotokoll
    ADD CONSTRAINT aenderungsprotokoll_quelle_check CHECK (quelle IN ('ui', 'mcp', 'system', 'hems'));

CREATE FUNCTION skytech_config.hems_protokoll(p_aktion text, p_details jsonb) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = skytech_config, pg_temp AS $$
    INSERT INTO skytech_config.aenderungsprotokoll (quelle, benutzer, aktion, details)
    VALUES ('hems', 'skytech_hems', p_aktion, p_details);
$$;
REVOKE ALL ON FUNCTION skytech_config.hems_protokoll(text, jsonb) FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- Schreibfunktionen für das HEMS
-- ---------------------------------------------------------------------------

-- Legt einen Sensor an oder übernimmt einen vorhandenen (gleiche Entität und
-- gleiches Attribut) und gibt seine ID zurück. Setzt Name, Kategorie, Größe,
-- Einheit und aktiv = true.
CREATE FUNCTION skytech.hems_sensor_sichern(
    p_entity_id text, p_attribut text, p_name text, p_kategorie text, p_groesse text,
    p_einheit text, p_quelle text) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = skytech, pg_temp AS $$
DECLARE
    v_sensor skytech.sensor%ROWTYPE;
    v_id integer;
BEGIN
    IF p_quelle IS NULL OR p_quelle NOT IN ('ha', 'hems') THEN
        RAISE EXCEPTION 'Quelle muss ha oder hems sein, nicht %.', p_quelle USING ERRCODE = '22023';
    END IF;
    IF (p_quelle = 'hems') IS DISTINCT FROM (p_entity_id LIKE 'hems.%') THEN
        RAISE EXCEPTION 'Entität % passt nicht zur Quelle %: eigene Reihen heißen hems.<name>, HA-Sensoren nie.',
            p_entity_id, p_quelle USING ERRCODE = '22023';
    END IF;
    PERFORM set_config('skytech.hems_verwaltung', 'an', true);

    SELECT * INTO v_sensor FROM skytech.sensor
    WHERE entity_id = p_entity_id AND coalesce(attribut, '') = coalesce(p_attribut, '')
    FOR UPDATE;

    IF NOT FOUND THEN
        INSERT INTO skytech.sensor (entity_id, attribut, name, kategorie, groesse, einheit, quelle, verwaltet_von)
        VALUES (p_entity_id, p_attribut, p_name, p_kategorie, p_groesse, p_einheit, p_quelle, 'hems')
        RETURNING id INTO v_id;
        PERFORM skytech_config.hems_protokoll('hems_sensor_angelegt', jsonb_build_object(
            'id', v_id, 'entity_id', p_entity_id, 'attribut', p_attribut, 'quelle', p_quelle));
    ELSE
        v_id := v_sensor.id;
        IF v_sensor.quelle <> p_quelle THEN
            RAISE EXCEPTION 'Sensor % (%) hat die Quelle %, erwartet %.', v_id, p_entity_id, v_sensor.quelle, p_quelle
                USING ERRCODE = '22023';
        END IF;
        IF v_sensor.verwaltet_von IS NULL THEN
            UPDATE skytech.sensor SET verwaltet_von = 'hems' WHERE id = v_id;
            PERFORM skytech_config.hems_protokoll('hems_sensor_uebernommen', jsonb_build_object(
                'id', v_id, 'entity_id', p_entity_id, 'attribut', p_attribut));
        END IF;
        IF v_sensor.name IS DISTINCT FROM p_name OR v_sensor.kategorie IS DISTINCT FROM p_kategorie
           OR v_sensor.groesse IS DISTINCT FROM p_groesse OR v_sensor.einheit IS DISTINCT FROM p_einheit
           OR NOT v_sensor.aktiv THEN
            UPDATE skytech.sensor
            SET name = p_name, kategorie = p_kategorie, groesse = p_groesse, einheit = p_einheit, aktiv = true
            WHERE id = v_id;
            PERFORM skytech_config.hems_protokoll('hems_sensor_aktualisiert', jsonb_build_object(
                'id', v_id, 'name', p_name, 'kategorie', p_kategorie, 'groesse', p_groesse,
                'einheit', p_einheit, 'reaktiviert', NOT v_sensor.aktiv));
        END IF;
    END IF;

    PERFORM set_config('skytech.hems_verwaltung', '', true);
    RETURN v_id;
END
$$;

-- Legt einen verwalteten Sensor still; Messwerte bleiben erhalten.
CREATE FUNCTION skytech.hems_sensor_stilllegen(p_sensor_id integer) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = skytech, pg_temp AS $$
DECLARE
    v_sensor skytech.sensor%ROWTYPE;
BEGIN
    SELECT * INTO v_sensor FROM skytech.sensor WHERE id = p_sensor_id FOR UPDATE;
    IF NOT FOUND OR v_sensor.verwaltet_von IS DISTINCT FROM 'hems' THEN
        RAISE EXCEPTION 'Sensor % ist kein vom HEMS verwalteter Sensor.', p_sensor_id USING ERRCODE = '22023';
    END IF;
    IF v_sensor.aktiv THEN
        PERFORM set_config('skytech.hems_verwaltung', 'an', true);
        UPDATE skytech.sensor SET aktiv = false WHERE id = p_sensor_id;
        PERFORM set_config('skytech.hems_verwaltung', '', true);
        PERFORM skytech_config.hems_protokoll('hems_sensor_stillgelegt', jsonb_build_object(
            'id', p_sensor_id, 'entity_id', v_sensor.entity_id));
    END IF;
END
$$;

-- Ordnet einer Rolle einen verwalteten Sensor zu. Unveränderte Zuordnung: nichts.
CREATE FUNCTION skytech.hems_zuordnen(p_rolle text, p_sensor_id integer) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = skytech, pg_temp AS $$
DECLARE
    v_aktuell integer;
    v_gefunden boolean;
BEGIN
    IF NOT EXISTS (SELECT FROM skytech.sensor WHERE id = p_sensor_id AND verwaltet_von = 'hems') THEN
        RAISE EXCEPTION 'Sensor % ist kein vom HEMS verwalteter Sensor.', p_sensor_id USING ERRCODE = '22023';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext('skytech.hems_zuordnung:' || p_rolle));
    SELECT sensor_id INTO v_aktuell FROM skytech.hems_zuordnung
    WHERE rolle = p_rolle ORDER BY gueltig_ab DESC LIMIT 1;
    v_gefunden := FOUND;
    IF v_gefunden AND v_aktuell = p_sensor_id THEN
        RETURN;
    END IF;
    INSERT INTO skytech.hems_zuordnung (rolle, sensor_id, gueltig_ab)
    VALUES (p_rolle, p_sensor_id, CASE WHEN v_gefunden THEN clock_timestamp() ELSE '-infinity'::timestamptz END);
    PERFORM skytech_config.hems_protokoll('hems_zuordnung', jsonb_build_object(
        'rolle', p_rolle, 'sensor_id', p_sensor_id, 'vorher', v_aktuell));
END
$$;

-- Schreibt Rohwerte einer eigenen Reihe (Quelle hems). Vorhandene Zeitpunkte
-- bleiben unverändert. Meldet neue Werte dem Collector, damit er die
-- Minutenwerte ab dem frühesten Zeitpunkt neu rechnet. Gibt die Anzahl neuer
-- Werte zurück.
CREATE FUNCTION skytech.hems_messwerte_schreiben(
    p_sensor_id integer, p_zeiten timestamptz[], p_werte double precision[]) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = skytech, pg_temp AS $$
DECLARE
    v_anzahl integer;
    v_ab timestamptz;
BEGIN
    IF NOT EXISTS (SELECT FROM skytech.sensor
                   WHERE id = p_sensor_id AND verwaltet_von = 'hems' AND quelle = 'hems' AND aktiv) THEN
        RAISE EXCEPTION 'Sensor % ist keine aktive, vom HEMS verwaltete Reihe mit Quelle hems.', p_sensor_id
            USING ERRCODE = '22023';
    END IF;
    IF p_zeiten IS NULL OR p_werte IS NULL OR cardinality(p_zeiten) <> cardinality(p_werte) THEN
        RAISE EXCEPTION 'Zeiten und Werte müssen gleich lang sein.' USING ERRCODE = '22023';
    END IF;
    IF cardinality(p_zeiten) = 0 THEN
        RETURN 0;
    END IF;
    IF cardinality(p_zeiten) > 10000 THEN
        RAISE EXCEPTION 'Höchstens 10000 Werte je Aufruf.' USING ERRCODE = '22023';
    END IF;
    IF EXISTS (SELECT FROM unnest(p_zeiten) z WHERE z IS NULL OR z > clock_timestamp()) THEN
        RAISE EXCEPTION 'Zeitpunkte dürfen weder leer noch in der Zukunft sein.' USING ERRCODE = '22023';
    END IF;
    IF EXISTS (SELECT FROM unnest(p_werte) w WHERE w IS NOT NULL AND w IN ('NaN', 'Infinity', '-Infinity')) THEN
        RAISE EXCEPTION 'Werte müssen endlich sein.' USING ERRCODE = '22023';
    END IF;

    WITH neu AS (
        INSERT INTO skytech.messwert (zeit, sensor_id, wert, text_wert)
        SELECT z, p_sensor_id, w, NULL FROM unnest(p_zeiten, p_werte) AS t(z, w)
        ON CONFLICT (sensor_id, zeit) DO NOTHING
        RETURNING zeit
    )
    SELECT count(*), min(zeit) INTO v_anzahl, v_ab FROM neu;

    IF v_anzahl > 0 THEN
        PERFORM pg_notify('skytech_hems_werte', json_build_object('sensor_id', p_sensor_id, 'ab', v_ab)::text);
    END IF;
    RETURN v_anzahl;
END
$$;

-- Schreibt einen vollständigen Lauf in einer Transaktion und gibt seine ID zurück.
CREATE FUNCTION skytech.hems_lauf_schreiben(
    p_art text, p_quelle text, p_erstellt timestamptz, p_raster_min integer,
    p_gueltig_ab timestamptz, p_gueltig_bis timestamptz, p_einheit text, p_methode text, p_details jsonb,
    p_zeiten timestamptz[], p_werte double precision[],
    p_p10 double precision[] DEFAULT NULL, p_p90 double precision[] DEFAULT NULL) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = skytech, pg_temp AS $$
DECLARE
    v_pflicht text[];
    v_fehlt text[];
    v_id bigint;
    v_anzahl integer := coalesce(cardinality(p_zeiten), 0);
BEGIN
    IF p_details IS NULL OR jsonb_typeof(p_details) <> 'object' THEN
        RAISE EXCEPTION 'details muss ein JSON-Objekt sein.' USING ERRCODE = '22023';
    END IF;
    IF p_gueltig_ab IS NULL OR p_gueltig_bis IS NULL OR p_gueltig_bis <= p_gueltig_ab THEN
        RAISE EXCEPTION 'gueltig_bis muss nach gueltig_ab liegen.' USING ERRCODE = '22023';
    END IF;
    v_pflicht := CASE p_art
        WHEN 'preis' THEN ARRAY['entity']
        WHEN 'pv' THEN ARRAY['entity', 'ist_rolle', 'heute_kwh', 'morgen_kwh', 'rest_heute_kwh']
        WHEN 'verbrauch' THEN ARRAY['ist_rolle', 'historie_tage', 'parameter']
        WHEN 'auswertung' THEN ARRAY[]::text[]
    END;
    IF v_pflicht IS NULL THEN
        RAISE EXCEPTION 'Unbekannte Art %.', p_art USING ERRCODE = '22023';
    END IF;
    SELECT array_agg(k) INTO v_fehlt FROM unnest(v_pflicht) k WHERE NOT p_details ? k;
    IF v_fehlt IS NOT NULL THEN
        RAISE EXCEPTION 'In details fehlt: %.', array_to_string(v_fehlt, ', ') USING ERRCODE = '22023';
    END IF;
    IF p_art IN ('pv', 'verbrauch') AND p_raster_min <> 15 THEN
        RAISE EXCEPTION 'PV- und Verbrauchsläufe haben ein 15-min-Raster.' USING ERRCODE = '22023';
    END IF;

    IF p_art = 'auswertung' THEN
        IF v_anzahl > 0 THEN
            RAISE EXCEPTION 'Ein Auswertungslauf hat keine Werte.' USING ERRCODE = '22023';
        END IF;
    ELSE
        IF v_anzahl = 0 OR cardinality(p_werte) IS DISTINCT FROM v_anzahl
           OR (p_p10 IS NOT NULL AND cardinality(p_p10) <> v_anzahl)
           OR (p_p90 IS NOT NULL AND cardinality(p_p90) <> v_anzahl) THEN
            RAISE EXCEPTION 'Zeiten, Werte, p10 und p90 müssen gleich lang und nicht leer sein.' USING ERRCODE = '22023';
        END IF;
        IF EXISTS (SELECT FROM unnest(p_zeiten) z WHERE z IS NULL OR z < p_gueltig_ab OR z >= p_gueltig_bis) THEN
            RAISE EXCEPTION 'Alle Zeitpunkte müssen im Gültigkeitszeitraum liegen.' USING ERRCODE = '22023';
        END IF;
        IF EXISTS (SELECT FROM unnest(p_werte) w WHERE w IS NULL OR w IN ('NaN', 'Infinity', '-Infinity')) THEN
            RAISE EXCEPTION 'Werte müssen endlich sein.' USING ERRCODE = '22023';
        END IF;
    END IF;

    INSERT INTO skytech.prognose_lauf (art, quelle, erstellt, raster_min, gueltig_ab, gueltig_bis, einheit, methode, details)
    VALUES (p_art, p_quelle, p_erstellt, p_raster_min, p_gueltig_ab, p_gueltig_bis, p_einheit, p_methode, p_details)
    RETURNING id INTO v_id;

    IF v_anzahl > 0 THEN
        INSERT INTO skytech.prognose_wert (lauf_id, zeit, wert, p10, p90)
        SELECT v_id, z, w, a, b FROM unnest(p_zeiten, p_werte, p_p10, p_p90) AS t(z, w, a, b);
    END IF;
    RETURN v_id;
END
$$;

-- ---------------------------------------------------------------------------
-- Aufbewahrung der Prognoseläufe (Preisläufe ohne Ablauf)
-- ---------------------------------------------------------------------------

INSERT INTO skytech_config.einstellung (schluessel, wert, beschreibung) VALUES
    ('aufbewahrung_prognose_tage', '365',
     'PV-, Verbrauchs- und Auswertungsläufe des HEMS werden nach so vielen Tagen gelöscht; null = nie. Preisläufe bleiben immer.');

CREATE PROCEDURE skytech_config.prognose_aufraeumen(job_id integer, config jsonb) LANGUAGE plpgsql AS $$
DECLARE
    tage integer := (SELECT (wert #>> '{}')::integer FROM skytech_config.einstellung
                     WHERE schluessel = 'aufbewahrung_prognose_tage');
BEGIN
    IF tage IS NOT NULL THEN
        DELETE FROM skytech.prognose_lauf
        WHERE art <> 'preis' AND erstellt < now() - make_interval(days => tage);
    END IF;
END
$$;
SELECT add_job('skytech_config.prognose_aufraeumen', INTERVAL '1 day');

-- ---------------------------------------------------------------------------
-- Rechte der Rolle skytech_hems (abschließend, Vertrag Abschnitt „Rechte“)
-- ---------------------------------------------------------------------------

REVOKE ALL ON FUNCTION skytech.hems_sensor_sichern(text, text, text, text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION skytech.hems_sensor_stilllegen(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION skytech.hems_zuordnen(text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION skytech.hems_messwerte_schreiben(integer, timestamptz[], double precision[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION skytech.hems_lauf_schreiben(text, text, timestamptz, integer, timestamptz, timestamptz, text, text,
                                                   jsonb, timestamptz[], double precision[], double precision[],
                                                   double precision[]) FROM PUBLIC;

GRANT USAGE ON SCHEMA skytech TO skytech_hems;
GRANT SELECT ON skytech.sensor, skytech.kategorie, skytech.groesse, skytech.v_messwert_15min, skytech.v_messwert_1h,
    skytech.hems_zuordnung, skytech.v_hems_zuordnung, skytech.v_hems_rolle_15min,
    skytech.prognose_lauf, skytech.prognose_wert, skytech.v_prognose_aktuell, skytech.v_prognose_vortag,
    skytech.v_preis, skytech.v_prognose_vs_ist, skytech.v_prognose_guete_tag, skytech.v_hems_vertrag
    TO skytech_hems;
GRANT EXECUTE ON FUNCTION skytech.hems_sensor_sichern(text, text, text, text, text, text, text),
    skytech.hems_sensor_stilllegen(integer),
    skytech.hems_zuordnen(text, integer),
    skytech.hems_messwerte_schreiben(integer, timestamptz[], double precision[]),
    skytech.hems_lauf_schreiben(text, text, timestamptz, integer, timestamptz, timestamptz, text, text, jsonb,
                                timestamptz[], double precision[], double precision[], double precision[])
    TO skytech_hems;
