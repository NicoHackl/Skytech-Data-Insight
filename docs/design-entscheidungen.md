# Design-Entscheidungen

**Quelle der Wahrheit fürs „warum".** Wer wissen will, weshalb etwas so gebaut ist, schaut hier —
und ändert es nicht, ohne die Entscheidung hier zu widerrufen.

## Wann ein Eintrag entsteht

Immer, wenn eine Festlegung getroffen wird, die später jemand hinterfragen könnte:
Technologiewahl, Datenformat, Namensschema, Zuständigkeitsgrenze, bewusst nicht Gebautes,
neue Laufzeit-Abhängigkeit.

**Nicht** eingetragen werden reine Umsetzungsdetails, die der Code selbst zeigt.

## Ablauf

1. Nächste freie `D-xxx` vergeben (fortlaufend, nie wiederverwenden).
2. Zeile in die Tabelle unten eintragen.
3. Bei tragweiter Entscheidung zusätzlich ein ADR anlegen:
   `docs/adr/D-xxx-kurzname.md` auf Basis von [adr/0000-vorlage.md](adr/0000-vorlage.md), und aus
   der Tabelle darauf verlinken.
4. Wird eine Entscheidung später gekippt: alte Zeile auf Status **Ersetzt** setzen und auf die neue
   `D-yyy` verweisen. **Zeilen werden nie gelöscht** — sonst geht die Begründung verloren, warum
   der frühere Weg verworfen wurde.

## Status-Werte

| Status | Bedeutung |
|---|---|
| Aktiv | Gilt und ist umgesetzt |
| Geplant | Beschlossen, aber noch nicht im Code — siehe [roadmap.md](roadmap.md) |
| Ersetzt | Durch eine spätere Entscheidung abgelöst, Verweis in der Begründung |
| Verworfen | Bewusst nicht umgesetzt, Begründung bleibt als Warnung stehen |

## Log

Die Nummern **D-001 bis D-003** stammen aus der Projektvorlage und gelten für jedes Projekt der
Skytech-Familie.

