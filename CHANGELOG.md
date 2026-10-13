# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Add-on-Version in `config.yaml` wird bei jedem Merge nach `main` automatisch
um eine Patch-Stelle erhöht (siehe `.github/workflows/bump-version.yaml`).

## [Unreleased]

### Geändert — 13.10.2026 (Vertrag mit SkytechHEMS 0.3, Migration 0004)

- Reihen mit Quelle `hems` werden nicht mehr fortgeführt: ein Rohwert gilt nur für seine Minute.
  Unter 0.2 lief ein einziger Grundlast-Wert als Konstante weiter. Die Migration entfernt die
  bisher fortgeführten Minuten dieser Reihen; die Verdichtungen ziehen über ihre Policy nach.
- Neue Sicht `v_hems_rolle_1min` (Minutenwerte je HEMS-Rolle) für die Grundlast je Minute.
- `hems_sensor_sichern` setzt zusätzlich das Zählerkennzeichen (`energie_zaehler`), damit Zähler
  wie Netzbezug oder PV-Ertrag ihren Zuwachs je Minute bekommen.
- Vertragsversion 0.3; SkytechHEMS im selben Arbeitspaket nachgezogen. Beide Add-ons zusammen
  aktualisieren.

### Hinzugefügt — 13.10.2026 (Dashboard „Skytech Dynamischer Strompreis“)

- Neues Grafana-Dashboard für den dynamischen Strompreis (SkytechHEMS-Phase P6), über den
  MCP-Server gespeichert:
  - Preiskurve mit Markierung „jetzt“ und Ende des Preishorizonts
  - PV- und Grundlast-Prognose (aktuell und Vortag mit p10–p90-Band) gegen Ist
  - PV je Tag: Helios-Vortagsprognose gegen Ist
  - Ladezustand, nutzbare Energie und Reichweite der Speicher
  - Netzlade-Schalter und -Zulässigkeit als Statusverlauf
  - Prognosegüte mit den Abnahmekriterien
  - Rückblick „Was hätte ideales Netzladen gestern gespart?“ (Netzbezug-Sensor wählbar)
- Dashboards liegen versioniert unter `grafana/dashboards/`; `tests/test_dashboards.py` führt jede
  Abfrage gegen ein frisch migriertes Schema mit der Leserolle aus.
- Bekannte Lücke L-017: `v_prognose_vs_ist` und `v_prognose_guete_tag` reichen Zeitfilter nicht
  durch; das Dashboard filtert deshalb jede Seite selbst. L-015 weitgehend bestätigt (Anbindung
  läuft auf der Referenzanlage).

### Dokumentation — 13.10.2026 (Vertrag vollständig umgesetzt)

- Vertrag `contract_hems_data_insight` 0.2: SkytechHEMS belegt seit Phase P5 alle Rollen, Reihen und
  Laufarten (Verbrauchsprognose, Auswertung, Schalter). Status und Implementierungsstellen
  nachgezogen; wortgleich mit SkytechHEMS.

### Dokumentation — 13.10.2026 (HEMS-Seite des Vertrags)

- Vertrag `contract_hems_data_insight` 0.2: Die SkytechHEMS-Seite ist umgesetzt (HEMS-Phase P4).
  Status je Abschnitt, Implementierungsstellen, Vertragsübersicht, Roadmap M7, D-027 und L-015
  nachgezogen. Wortgleich mit SkytechHEMS.

### Hinzugefügt — 12.10.2026 (Anbindung von Skytech HEMS, D-027)

- **Skytech HEMS kann Daten schreiben.** Neuer Datenbankbenutzer `skytech_hems`, nur aus dem
  internen Add-on-Netz erreichbar. Das Passwort erzeugt die Seite „Zugänge“ (neue Karte „Skytech HEMS –
  Datenbank (intern)“, Option `hems_password`); im HEMS wird es als `insight_password` eingetragen.
- **Vom HEMS verwaltete Sensoren.** Das HEMS legt die Sensoren, die es braucht, selbst an oder
  übernimmt vorhandene. Sie stehen auf der Seite „Sensoren“ in einem eigenen Abschnitt „Über Vertrag
  verwaltet — Skytech HEMS“ und lassen sich hier weder ändern noch löschen – auch nicht per MCP
  oder SQL. Das HEMS kann sie austauschen, ohne dass der Verlauf abreißt.
- **Prognosen und Preise.** Neue Tabellen und Sichten für Preis-, PV- und Verbrauchsprognosen des
  HEMS samt Vergleich mit dem Ist und Prognosegüte je Tag (`v_preis`, `v_prognose_vs_ist`,
  `v_prognose_guete_tag` …). PV-, Verbrauchs- und Auswertungsläufe werden nach 365 Tagen gelöscht,
  Preise bleiben.
- **Eigene Reihen des HEMS** (z. B. Grundlast) erscheinen wie andere Sensoren; ihre Minutenwerte
  werden nachgerechnet, sobald das HEMS Werte schreibt.
