# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Add-on-Version in `config.yaml` wird bei jedem Merge nach `main` automatisch
um eine Patch-Stelle erhöht (siehe `.github/workflows/bump-version.yaml`).

## [Unreleased]

### Hinzugefügt (Meilenstein M2, Version 0.4.0)

- **Daten im Home-Assistant-Backup, richtig gesichert.** Vor jedem HA-Backup legt das Add-on einen
  Datenbank-Dump und eine konsistente Kopie der Grafana-Datenbank an; das Datenbankverzeichnis
  selbst und die lokalen Sicherungen sind ausgeschlossen. Nach dem Wiederherstellen eines
  HA-Backups spielt das Add-on den Dump beim Start automatisch ein und lädt die Lücke aus dem
  HA-Verlauf nach (D-023).
- **Seite „Sicherungen".** Komplettsicherung (Datenbank und Grafana-Dashboards) als `.tar`
  herunterladen; `.tar` oder `.dump` hochladen, prüfen lassen und nach Bestätigung einspielen –
  vorher wird der aktuelle Stand gesichert, Aufzeichnung und MCP-Server starten dabei kurz neu
  (D-024). Liste der lokalen Sicherungen mit Herunterladen, Einspielen, Löschen und „Jetzt sichern".
- Aufbewahrung lokaler Sicherungen je Art (z. B. 20 vor MCP-Änderungen, 5 hochgeladene).

### Behoben

- **Minutenwerte blieben stehen (0.4.1).** Auf einer Anlage hörte die Berechnung der Minutenwerte
  nach einem Neustart still auf, während die Rohwerte weiter aufgezeichnet wurden – Grafana zeigte
  ab da keine Werte mehr. Die Schleifen der Aufzeichnung fangen jetzt jede Ausnahme ab, protokollieren
  sie mit Ursache und laufen weiter; die Übersicht meldet „Minutenwerte stehen seit …", sobald die
  Berechnung mehr als drei Minuten zurückliegt. Fehlende Minuten werden beim nächsten Start aus den
  Rohwerten nachgerechnet.
- MCP-Werkzeuge für Grafana melden einen nicht erreichbaren Grafana (z. B. während eines
  Neustarts) jetzt als verständlichen Fehler statt als interne Ausnahme.


### Hinzugefügt (Version 0.3.0, MCP vorgezogen)

- **MCP-Server für LLMs** (Port 8765, `http://<ha>:8765/mcp`, Anmeldung mit der neuen Option
  `mcp_token`): Werkzeuge zum Lesen (Schema, SQL, Statistik, Sensoren, Katalog, Sicherungen,
  Grafana) und Schreiben (SQL, Migrationen, Sensoren, Aufbewahrung, Grafana-Dashboards). Vor jeder
  schreibenden Datenbank-Aktion automatisch eine Sicherung (`pg_dump`, die letzten 20 bleiben),
  jede Aktion im Änderungsprotokoll mit Quelle `mcp`. Einrichtung für Claude Code, Claude Desktop
  und andere Clients in `docs/mcp.md` (D-021).
- **Grafana-Datenquelle „Skytech DB"** wird automatisch eingerichtet (`uid: skytech-db`, nur lesend
  über die interne Rolle `skytech_grafana`); Dashboards funktionieren damit ohne weitere
  Einrichtung (D-022).
- Anlagen-Migrationen über MCP werden ab Nummer 1000 angelegt.


### Hinzugefügt (Meilenstein M1, Version 0.2.0)

- **Aufzeichnung von HA-Werten.** Das Add-on verbindet sich über den Supervisor mit der
  WebSocket-API von Home Assistant und schreibt jede Änderung ausgewählter Entitäten – oder
  einzelner Attribute – nach `skytech.messwert`. `on`/`off` wird zusätzlich als 1/0 gespeichert
  (D-017). Geschrieben wird gebündelt alle 2 s; fällt die Datenbank kurz aus, bleiben die Werte im
  Puffer. Nach einem Neustart oder Verbindungsabbruch lädt das Add-on die Lücke aus dem HA-Verlauf
  nach (bis 10 Tage).
- **Minutenwerte und Verdichtungen.** Je Minute ein zeitgewichtetes Mittel, Minimum, Maximum,
  letzter Wert und bei Zählern der Zuwachs (mit Neustart-Erkennung), dazu 15-Minuten-, Stunden-
  und Tageswerte (Berliner Kalendertag) als Continuous Aggregates (D-015). Rohwerte werden nach
  7 Tagen komprimiert und standardmäßig nach 365 Tagen gelöscht, Verdichtungen bleiben.
