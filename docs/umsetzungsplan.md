# Plan: Skytech Data Insight — Energie-Datenbank + Grafana Add-on

## Context

Die Skytech-Familie (HEMS, Energy Pilot, Battery Provider, Power Flow Card) hat keine eigene
Langzeit-Persistenz — HEMS liest/schreibt nur HA-State. Gebraucht wird ein weiteres HA-Add-on,
das Leistungs-, Energie- und Soll/Ist-Werte (PV, Heizung, Speicher …) dauerhaft in einer
SQL-Datenbank mit Zeit als Schlüssel ablegt, sie in Grafana darstellt, in HA-Backups enthalten
ist, sich zusätzlich unabhängig von HA sichern lässt, per VSCode direkt abfragbar ist, über eine
eigene Weboberfläche (wie HEMS) verwaltet wird und per MCP von einem LLM (Claude/GPT)
konfiguriert werden kann (Dashboards, Schema, Migrationen).


## Getroffene Entscheidungen (vom User bestätigt, 27.09.2026)

| Thema | Entscheidung |
|---|---|
| Datenbank | **TimescaleDB** (PostgreSQL + Zeitreihen-Erweiterung) — normales SQL; MS SQL scheidet aus (Lizenz, Container-Betrieb im Add-on) |
| Datenquelle | HA-Entitäten mitschreiben (Auswahl in Weboberfläche) |
| Hardware | nur **amd64** |
| Erfassung | Jede Zustandsänderung roh + automatische Raster-Aggregate (1 min / 15 min / 1 h / 1 Tag) |
| Aufbewahrung | konfigurierbar, Default: Rohdaten 1 Jahr, Aggregate unbegrenzt |
| Schema | generische Hypertable + Sensor-Stammdaten + SQL-Views je Fachbereich |
| HA-Backup | vor jedem HA-Backup automatischer `pg_dump`, Rohdatenverzeichnis ausgeschlossen |
| Externes Backup | Download/Upload (Wiederherstellen) in der Weboberfläche |
| MCP | im Add-on, **voller Zugriff** (DDL/DML, Dashboards), automatischer Dump vor jeder Änderung |
| Netzzugang | Ingress (HA-Login) für Verwaltung + Grafana; zusätzlich LAN-Ports für PostgreSQL, Grafana, MCP — einzeln abschaltbar, eigenes Passwort/Token, kein Internet-Portforward |
| Repo | eigenes GitHub-Repo unter `nicohackl/`, Regelwerk wie HEMS (AGENTS.md, docs/, CHANGELOG, `agent/main`) |
| Zielgruppe | eigene Anlagen + wenige Kunden, Einrichtung durch Skytech |
| Designsprache | Home Assistant, Akzent `#18BCF2`, `data-design="ha"`, Hell/Dunkel-Schalter |
| Altdaten-Import | manuell in der Weboberfläche auslösbar (aus HA-Recorder und Langzeitstatistik) |
| HEMS-Anbindung (später) | HEMS schreibt entweder direkt in die DB oder stellt – wie bei der Power Flow Card – einen Sensor mit den Werten als Attributen bereit; beide Wege werden vorbereitet |
| TLS für DB-Port | nicht nötig (nur LAN) |

## Produktname

**Skytech Data Insight** (festgelegt am 27.09.2026). Slug `skytech_data_insight`, Repo
`nicohackl/Skytech-Data-Insight`. Tabellen-/Rollennamen neutral (`skytech_*`).

## Architektur

Ein Add-on-Container (Basis `ghcr.io/home-assistant/amd64-base-debian:bookworm`, s6-overlay)
mit vier Diensten:

```text
 HA Core ──WebSocket state_changed──► Collector (Python/asyncio) ──COPY/Batch──► TimescaleDB
                                                                                 │ :5432 (LAN, VSCode)
 HA-Ingress ──► nginx ──/          ──► Verwaltungs-API + React-SPA (aiohttp)  ────┤
                      └─/grafana/ ──► Grafana (auth.proxy, Header nur von 127.0.0.1)
 LAN :3000  ──► nginx ──► Grafana (Login mit Grafana-Benutzer)
 LAN :8765  ──► MCP-Server (Streamable HTTP, Bearer-Token) ──► DB + Grafana-HTTP-API
```

