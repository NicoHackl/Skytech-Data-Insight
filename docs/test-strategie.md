# Test-Strategie

## Testarten

| Art | Werkzeug | Umfang |
|---|---|---|
| Unit-Tests Python | `pytest -q` | Wertumsetzung, Vorschläge, Eingabeprüfung, Collector (Änderungserkennung, Attribute, Puffer, verspätete Werte), HA-Client gegen nachgebauten HA (`tests/fake_ha.py`: Anmeldung, Abo, Verlauf, Neuverbindung), Dienstprüfungen, Status-API |
| Integration Datenbank | `SKYTECH_TEST_DSN=… pytest -q` | gegen echte TimescaleDB: Migrationen (idempotent, Prüfsumme, Anlagen-Migration), Minutenwerte (zeitgewichtet, Lücken, Zähler-Neustart, wiederholbar), Verdichtungen (Gewichtung, Berliner Tag), Aufbewahrung, Rollenrechte, Sensorverwaltung samt Protokoll, Collector Ende-zu-Ende mit Nachladen und NOTIFY, HEMS-Anbindung (Rechte von `skytech_hems`, Übernahme und Sperre, Sensortausch ohne Lücke, nachgerechnete HEMS-Reihen, Läufe, Sichten, Prognosegüte, Aufräumen). Ohne `SKYTECH_TEST_DSN` übersprungen; die CI stellt die Datenbank bereit |
| Paketierung | `pytest` (`tests/test_packaging.py`) | Manifest, Übersetzungen, s6-Dienste und Abhängigkeiten, jeder Vorlagen-Platzhalter wird gesetzt, Ingress-Sperre und LAN-Header-Entfernung |
| Lint | `ruff check app tests`, ShellCheck (CI) | Python und Init-/Dienstskripte |
| Frontend | `cd web && npm run build` | Typprüfung und Bundle; CI prüft Drift des eingecheckten Bundles |
| Sicherung | `pytest` (`tests/test_backup.py`) | Namensmuster und Pfadschutz, Aufbewahrung, Paketprüfung, sicheres Auspacken, Grafana-Kopie, Ablauf und Fehlerfall der Wiederherstellung |
| Container-Rauchtest | CI-Job `image` | Image bauen, starten, Datenbank und Grafana gesund, Migrationen gelaufen, Sensor-API antwortet, Grafana über Ingress-Port, LAN-Login und Abwehr gefälschter Header |

## Integrationstests lokal

```bash
docker run -d --name tsdb-test -e POSTGRES_PASSWORD=test -p 15432:5432 timescale/timescaledb:2.30.1-pg17
SKYTECH_TEST_DSN=postgresql://postgres:test@127.0.0.1:15432/postgres pytest -q
```

`tests/test_dashboards.py` legt dabei eine eigene Datenbank `skytech_dashboard_test` an, migriert
sie und führt jede SQL-Abfrage der Dashboards unter `grafana/dashboards/` mit der Rolle
`skytech_reader` aus (Grafana-Makros und Variablen durch feste Werte ersetzt). Ohne
`SKYTECH_TEST_DSN` läuft nur die Strukturprüfung.

Neustarts (seit 13.10.2026): Nachladen in Fenstern ≤ 1 h und Gruppen ≤ 5 ohne Attribute, erster
Versuch mit Verbindungsabbruch und Wiederholung, ältere Werte landen trotz schon aufgenommenem
aktuellem Zustand, offene Lücke über einen Neustart hinweg, HEMS-Rohwerte ohne Meldung bekommen
beim Start Minutenwerte, Aufzeichnung startet trotz gescheiterter Migration.

## Migrationen gegen eine Sicherung der echten Datenbank (Pflicht vor Release)

Leere Testdatenbanken zeigen keine Probleme mit Datenmengen oder Kompression – Migration 0004
scheiterte am 13.10.2026 erst an der Referenzanlage an komprimierten Chunks. Deshalb vor jedem
Release mit einer neuen Migration:

