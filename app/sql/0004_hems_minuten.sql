-- 0004 HEMS-Reihen je Minute und Energiezähler (D-027, Vertrag contract_hems_data_insight 0.3).
-- Läuft als skytech_app.
--
-- * Reihen mit quelle = 'hems' werden nicht mehr fortgeführt: ein Rohwert gilt
--   genau für seine Minute (app/minute_values.py). Die bisher fortgeführten
--   Minutenwerte (anzahl = 0) entfallen hier; die Verdichtungen ziehen über ihre
--   Policy nach (30 Tage rückwirkend).
--   Die Bereinigung filtert mit festen Sensor-IDs und festem Zeitbeginn: Ein
--   DELETE mit Join ohne Zeitfilter entpackt alle komprimierten Chunks und
--   scheitert an timescaledb.max_tuples_decompressed_per_dml_transaction
--   (Referenzanlage 13.10.2026: 132 036 Zeilen bei Grenze 100 000).
-- * Sicht v_hems_rolle_1min: Minutenwerte je Rolle, für die Grundlast je Minute.
-- * hems_sensor_sichern setzt zusätzlich energie_zaehler (Zählerrollen).

-- ---------------------------------------------------------------------------
-- Fortgeführte Minutenwerte der HEMS-Reihen entfernen
-- ---------------------------------------------------------------------------

-- Bereinigung: Anfang
DO $$
DECLARE
    v_sensoren integer[];
    v_ab timestamptz;
BEGIN
    SELECT array_agg(id) INTO v_sensoren FROM skytech.sensor WHERE quelle = 'hems';
    IF v_sensoren IS NULL THEN
        RETURN;
    END IF;
    -- Fortgeführt wird erst ab dem ersten Rohwert einer Reihe.
    SELECT date_trunc('minute', min(zeit)) INTO v_ab FROM skytech.messwert WHERE sensor_id = ANY(v_sensoren);
    IF v_ab IS NULL THEN
        RETURN;
    END IF;
    -- Nur für diese Transaktion: liegen HEMS-Minuten schon in komprimierten Chunks, dürfen deren
    -- Segmente entpackt werden. Andere Chunks schließen die Literale unten aus.
    PERFORM set_config('timescaledb.max_tuples_decompressed_per_dml_transaction', '0', true);
    EXECUTE format(
        'DELETE FROM skytech.messwert_1min WHERE sensor_id = ANY(%L::integer[]) AND zeit >= %L::timestamptz '
        'AND anzahl = 0', v_sensoren, v_ab);
END
$$;
-- Bereinigung: Ende

-- ---------------------------------------------------------------------------
-- Minutenwerte je Rolle
-- ---------------------------------------------------------------------------

CREATE VIEW skytech.v_hems_rolle_1min AS
SELECT z.rolle, m.zeit, z.sensor_id, s.einheit, m.mittel, m.minimum, m.maximum, m.letzter, m.zuwachs,
       m.anzahl, m.abdeckung_s
FROM skytech.v_hems_zuordnung z
JOIN skytech.messwert_1min m
  ON m.sensor_id = z.sensor_id AND m.zeit >= z.gueltig_ab AND (z.gueltig_bis IS NULL OR m.zeit < z.gueltig_bis)
JOIN skytech.sensor s ON s.id = z.sensor_id;
COMMENT ON VIEW skytech.v_hems_rolle_1min IS 'Minutenwerte je HEMS-Rolle, über Sensorwechsel hinweg zusammengesetzt.';

-- ---------------------------------------------------------------------------
-- hems_sensor_sichern mit Zählerkennzeichen
-- ---------------------------------------------------------------------------

DROP FUNCTION skytech.hems_sensor_sichern(text, text, text, text, text, text, text);

-- Legt einen Sensor an oder übernimmt einen vorhandenen (gleiche Entität und
-- gleiches Attribut) und gibt seine ID zurück. Setzt Name, Kategorie, Größe,
-- Einheit, Zählerkennzeichen und aktiv = true.
CREATE FUNCTION skytech.hems_sensor_sichern(
    p_entity_id text, p_attribut text, p_name text, p_kategorie text, p_groesse text,
    p_einheit text, p_quelle text, p_energie_zaehler boolean) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = skytech, pg_temp AS $$
DECLARE
    v_sensor skytech.sensor%ROWTYPE;
    v_id integer;
    v_zaehler boolean := coalesce(p_energie_zaehler, false);
BEGIN
    IF p_quelle IS NULL OR p_quelle NOT IN ('ha', 'hems') THEN
        RAISE EXCEPTION 'Quelle muss ha oder hems sein, nicht %.', p_quelle USING ERRCODE = '22023';
    END IF;
    IF (p_quelle = 'hems') IS DISTINCT FROM (p_entity_id LIKE 'hems.%') THEN
        RAISE EXCEPTION 'Entität % passt nicht zur Quelle %: eigene Reihen heißen hems.<name>, HA-Sensoren nie.',
            p_entity_id, p_quelle USING ERRCODE = '22023';
    END IF;
    IF v_zaehler AND p_quelle = 'hems' THEN
        RAISE EXCEPTION 'Eigene Reihen hems.<name> sind keine Zähler.' USING ERRCODE = '22023';
    END IF;
    PERFORM set_config('skytech.hems_verwaltung', 'an', true);

    SELECT * INTO v_sensor FROM skytech.sensor
    WHERE entity_id = p_entity_id AND coalesce(attribut, '') = coalesce(p_attribut, '')
    FOR UPDATE;

    IF NOT FOUND THEN
        INSERT INTO skytech.sensor (entity_id, attribut, name, kategorie, groesse, einheit, quelle, verwaltet_von,
                                    energie_zaehler)
        VALUES (p_entity_id, p_attribut, p_name, p_kategorie, p_groesse, p_einheit, p_quelle, 'hems', v_zaehler)
        RETURNING id INTO v_id;
        PERFORM skytech_config.hems_protokoll('hems_sensor_angelegt', jsonb_build_object(
            'id', v_id, 'entity_id', p_entity_id, 'attribut', p_attribut, 'quelle', p_quelle,
            'energie_zaehler', v_zaehler));
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
           OR v_sensor.energie_zaehler IS DISTINCT FROM v_zaehler OR NOT v_sensor.aktiv THEN
            UPDATE skytech.sensor
            SET name = p_name, kategorie = p_kategorie, groesse = p_groesse, einheit = p_einheit,
                energie_zaehler = v_zaehler, aktiv = true
            WHERE id = v_id;
            PERFORM skytech_config.hems_protokoll('hems_sensor_aktualisiert', jsonb_build_object(
                'id', v_id, 'name', p_name, 'kategorie', p_kategorie, 'groesse', p_groesse,
                'einheit', p_einheit, 'energie_zaehler', v_zaehler, 'reaktiviert', NOT v_sensor.aktiv));
        END IF;
    END IF;

    PERFORM set_config('skytech.hems_verwaltung', '', true);
    RETURN v_id;
END
$$;

REVOKE ALL ON FUNCTION skytech.hems_sensor_sichern(text, text, text, text, text, text, text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION skytech.hems_sensor_sichern(text, text, text, text, text, text, text, boolean)
    TO skytech_hems;
GRANT SELECT ON skytech.v_hems_rolle_1min TO skytech_hems;

-- ---------------------------------------------------------------------------
-- Vertragsversion
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW skytech.v_hems_vertrag AS SELECT '0.3'::text AS version;
