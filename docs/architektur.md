# Architektur

> Beschreibt den **tatsächlichen** Stand (Meilenstein M1). Das Zielbild steht im
> [Umsetzungsplan](umsetzungsplan.md).

## Zweck und Abgrenzung

Home-Assistant-Add-on zur Langzeitablage und Auswertung von Energiedaten mit TimescaleDB und
Grafana. Stand M1: Aufzeichnung ausgewählter HA-Entitäten und -Attribute, Minutenwerte und
Verdichtungen, Sensorverwaltung in der Oberfläche, Datenbankzugang aus dem LAN. **Noch nicht**
vorhanden: Backup-Funktionen, Altdaten-Import, Grafana-Datasource und -Dashboards, MCP (siehe
[roadmap.md](roadmap.md)).

## Tech-Stack

| Schicht | Technologie | Warum |
|---|---|---|
| Datenbank | PostgreSQL 17.11 + TimescaleDB 2.30.1 | D-004 |
| Dashboards | Grafana 13.2.2 (OSS) | Plan, D-006 |
| Eingang | nginx (Debian-Paket) | trennt Ingress und LAN, D-006 |
| Verwaltungsdienst und Collector | Python 3.11, aiohttp, asyncpg | wie Skytech HEMS; ein Prozess für API und Aufzeichnung |
| Oberfläche | React 19 + TypeScript (`strict`) + Vite | eiserne Regel 8, [frontend.md](frontend.md) |
| Prozessaufsicht | s6-overlay v3 aus `ghcr.io/home-assistant/amd64-base-debian:bookworm` | D-005 |

Versionen sind im [`Dockerfile`](../Dockerfile) gepinnt.

## Dienste und Ports

```text
  HA Core ──WebSocket (über Supervisor)──► app: Collector ──socket──► postgres
  HA-Supervisor ──Ingress──► nginx :8099 ──/──────────► app: API + SPA (127.0.0.1:8100)
  (172.30.32.2)                          └─/grafana/──► grafana 127.0.0.1:3001 ◄──┐
  LAN ─────────────────────► nginx :3000 ──<ingress_entry>/grafana/ ───────────────┘
  LAN (VSCode) ────────────► postgres :5432 (skytech_admin / skytech_reader, Passwort)
  LAN (LLM) ───────────────► mcp :8765/mcp (Bearer-Token) ──socket──► postgres, ──auth-proxy──► grafana
```

| Dienst (s6) | Typ | Hängt ab von | Verantwortung |
|---|---|---|---|
| `init-env` | oneshot | `base` | Protokollstufe und `ingress_entry` ermitteln, als Umgebung für alle Dienste ablegen |
| `init-postgres` | oneshot | `init-env` | Cluster unter `/data/pgdata` anlegen (erster Start), Laufzeitkonfiguration schreiben, Hauptversion prüfen, Grundobjekte sicherstellen (`bootstrap.sql`, Extension anlegen und aktualisieren) |
| `postgres` | longrun | `init-postgres` | Datenbank; Stopp per `SIGINT` (fast shutdown) |
| `init-grafana` | oneshot | `init-env` | `grafana.ini` schreiben, Admin-Passwort setzen (D-011) |
| `grafana` | longrun | `init-grafana` | Dashboards |
| `app` | longrun | `init-env`, `postgres` | Verwaltungsdienst: Oberfläche und API, [api-referenz.md](api-referenz.md) |
| `init-nginx` | oneshot | `init-env` | `nginx.conf` schreiben, Ingress-Port auf den Supervisor beschränken |
| `nginx` | longrun | `init-nginx`, `app`, `grafana` | Eingang für Ingress und LAN |
| `mcp` | longrun | `init-env`, `postgres` | MCP-Server (`app/mcp_server.py`), nur mit `mcp_token`, sonst Leerlauf; [mcp.md](mcp.md) |

## Verwaltungsdienst (`app/`)