1. Auf der Seite „Sicherungen“ eine aktuelle Sicherung erstellen und herunterladen (`.dump`).
2. In den Testcontainer (dieselbe TimescaleDB-Version) einspielen:

   ```bash
   docker cp skytech.dump tsdb-test:/tmp/skytech.dump
   docker exec tsdb-test psql -U postgres -c "DROP DATABASE IF EXISTS skytech_kopie WITH (FORCE)" \
     -c "CREATE DATABASE skytech_kopie OWNER skytech_app"
   docker exec tsdb-test psql -U postgres -d skytech_kopie -c "CREATE EXTENSION IF NOT EXISTS timescaledb" \
     -c "SELECT timescaledb_pre_restore()"
   docker exec tsdb-test pg_restore -U postgres -d skytech_kopie /tmp/skytech.dump
   docker exec tsdb-test psql -U postgres -d skytech_kopie -c "SELECT timescaledb_post_restore()"
   ```

   Wie im Add-on (`restore-db.sh`) als `postgres` und mit Eigentümern – mit `--role=skytech_app`
   fehlen die Rechte auf den TimescaleDB-Katalog, und die Messwerte fehlen danach. Die Rollen
   (`skytech_app`, `skytech_collector`, `skytech_reader`, `skytech_hems`, `skytech_grafana`, …)
   müssen existieren; die Integrationstests legen sie an, sonst vorher `CREATE ROLE … LOGIN`.
   Danach prüfen: `skytech_config.migration`, Zahl der Roh- und Minutenwerte, komprimierte Chunks.
3. Die neuen Migrationen als `skytech_app` mit `migration_runner.migrate` darauf laufen lassen und
   die Dauer notieren; neue Abfragen des Collectors ebenso einmal ausführen. Scheitert etwas, wird
   nicht veröffentlicht. Erstmals so geprüft am 13.10.2026 (Migration 0005: 0,01 s auf
   2,6 Mio. Rohwerten mit 2 komprimierten Chunks).
4. Datenbank `skytech_kopie` und die Sicherung danach löschen; sie enthalten echte Messwerte.

## Lokaler Containertest (amd64)

Auf einem Mac mit Apple-Chip läuft der amd64-Container über Rosetta in Colima:

```bash
colima start --profile amd64 --vm-type vz --vz-rosetta --cpu 4 --memory 6
docker build --platform linux/amd64 --build-arg BUILD_VERSION=lokal -t skytech-data-insight .
docker volume create sdi-data
docker run --rm --platform linux/amd64 -v sdi-data:/data --entrypoint sh skytech-data-insight \
  -c 'echo "{\"log_level\":\"info\",\"grafana_admin_password\":\"lokal-test\"}" > /data/options.json'
docker run -d --name sdi --platform linux/amd64 -v sdi-data:/data -p 18099:8099 -p 13000:3000 skytech-data-insight
```

| Prüfung | Aufruf | Erwartung |
|---|---|---|
| Status | `curl http://127.0.0.1:18099/api/status` | beide Dienste `is_ok: true` |
| Grafana wie über Ingress | `curl -H "X-Remote-User-Name: test" http://127.0.0.1:18099/grafana/api/user` | Benutzer `test` |
| Grafana im LAN | Browser `http://127.0.0.1:13000/` | Weiterleitung, Grafana-Login |

Mit Aufzeichnung: einen nachgebauten HA starten (z. B. `tests/fake_ha.py` in einem kleinen Skript,
das Werte laufend ändert) und den Container zusätzlich mit
`-p 15433:5432 -e SKYTECH_HA_URL=ws://host.lima.internal:<port>/api/websocket -e SKYTECH_HA_TOKEN=<token>`
starten; in `options.json` `db_password`/`db_readonly_password` setzen.

Für einen Browsertest der Oberfläche unter dem vollen Ingress-Pfad genügt ein kleiner Proxy, der
`/api/hassio_ingress/lokaltest` entfernt und auf Port 18099 weiterreicht – so arbeitet der
Supervisor.

## Pflicht vor jedem Commit

`ruff check app tests` und `pytest -q` fehlerfrei; bei Änderungen an `web/` Build und Bundle
mitcommitten; bei Änderungen an `rootfs/` oder `Dockerfile` den lokalen Containertest.

## Sicherung im Container prüfen (vor Releases mit Änderungen an M2)

1. `curl -o paket.tar http://127.0.0.1:18099/api/backups/download`, Daten ändern, Paket per
   `PUT api/backups/upload` hochladen, `POST api/backups/<datei>/restore` → Änderungen sind weg,
   Grafana-Dashboards wie im Paket, Aufzeichnung läuft weiter.
2. HA-Weg: `docker exec <container> /usr/bin/skytech-backup-pre`, Container stoppen, im Volume
   `pgdata` löschen, starten → Protokoll „Wiederherstellung aus einem Home-Assistant-Backup
   erkannt", Daten vollständig.