| Komponente | Technik | Verantwortung |
|---|---|---|
| PostgreSQL 16 + TimescaleDB 2.x | Timescale-APT-Repo, Versionen im Dockerfile gepinnt | Speicherung, Aggregate, Kompression, Retention |
| Grafana (OSS) | Grafana-APT-Repo, gepinnt | Dashboards; Daten in `/data/grafana` |
| nginx | Debian-Paket | Ingress-Routing, Sub-Pfad für Grafana, Auth-Header setzen |
| `app/` (Python 3.11, aiohttp, asyncpg) | wie HEMS | Collector, Verwaltungs-API, Backup/Restore, Migrationsrunner, Supervisor-/HA-Client |
| `app/mcp_server` | offizielles Python-MCP-SDK | LLM-Werkzeuge |
| `web/` → `app/static/` | React 18 + TS strict + Vite, Design-System aus HEMS übernommen | Verwaltungsoberfläche |

Wiederverwendung aus `SkytechHEMS`: `app/ha_client.py` (WebSocket-/REST-Muster),
`app/supervisor_client.py` (Optionen, Ingress-Info), `web/`-Gerüst inkl. `styles.css`,
Icon-Set, API-Client, Hell/Dunkel-Schalter; `docs/`-Struktur, `.github/workflows/ci.yaml` +
`bump-version.yaml`, AGENTS.md-Regelwerk (angepasst).

### Add-on-Konfiguration (`config.yaml`, Auszug)

- `arch: [amd64]`, `ingress: true`, `ingress_port`, `panel_icon`, `homeassistant_api: true`, `hassio_api: true`
- `ports`: `5432/tcp`, `3000/tcp`, `8765/tcp` (jeweils per Option abschaltbar / leer = aus)
- `backup_pre: /usr/bin/skytech-backup-pre`, `backup_post: …`, `backup_exclude: ["pgdata/**"]`
- Optionen (nur Zugangs-/Infrastruktur): `db_password` (password), `db_readonly_password`,
  `grafana_admin_password`, `mcp_token`, `db_lan_enabled`, `grafana_lan_enabled`,
  `mcp_enabled`, `log_level`.
- **Fachkonfiguration** (Sensorauswahl, Aufbewahrung, Kategorien) liegt **in der DB**
  (Tabelle `skytech_config.*`) → automatisch in jedem Backup, von UI und MCP gleich bearbeitbar.

## Datenmodell (Schema `skytech`)

```sql
-- Stammdaten
sensor (
  id serial PK, entity_id text, attribut text NULL,   -- NULL = Zustand, sonst Attributname
  name text, kategorie text,   -- pv|heizung|speicher|netz|verbraucher|sonstiges
  groesse text,            -- leistung|energie|temperatur|soc|sollwert|zustand …
  rolle text,              -- ist|soll|null
  einheit text, anlage text, aktiv bool, erfassung text,   -- 'aenderung'
  energie_zaehler bool,    -- total_increasing → Delta-Berechnung
  quelle text,             -- ha|hems|extern
  erstellt_am timestamptz,
  UNIQUE (entity_id, attribut)
)
-- Messwerte (Hypertable, Chunk 7 Tage, Kompression nach 7 Tagen, segmentby sensor_id)
messwert (zeit timestamptz NOT NULL, sensor_id int NOT NULL, wert double precision,
          text_wert text, PRIMARY KEY (sensor_id, zeit))
-- Importierte Langzeitstatistik (HA liefert nur Stundenwerte → eigene Tabelle, nicht als Rohwert)
statistik_stunde (zeit timestamptz, sensor_id int, mittel, min, max, summe double precision,
                  PRIMARY KEY (sensor_id, zeit))
-- Continuous Aggregates: messwert_1min, _15min, _1h, _1d  (avg, min, max, last, count;
--   für Energiezähler zusätzlich Delta aus last-first mit Reset-Erkennung)
-- messwert_1h/_1d werden per View mit statistik_stunde ergänzt, wo keine Rohwerte vorliegen
-- Views: v_pv, v_heizung, v_speicher, v_netz, v_soll_ist (Soll/Ist-Paare über sensor.anlage)
-- Konfiguration & Protokoll
skytech_config.einstellung (schluessel, wert jsonb)       -- Aufbewahrung etc.
skytech_config.migration   (version, name, quelle, angewendet_am, checksumme)
skytech_config.aenderungsprotokoll (zeit, quelle ui|mcp|vscode, aktion, sql, backup_datei)
skytech_config.importauftrag (id, sensoren, von, bis, quelle, status, zeilen, fehler, gestartet_am)
```

