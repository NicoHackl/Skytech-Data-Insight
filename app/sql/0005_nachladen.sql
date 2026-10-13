-- 0005 Nachladen aus dem HA-Verlauf mit gespeichertem Stand.
-- Läuft als skytech_app.
--
-- Nach jedem Neustart von Data Insight oder Home Assistant fehlt die Zeit
-- dazwischen. Der Collector trägt sie hier als Lücke ein und lädt sie im
-- Hintergrund in kleinen Stücken nach. Scheitert ein Stück, bleibt die Lücke
-- offen und wird später erneut versucht – auch nach einem weiteren Neustart.
-- Bis 0.7.1 gab es nur einen einzigen Versuch, und der scheiterte an der Größe
-- der Antwort (Referenzanlage 13.10.2026).

CREATE TABLE skytech_config.nachlade_luecke (
    id             bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    von            timestamptz NOT NULL,
    bis            timestamptz NOT NULL CHECK (bis > von),
    erstellt_am    timestamptz NOT NULL DEFAULT now(),
    erledigt_am    timestamptz,
    versuche       integer     NOT NULL DEFAULT 0,
    letzter_fehler text
);
CREATE INDEX nachlade_luecke_offen ON skytech_config.nachlade_luecke (von) WHERE erledigt_am IS NULL;
COMMENT ON TABLE skytech_config.nachlade_luecke IS
    'Zeiträume ohne Aufzeichnung, die der Collector aus dem HA-Verlauf nachlädt; von rückt mit dem Fortschritt vor.';

GRANT SELECT, INSERT, UPDATE ON skytech_config.nachlade_luecke TO skytech_collector;