| ID | Datum | Entscheidung | Status | Begründung / Verweis |
|---|---|---|---|---|
| D-001 | 13.08.2026 | Regeln für KI-Agenten liegen in `AGENTS.md`; `CLAUDE.md`, `GEMINI.md`, `copilot-instructions.md` und `.cursor/rules/` sind reine Verweise darauf | Aktiv | Jede Regel existiert genau einmal. Alternative „je Tool eine eigene Datei" wurde verworfen, weil die Kopien erfahrungsgemäß auseinanderlaufen. |
| D-002 | 13.08.2026 | Datum immer `TT.MM.JJJJ`, Uhrzeit immer Berliner Zeit als `hh:mm` bzw. `hh:mm:ss`, ohne Offset oder Zonenkürzel (eiserne Regel 9 in [`AGENTS.md`](../AGENTS.md)) | Aktiv | Einheitliche Lesart in Doku, Changelog, Logs und UI. Alternative „ISO 8601 mit Offset überall" wurde verworfen: technisch korrekt, für die deutschsprachige Zielgruppe aber unlesbar. Maschinenformate bleiben davon ausgenommen. |
| D-003 | 13.08.2026 | Designsprachen über `data-design` (`ha` = Home Assistant mit `#18BCF2`, `fcr` = FC Ruderting), ohne Default und mit grauem Akzent als sichtbarem „nicht entschieden"; Hell/Dunkel über `data-theme` in jeder Sprache Pflicht (eiserne Regeln 10 und 11 in [`../AGENTS.md`](../AGENTS.md)) | Aktiv | Ein Vokabular, mehrere Akzentsätze. Alternative „je Designsprache eine eigene styles.css" wurde verworfen, weil dann jede Klassenänderung doppelt gepflegt werden müsste. Ein stiller Default wurde ebenfalls verworfen: er hätte fremde Projekte in den Farben eines anderen erscheinen lassen, statt die offene Entscheidung zu zeigen. |
| D-004 | 27.09.2026 | Datenbank ist **PostgreSQL 17 mit TimescaleDB** (Hypertables, Continuous Aggregates, Kompression, Retention) | Aktiv | Vom User gewählt. Normales SQL für VSCode, Grafana und LLMs, Zeit als Schlüssel nativ. MS SQL scheidet aus (Lizenz, kein sinnvoller Betrieb im Add-on-Container), MariaDB hat keine Zeitreihen-Funktionen. Der Plan nannte PostgreSQL 16; gewählt wurde 17, weil TimescaleDB 2.30 beide unterstützt und 17 die längere Pflegezeit hat. Versionen sind im `Dockerfile` gepinnt; das TimescaleDB-Paket ist je PostgreSQL-Minor gebaut und wird mit ihm zusammen angehoben. |
| D-005 | 27.09.2026 | **Ein** Container mit s6-overlay (Basis-Image `amd64-base-debian`) betreibt Postgres, Grafana, nginx und den Verwaltungsdienst; ein Dienst, der unerwartet endet, stoppt das ganze Add-on | Aktiv | Ein Add-on = eine Installation, ein Backup, eine Version. Getrennte Add-ons wurden verworfen: Reihenfolge, Zugangsdaten und Backups müssten über Add-on-Grenzen koordiniert werden. Halt statt Einzelneustart, weil ein halb laufendes Add-on für HA gesund aussähe; der Watchdog startet es neu. |
| D-006 | 27.09.2026 | Grafana läuft mit `serve_from_sub_path` unter `<ingress_entry>/grafana/`; nginx trennt Ingress (Port 8099, nur Supervisor, Anmeldung per `auth.proxy` mit dem HA-Benutzer) und LAN (Port 3000, Grafana-Login, Anmeldeheader wird entfernt) | Aktiv | Ausführlich: [adr/D-006-grafana-unter-ingress.md](adr/D-006-grafana-unter-ingress.md). |
| D-007 | 27.09.2026 | Das gebaute SPA-Bundle liegt eingecheckt unter `app/static/`; die CI baut neu und bricht bei Abweichung ab | Aktiv | Übernommen aus Skytech HEMS (dort D-035): Der Add-on-Build auf dem HA-Host hat kein Node.js, und ein zusätzlicher Build-Schritt im Image verlängerte jede Installation. |
| D-008 | 27.09.2026 | Unter HA-Ingress: `base: './'`, API-Pfade ohne führenden Slash, `HashRouter` | Aktiv | Übernommen aus Skytech HEMS (dort D-036): Der Ingress-Pfad entsteht erst zur Laufzeit. Details in [frontend.md](frontend.md). |
| D-009 | 27.09.2026 | LAN-Zugänge werden über den Abschnitt „Netzwerk" der Add-on-Seite freigegeben oder abgeschaltet – keine eigenen Optionen `*_lan_enabled` | Aktiv | Abweichung vom Plan, der eigene Schalter vorsah. Home Assistant bietet genau diese Funktion bereits (Port umlegen oder leeren = aus); eigene Schalter wären eine zweite Quelle für dieselbe Entscheidung. Ist ein Port abgeschaltet, erreicht ihn aus dem LAN niemand, auch wenn der Dienst im Container lauscht. |
| D-010 | 27.09.2026 | `styles.css`, `Icon.tsx` und `Theme.tsx` werden unverändert aus Skytech HEMS übernommen, inklusive des HEMS-Blocks | Aktiv | Eine Designsprache für die ganze Produktfamilie. Klassen des HEMS-Blocks, die hier ungenutzt sind, bleiben stehen, damit sich die Datei zwischen den Projekten vergleichen und abgleichen lässt; neue Klassen kommen als eigener Block „Data Insight" dazu. |
| D-011 | 27.09.2026 | Ohne `grafana_admin_password` bekommt der Grafana-Benutzer `admin` bei jedem Start ein Zufallspasswort | Aktiv | Grafana käme sonst mit `admin/admin` und wäre im LAN offen. Über Ingress wird ohnehin per Proxy angemeldet, das Passwort braucht nur, wer Grafana im LAN nutzt. |
| D-012 | 27.09.2026 | Im Container verbindet sich der Verwaltungsdienst nur über den Unix-Socket mit `peer`-Anmeldung (Zuordnung in `pg_ident.conf`); Postgres lauscht in M0 nur auf `localhost` | Aktiv | Kein Passwort im Container nötig. Der LAN-Zugang für VSCode kommt mit M1 zusammen mit den Rollen `skytech_admin`/`skytech_reader`. |
| D-013 | 27.09.2026 | Init-Skripte lesen Optionen aus `/data/options.json` (per `jq`) statt über `bashio::config`; ohne Supervisor gilt ein lokaler Testmodus | Aktiv | Damit lässt sich der komplette Container ohne Home Assistant starten und in der CI rauchtesten. Der Supervisor schreibt die Datei vor jedem Start, sie ist dieselbe Quelle. |
| D-014 | 27.09.2026 | Nur Architektur `amd64` | Aktiv | Vom User festgelegt. TimescaleDB- und Grafana-Pakete gäbe es auch für `aarch64`; eine Erweiterung bräuchte nur `build.yaml` und `config.yaml`. |
| D-015 | 27.09.2026 | Minutenwerte werden **zeitgewichtet** („letzter Wert gilt fort") per SQL aus den Rohwerten berechnet (`app/minute_values.py`) und in der Tabelle `messwert_1min` gespeichert; 15 min/1 h/1 d sind Continuous Aggregates darauf, gewichtet nach Abdeckung | Aktiv | HA meldet nur Änderungen – ein Mittel über Rohwerte wäre verzerrt (viele Meldungen in kurzer Zeit zählten mehrfach). Continuous Aggregates können keine Fensterfunktionen, und das Timescale-Toolkit (`time_weight`) kennt den Wert vor Bucket-Beginn nicht; es hätte außerdem ein weiteres Paket gebracht. „Stützwerte" je Minute in den Rohdaten wurden verworfen, weil sie die Rohwerte verfälschen. Die SQL-Berechnung ist wiederholbar (Upsert) und damit auch für Nachladen und Import (M3b) nutzbar; Zählerzuwachs mit Neustart-Erkennung wie in HA. |
| D-016 | 27.09.2026 | Soll/Ist-Paare werden über `sensor.soll_ist_paar` (Paarname) gebildet, nicht über `anlage` + `groesse` wie im Plan skizziert | Aktiv | Eine Anlage kann mehrere Ist-Leistungen haben (z. B. mehrere PV-Strings); die Zuordnung über Anlage und Größe wäre dann mehrdeutig. Ein expliziter Paarname mit Eindeutigkeit je Rolle macht `v_soll_ist` eindeutig. |
| D-017 | 27.09.2026 | `on`/`off` (und `true`/`false`) werden als `wert` 1/0 **und** als `text_wert` gespeichert | Aktiv | Vom User gewählt. Schaltzustände werden in Grafana als Kurve nutzbar, das Minutenmittel ist der Einschaltanteil. Andere Texte stehen nur in `text_wert`. |
| D-018 | 27.09.2026 | Kategorien und Größen sind Katalogtabellen (`skytech.kategorie`, `skytech.groesse`) mit Fremdschlüssel statt CHECK-Listen | Aktiv | Neue Kategorien (z. B. Wallbox) per `INSERT` statt Migration; Oberfläche und LLM lesen dieselbe Liste. |
| D-019 | 27.09.2026 | Die Sensorverwaltung (Liste, Mehrfachauswahl, Attribute, Soll/Ist, Anlage) wird aus M3 vollständig in M1 vorgezogen | Aktiv | Vom User entschieden: ohne Oberfläche wäre die Aufzeichnung nur per SQL bedienbar. Die übrigen M3-Seiten (Aufbewahrung, Backups, Zugänge, Migrationen, Protokoll) bleiben in M3. |
| D-020 | 27.09.2026 | Getrennte Datenbankrollen: `skytech_app` (Besitzer), `skytech_collector` (nur Messwerte schreiben), `skytech_admin` (LAN, Mitglied von `skytech_app`), `skytech_reader` (LAN, nur lesen); LAN-Zugang nur zur Datenbank `skytech` und nur mit Passwort | Aktiv | Geringste Rechte je Aufgabe. `skytech_admin` ist bewusst kein Superuser: Schema ändern ja, Cluster und Erweiterungen nicht. Passwörter kommen aus den Add-on-Optionen und werden bei jedem Start gesetzt; leer sperrt die Anmeldung. |
| D-021 | 27.09.2026 | Der MCP-Server (M5) wird vor M2 umgesetzt; als eigener s6-Dienst auf Port 8765 mit Streamable HTTP (zustandslos, JSON), Bearer-Token aus der Option `mcp_token` und Datenbankrolle `skytech_admin` | Aktiv | Vom User entschieden, um Dashboards per LLM zu bauen. Eigener Prozess statt Teil des Verwaltungsdienstes: ein Fehler oder eine lange Abfrage im MCP-Pfad bremst die Aufzeichnung nicht. Token statt OAuth: für einen LAN-Dienst mit wenigen Nutzern angemessen, jeder MCP-Client kann Header setzen. Die für „voller Zugriff mit Sicherung" nötige `pg_dump`-Sicherung ist der erste Baustein von M2. |
| D-022 | 27.09.2026 | Die Grafana-Datenquelle „Skytech DB" (`uid: skytech-db`) wird vom Add-on bereitgestellt (Provisioning, nicht änderbar) und nutzt die interne Rolle `skytech_grafana` mit erzeugtem Passwort | Aktiv | Aus M4 vorgezogen, weil Dashboards ohne Datenquelle nichts zeigen. Eine interne Rolle statt `skytech_reader`: Grafana funktioniert auch ohne vom Benutzer gesetztes Passwort, und ein geändertes LAN-Passwort bricht keine Dashboards. Das Passwort liegt in `/data/secrets` (im Backup) und gelangt per `$__file{…}` in Grafana. |
| D-023 | 27.09.2026 | HA-Backups enthalten einen `pg_dump` (Hook `backup_pre`) und eine SQLite-Online-Kopie von Grafana statt des Datenbankverzeichnisses; `/data/pgdata` und die lokalen Sicherungen sind per `backup_exclude` ausgeschlossen. Nach einer HA-Wiederherstellung (Dump vorhanden, Cluster fehlt) spielt das Add-on den Dump beim Start selbst ein | Aktiv | Wie im Plan. Das Kopieren der Dateien einer laufenden PostgreSQL ist nicht konsistent; ein „kaltes" Backup (Add-on stoppt) hätte die Aufzeichnung unterbrochen. Der Dump ist zudem versionsunabhängiger und kleiner. Die Wiederherstellungserkennung braucht keinen Eingriff des Benutzers. |
| D-024 | 27.09.2026 | Einspielen über die Oberfläche als Hintergrundauftrag: Sicherung vorher, Aufzeichnung anhalten, Datenbank per `restore-db.sh` ersetzen, danach Verwaltungsdienst und MCP-Server über s6 neu starten; Download als `.tar` mit Dump, Grafana-Datenbank und Beschreibung | Aktiv | Ein Neustart der beiden Dienste ist der einfachste sichere Weg, alle Verbindungen, Pools und Zwischenstände auf die neue Datenbank zu bringen; das ganze Add-on neu zu starten bräuchte die Supervisor-Rolle `manager`. Ein Paket statt zweier Downloads, damit Daten und Dashboards zusammenbleiben. |