Zeit intern immer `timestamptz` (UTC gespeichert); Grafana/Views zeigen `Europe/Berlin`.

Rollen: `skytech_admin` (Vollzugriff, VSCode/MCP), `skytech_reader` (nur lesen, Grafana-Datasource
und optional VSCode), `skytech_collector` (nur INSERT auf `messwert`), später `skytech_hems`
(nur INSERT auf `messwert` für Sensoren mit `quelle = 'hems'`).

## Collector

- WebSocket zu HA (`subscribe_events state_changed`), Filter auf aktive Sensoren.
- Puffer im Speicher → Batch-`COPY` alle 1–5 s; bei DB-Ausfall Puffer mit Obergrenze + Warnung.
- Nach Neustart/Verbindungsabbruch: Lücke über HA-History-API nachladen (Zeitraum seit letztem Wert).
- `unknown`/`unavailable` → `wert NULL`, `text_wert` gesetzt (Lücke sichtbar statt falscher 0).
- Neue Sensoren: Auswahl in UI/MCP, Vorschlag von Kategorie/Einheit aus `device_class`/`unit_of_measurement`.
- **Attribut-Sensoren:** Ein Eintrag in `sensor` kann statt des Zustands ein Attribut einer Entität
  erfassen (`attribut` gesetzt). Ein Sammelsensor mit vielen Werten als Attributen (Muster Power
  Flow Card, später HEMS) wird so zu mehreren Messreihen; in der UI „alle Attribute übernehmen".

## Altdaten-Import (manuell in der Weboberfläche)

- Seite **Import**: Sensoren wählen, Zeitraum wählen, Vorschau (verfügbare Datenmenge je Quelle),
  Start; Fortschritt, Abbruch und Ergebnis im `importauftrag`.
- Quellen, jeweils über die HA-WebSocket-API:
  1. **Recorder-Verlauf** (`history/history_during_period`) → Rohwerte nach `messwert`. Reicht nur so
     weit zurück, wie der HA-Recorder aufbewahrt (`purge_keep_days`, Standard 10 Tage).
  2. **Langzeitstatistik** (`recorder/statistics_during_period`, Stundenwerte) → `statistik_stunde`,
     für ältere Zeiträume.
- Doppelte Werte werden übersprungen (`ON CONFLICT DO NOTHING`), der Import ist also wiederholbar.
- Danach werden die betroffenen Continuous Aggregates für den Zeitraum neu berechnet.
- Vor dem Import automatischer Sicherheits-Dump; läuft in Portionen, der Live-Collector läuft weiter.

## HEMS-Anbindung (vorbereitet, Umsetzung später)

- **Weg A – Attribut-Sensor:** HEMS veröffentlicht einen Sensor mit seinen Werten (Sollwerte,
  Entscheidungen, Pool, Speicherleistung …) als Attributen; Data Insight erfasst ihn über
  Attribut-Sensoren. Kein Code in Data Insight nötig außer dem Attribut-Support oben.
- **Weg B – direktes Schreiben:** HEMS schreibt mit eigener Rolle `skytech_hems` in `messwert`
  (Verbindungsdaten per Add-on-Option im HEMS). Hohe Auflösung auch ohne HA-State-Änderung.