- **Sichten für SQL und Grafana:** `v_messwert*` je Stufe mit Stammdaten, `v_pv`, `v_speicher`,
  `v_netz`, `v_heizung`, `v_verbraucher` und `v_soll_ist` (Paare über einen Paarnamen, D-016).
- **Seite „Sensoren".** Liste mit Suche, Kategorie-Filter, letztem Wert und Schalter zum Pausieren;
  „Sensoren hinzufügen" mit Suche über alle HA-Entitäten, Mehrfachauswahl, Attributen („Alle
  Attribute übernehmen"), Vorschlägen aus Einheit/Geräteklasse und „Für alle setzen"; Bearbeiten
  und Löschen. Vorgezogen aus M3 (D-019). Jede Änderung steht mit HA-Benutzer im Protokoll.
- **Datenbankzugang aus dem LAN** (Port 5432) für VSCode & Co.: `skytech_admin` (Vollzugriff) und
  `skytech_reader` (nur lesen) mit den neuen Optionen `db_password` und `db_readonly_password`;
  ohne Passwort gesperrt (D-020). Die Übersicht zeigt die Verbindungsdaten.
- **Übersicht** um die Aufzeichnung erweitert: Dienststatus, Sensoren, Werte pro Minute, letzte
  Schreibung, Stand der Minutenwerte, Größe der Datenbank.
- **Migrationen** aus `app/sql/` und optional `/data/migrations/`, mit Prüfsumme.
- CI: Integrationstests gegen TimescaleDB 2.30.1 (Minutenwerte, Verdichtungen, Rechte, Collector
  Ende-zu-Ende) und erweiterter Rauchtest.

### Geändert (M1)

- PostgreSQL lauscht jetzt auch im LAN (Anmeldung wie oben geregelt) und protokolliert ruhiger
  (keine Hinweise, keine Checkpoints).
- Die Oberfläche lädt nach einem Update immer die neue Fassung (`index.html` ohne Cache).

### Geändert

- **Abhängigkeiten aktualisiert** (ersetzt die Dependabot-PRs #1–#10): React 19, React Router 7,
  Vite 8, TypeScript 7, `@vitejs/plugin-react` 6, aiohttp 3.14.3, asyncpg 0.31.0; CI-Actions
  `checkout`, `setup-python`, `setup-node` auf v7, Node 22 im Frontend-Job (Vite 8 braucht
  mindestens 20.19). Oberfläche unverändert.

### Hinzugefügt

- **Meilenstein M0 – Gerüst.** Neues Add-on „Skytech Data Insight" (nur `amd64`): ein Container
  mit PostgreSQL 17.11 + TimescaleDB 2.30.1, Grafana 13.2.2, nginx und einem Verwaltungsdienst
  unter s6-overlay (D-004, D-005). Der Datenbank-Cluster entsteht beim ersten Start unter
  `/data/pgdata`; Datenbank `skytech` mit TimescaleDB wird bei jedem Start sichergestellt.
- **Verwaltungsoberfläche im HA-Seitenmenü** (Designsprache Home Assistant, Hell/Dunkel) mit der
  Seite „Übersicht": Zustand von Datenbank und Grafana samt Versionen, Weg zu Grafana.
- **Grafana im selben Ingress** unter „Grafana", automatisch mit dem HA-Benutzer angemeldet;
  zusätzlich im LAN unter Port 3000 mit eigenem Login `admin` (D-006). Ohne gesetztes
  `grafana_admin_password` ist die LAN-Anmeldung gesperrt (D-011). Grafana startet auf Deutsch
  mit Berliner Zeit und deutschen Datumsformaten; Telemetrie und Update-Abfragen sind aus.
- **Regelwerk und Doku** nach dem Muster von Skytech HEMS (`AGENTS.md`, `docs/`, Entscheidungs-Log
  D-001 bis D-014, ADR D-006) sowie der freigegebene Umsetzungsplan unter
  `docs/umsetzungsplan.md`.
- **CI:** Lint (Ruff, ShellCheck), Tests, Frontend-Build mit Drift-Prüfung und ein Rauchtest, der
  das Image baut, startet und Dienste, Ingress-Weg und LAN-Anmeldung prüft.