| Modul | Verantwortung | Darf nicht |
|---|---|---|
| `main.py` | Startablauf (Pools, Migrationen, Aufbewahrung, Collector, HA-Verbindung), HTTP-Routen | Fachlogik enthalten |
| `database.py` | Verbindungsparameter und Pools je Rolle | – |
| `migration_runner.py` | Migrationen finden, prüfen, anwenden | Schemainhalte kennen |
| `ha_client.py` | einzige Stelle mit HA-Zugriff: WebSocket, Anmeldung, Zustandsabbild, Abo `state_changed`, Verlauf, Neuverbindung | in die Datenbank schreiben |
| `collector.py` | Werte umsetzen, nur Änderungen puffern, gebündelt schreiben, Minutenlauf, Lücken nachladen, Sensorliste per `LISTEN` aktuell halten | HTTP sprechen |
| `minute_values.py` | Minutenwerte per SQL berechnen (D-015) | Zustand halten |
| `values.py`, `suggestions.py` | Umsetzung HA-Wert → Zahl/Text; Vorschläge für neue Sensoren | auf HA oder die Datenbank zugreifen |
| `sensor_service.py` | Sensorliste prüfen, ändern, protokollieren | den Collector direkt ansprechen (das macht der Trigger) |
| `health.py`, `display_time.py` | Dienstprüfungen, Anzeigezeit | – |
| `mcp_server.py`, `mcp_tools.py` | eigener Prozess: MCP-Protokoll und Token-Prüfung bzw. Fachlogik der Werkzeuge | – |
| `backup.py`, `grafana_client.py` | `pg_dump`-Sicherungen unter `/data/backup`; Grafana-HTTP-API über den Auth-Proxy | – |

### Ablauf der Aufzeichnung

1. Beim Start: Migrationen, `aufbewahrung_anwenden()`, Sensorliste und letzter Wert je Sensor laden.
2. Nach jeder (Neu-)Verbindung zu HA: Zustandsabbild holen, `state_changed` abonnieren, die Lücke
   seit dem letzten gespeicherten Wert aus dem HA-Verlauf nachladen (höchstens 10 Tage), dann den
   aktuellen Zustand übernehmen.
3. Je Zustandswechsel: Wert je betroffenem Sensor umsetzen, nur bei Änderung puffern.
4. Alle 2 s: Puffer gebündelt schreiben. Datenbank weg → Puffer bleibt (höchstens 100 000 Werte).
5. Jede Minute (5 s nach Minutenwechsel): Minutenwerte der abgeschlossenen Minuten berechnen;
   verspätete oder nachgeladene Werte lösen eine Neuberechnung der betroffenen Sensoren aus.
6. Änderungen an `skytech.sensor` (Oberfläche oder SQL) kommen per `NOTIFY`; neue Sensoren
   beginnen sofort mit dem aktuellen Zustand.
7. Beim Stopp (SIGTERM): Puffer schreiben, dann beenden.

Ohne `SUPERVISOR_TOKEN` verbindet sich der Collector nur, wenn `SKYTECH_HA_URL` und
`SKYTECH_HA_TOKEN` gesetzt sind (lokaler Test).

## Dienstende

Endet ein Dienst unerwartet, stoppt [`finish.sh`](../rootfs/usr/lib/skytech/finish.sh) das ganze
Add-on; der Watchdog (`tcp://…:8099`) startet es neu (D-005).

Konfigurationsdateien entstehen bei **jedem** Start aus den Vorlagen in
[`rootfs/usr/share/skytech/templates/`](../rootfs/usr/share/skytech/templates/) unter
`/run/skytech/`. Platzhalter `__NAME__` ersetzt `skytech::render` aus
[`lib.sh`](../rootfs/usr/lib/skytech/lib.sh); ein Test prüft, dass jeder Platzhalter gesetzt wird.

## Verzeichnisse im Container

| Pfad | Inhalt | Im HA-Backup |
|---|---|---|
| `/data/pgdata` | PostgreSQL-Cluster | ja (M2 ersetzt das durch einen Dump, siehe Plan) |
| `/data/migrations` | Anlagen-Migrationen (optional) | ja |
| `/data/backup` | Sicherungen (`pg_dump`) | ja |
| `/data/secrets` | intern erzeugte Zugangsdaten (Grafana-Datenquelle) | ja |
| `/data/grafana` | Grafana-Datenbank (SQLite), Plugins, Protokolle | ja |
| `/data/options.json` | Add-on-Optionen, vom Supervisor geschrieben, nur gelesen | ja |
| `/run/skytech/` | erzeugte Konfiguration (postgres, grafana, nginx) | nein, flüchtig |
| `/opt/skytech/app` | Verwaltungsdienst samt gebauter Oberfläche | nein, im Image |
| `/etc/grafana/provisioning` | Provisioning (M4) | nein, im Image |

## Lokaler Betrieb ohne Supervisor

Fehlt `SUPERVISOR_TOKEN`, läuft der Container im Testmodus (D-013): `ingress_entry` kommt aus
`SKYTECH_INGRESS_ENTRY` (Voreinstellung `/api/hassio_ingress/lokaltest`), der Ingress-Port ist
nicht auf den Supervisor beschränkt. Ablauf in [test-strategie.md](test-strategie.md).