- Welcher Weg genutzt wird, entscheidet die spätere HEMS-Erweiterung; Data Insight unterstützt beide.

## Migrationen

- Eigener, schlanker Runner (Python): nummerierte SQL-Dateien, jede in Transaktion, Checksumme in
  `skytech_config.migration`.
- **System-Migrationen** im Image (`app/migrations/`), **Anlagen-Migrationen** in `/data/migrations/`
  (von UI/MCP/Hand angelegt, damit im Backup).
- Vor jeder Migration automatischer Dump → bei Fehler Rollback der Transaktion, Dump bleibt als
  Rettungsanker.

## Backup

- **HA-Backup:** `backup_pre` erzeugt `pg_dump -Fc` nach `/data/backup/ha_snapshot.dump`
  (+ Grafana-Daten liegen ohnehin in `/data/grafana`); `pgdata/` ausgeschlossen. Beim Start: ist
  `pgdata` leer und ein Dump vorhanden → automatisch `timescaledb_pre_restore()` →
  `pg_restore` → `timescaledb_post_restore()`.
- **Extern (Weboberfläche):** „Backup herunterladen" (Stream `pg_dump -Fc` + Grafana-Export als
  ein `.tar`), „Backup hochladen & wiederherstellen" (mit Bestätigungsdialog und vorherigem
  Sicherheits-Dump), Liste der lokalen Dumps (MCP-/Migrations-Dumps) mit Aufräumregel.
- Zusätzlich jederzeit möglich: `pg_dump` direkt per LAN-Port.
- Nebeneffekt: Dump/Restore ist auch der Weg für spätere PostgreSQL-Major-Upgrades.

## Verwaltungsoberfläche (Ingress)

Seiten: **Übersicht** (DB-Größe, Werte/min, letzte Werte, Dienststatus, Link Grafana) ·
**Sensoren** (HA-Entitäten suchen/auswählen, Kategorie/Rolle/Anlage) · **Aufbewahrung**
(Retention/Kompression je Stufe) · **Backups** (Download/Upload/Liste) · **Zugänge**
(Verbindungsdaten für VSCode kopierbar, Passwörter/MCP-Token rotieren, LAN-Ports) ·
**Import** (Altdaten aus HA, siehe oben) · **Migrationen** (Status, Inhalt, Fehler) · **Protokoll** (Änderungen aus UI/MCP/VSCode).
Grafana öffnet eingebettet unter `/grafana/` im selben Ingress.

## Grafana

- Provisioning: Datasource „Skytech DB" (`skytech_reader`), Startdashboards (Übersicht Energie,
  PV, Speicher, Heizung, Soll/Ist) als JSON im Image, **editierbar** (Kopie in Grafana-DB).
- Ingress: `auth.proxy` mit Header aus nginx (HA-Benutzername), nur von `127.0.0.1` akzeptiert;
  `serve_from_sub_path` mit dynamischem `root_url` aus Supervisor-Ingress-Info.
- LAN-Port: normaler Grafana-Login.
- Service-Account-Token (intern generiert) für MCP-Dashboardzugriff.

## MCP-Server (voller Zugriff)

Transport Streamable HTTP auf `:8765/mcp`, `Authorization: Bearer <mcp_token>`. Einbindung in
Claude Desktop/Code bzw. GPT-Clients per URL + Token (Anleitung in `docs/mcp.md`).

Werkzeuge:
- Lesen: `schema_anzeigen`, `sql_abfrage` (SELECT, Zeilenlimit), `sensoren_auflisten`, `statistik`
- Schreiben: `sql_ausfuehren` (DDL/DML), `migration_anlegen_und_anwenden`, `sensor_erfassen`,
  `aufbewahrung_setzen`
- Grafana: `dashboards_auflisten`, `dashboard_lesen`, `dashboard_speichern`, `datasources_auflisten`
- Sicherung: `backup_erstellen`, `backups_auflisten`

