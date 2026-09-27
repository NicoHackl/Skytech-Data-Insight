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