- Protokoll: neue Quelle „Skytech HEMS“.

### Dokumentation — 12.10.2026 (Vertrag 0.2)

- Vertrag `contract_hems_data_insight` auf Version 0.2: Das HEMS schreibt nur über geprüfte
  Datenbankfunktionen; zugelassenes Netz `172.30.33.0/24`. Data-Insight-Seite implementiert,
  HEMS-Seite offen. Wortgleich mit SkytechHEMS.

### Dokumentation — 12.10.2026 (Vertrag mit SkytechHEMS)

- **Vertrag `contract_hems_data_insight` 0.1 (Entwurf)** wortgleich mit SkytechHEMS und neue
  Grundsatzentscheidung D-027 (Status Geplant): eigene Rolle `skytech_hems`, vom HEMS verwaltete und
  hier gesperrte Sensoren, Rollen-Zuordnung, Prognose- und Preistabellen. Noch nicht
  implementiert. `AGENTS.md` (Regel 12), `contract/README.md`, `datenmodell.md`, `roadmap.md` und
  `umsetzungsplan.md` verweisen darauf.

### Dokumentation — 12.10.2026 (dynamischer Strompreis)

- HEMS-Anbindung (M7) festgelegt: Weg B mit eigener Rolle `skytech_hems` für den dynamischen
  Strompreis (SkytechHEMS D-065). Vom HEMS verwaltete Sensoren werden hier gekennzeichnet und
  gesperrt; Prognose- und Preistabellen kommen dazu. Vertrag und Umsetzung folgen. Kein Code
  geändert.

### Dokumentation — 07.10.2026

- Grafana in einer HA-Karte „Webseite“ einbinden: relativer Ingress-Pfad statt `http://<ip>:3000`
  (D-026). Das vermeidet die Meldung „Iframes, die auf Websites mit http: zeigen, können nicht
  geladen werden“ bei https-HA, auch über Reverse Proxy. Eine zuvor erwogene TLS-Option für
  Port 3000 wurde wieder entfernt (nicht in einer veröffentlichten Version).

### Dokumentation — 06.10.2026

- Gemeinsame Contract-Ablage mit einem Ordner je Projektpaar und aktualisierten Verweisen.
- Ablagekonvention vorbereitet; kein neuer bilateraler Laufzeitvertrag eingeführt.


### Hinzugefügt (Meilenstein M3, Version 0.5.0)

- **Seite „Speicher"** (M3): Größe der Datenbank und jeder Tabelle, Stand der Kompression,
  Rohwerte je Tag mit Hochrechnung pro Jahr, Aufbewahrung von Roh- und Minutenwerten änderbar.
  Vor einer Änderung legt das Add-on automatisch eine Sicherung an (`vor_aenderung_*`).
- **Seite „Protokoll"** (M3): alle Änderungen aus Oberfläche, MCP und System mit Benutzer und
  Details, Filter nach Quelle, ältere Einträge seitenweise.
- **Seite „Migrationen"** (M3): Stand aller System- und Anlagen-Migrationen mit SQL-Inhalt;
  eine nach dem Anwenden veränderte Datei wird rot markiert.
- **Seite „Zugänge"** (M3, D-025): Verbindungsdaten für VSCode, Grafana im LAN und MCP mit
  Adresse des HA-Hosts und freigegebenem Port. Passwörter und MCP-Token lassen sich neu erzeugen
  oder sperren – sofort wirksam, ohne Neustart des Add-ons; das neue Secret wird genau einmal
  angezeigt. Dafür braucht das Add-on die Supervisor-Rolle `manager`.

### Geändert (Version 0.5.0)

- Der MCP-Server liest `mcp_token` beim Start über die Supervisor-API, damit ein neu erzeugtes
  Token ohne Neustart des Add-ons gilt.
- Das MCP-Werkzeug `aufbewahrung_setzen` prüft Minutenwerte jetzt vorab auf mindestens 31 Tage
  (gemeinsame Logik mit der Seite „Speicher").

### Hinzugefügt (Version 0.4.3)

- **Größe „Preis"** (`preis`) für Tarif- und Börsenpreise wie €/kWh (System-Migration 0002).
  Neue Sensoren mit der Einheit €/kWh, ct/kWh oder €/MWh bekommen sie als Vorschlag.

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

- **Ursache der stehenden Minutenwerte behoben (0.4.2).** Schreib- und Minutenschleife schrieben
  den Puffer gleichzeitig; danach wurde abgezählt entfernt. Das führte zu „pop from an empty
  deque" und konnte Rohwerte, die während des Schreibens eingingen, ungeschrieben verwerfen. Der
  Puffer wird jetzt gesperrt und beim Schreiben ausgetauscht – kein Wert geht mehr verloren, auch
  nicht, wenn das Schreiben scheitert.
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