Schutz trotz Vollzugriff: automatischer Dump vor jedem schreibenden Aufruf, jeder Aufruf im
`aenderungsprotokoll`, Statement-Timeout, MCP standardmäßig **aus** bis Token gesetzt.

> **Sicherheitshinweis:** Vollzugriff heißt, ein LLM kann Daten und Dashboards löschen oder
> verfälschen. Wiederherstellung ist nur über die automatischen Dumps möglich; deren Aufbewahrung
> muss groß genug gewählt werden. MCP-Port und DB-Port nie ins Internet freigeben.

## Repo-Struktur (neues Repo, analog HEMS)

```text
AGENTS.md  CLAUDE.md  GEMINI.md  CHANGELOG.md  README.md  config.yaml  Dockerfile  build.yaml
rootfs/etc/s6-overlay/s6-rc.d/{postgres,grafana,nginx,app}/   rootfs/etc/nginx/  rootfs/usr/bin/
app/ (main.py, collector/, db/, migrations/, backup/, mcp_server/, ha_client.py, supervisor_client.py, static/)
grafana/provisioning/{datasources,dashboards}/
web/ (React/Vite)   tests/   translations/{de,en}.yaml
docs/ (architektur, datenmodell, konfiguration, backup-restore, mcp, vscode-zugriff,
       sicherheit-datenschutz, design-entscheidungen, adr/, roadmap, bekannte-luecken, …)
```

## Meilensteine

1. **M0 Gerüst & Spike** — Repo, AGENTS.md, CI; Container mit Postgres+Timescale, Grafana, nginx
   unter s6 startet; Grafana-Sub-Pfad über Ingress nachgewiesen (größtes technisches Risiko).
2. **M1 Datenbank & Collector** — Schema, System-Migrationen, Rollen, Collector mit Batch/Pufferung/
   Lückennachladen, Continuous Aggregates, Retention/Kompression.
3. **M2 Backup** — `backup_pre`/Auto-Restore, Download/Upload, Sicherheits-Dumps.
4. **M3 Verwaltungsoberfläche** — alle Seiten, Sensorauswahl, Zugänge.
5. **M3b Altdaten-Import** — Import-Seite, Recorder- und Statistik-Import, Neuberechnung Aggregate.
6. **M4 Grafana** — Provisioning, Startdashboards, Auth-Proxy, LAN-Login.
7. **M5 MCP** — Server, Werkzeuge, Protokoll, Doku für Claude/GPT.
8. **M6 Härtung & Release** — Tests, Last (Jahresdaten), Restore-Probe, Release.
9. **M7 HEMS-Anbindung** (später) — im HEMS-Repo Weg A oder B umsetzen, Rolle `skytech_hems` aktivieren.

## Verifikation

- `pytest` (Collector-Batching, Migrationsrunner, Energiezähler-Delta mit Reset, Backup-Roundtrip
  gegen Testcontainer mit TimescaleDB), `ruff`, `npm run build`.
- Test-HA (amd64-VM): Add-on installieren, 5 Sensoren auswählen → Werte in `messwert` und
  Aggregaten; HA neu starten → Lücke nachgeladen.
- VSCode (Extension „PostgreSQL" von Microsoft oder SQLTools) über LAN-Port verbinden, SELECT auf `v_pv`.
- HA-Backup erstellen → Add-on deinstallieren → Backup wiederherstellen → Daten + Dashboards vollständig.
- Import: Zeitraum der letzten 30 Tage für 3 Sensoren importieren → Recorder-Anteil in `messwert`,
  älterer Anteil in `statistik_stunde`; zweiter Import erzeugt keine Duplikate.
- Attribut-Sensor: Testsensor mit 3 Attributen → 3 Messreihen.
- Download-Backup in frischem Add-on hochladen → identische Zeilenzahlen.
- Claude Code mit MCP-URL verbinden: Dashboard anlegen lassen, Spalte per Migration ergänzen,
  Protokolleintrag + Sicherheits-Dump prüfen.

## Offene Punkte

- Keine vor M0. Nächster Schritt: Repo-Gerüst `nicohackl/Skytech-Data-Insight` (M0).
