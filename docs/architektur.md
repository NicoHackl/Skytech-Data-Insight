# Architektur

> Beschreibt den **tatsächlichen** Stand (Meilenstein M0). Das Zielbild steht im
> [Umsetzungsplan](umsetzungsplan.md).

## Zweck und Abgrenzung

Home-Assistant-Add-on zur Langzeitablage und Auswertung von Energiedaten mit TimescaleDB und
Grafana. Stand M0: Container mit allen Diensten, Verwaltungsoberfläche mit Dienststatus,
Grafana über Ingress und LAN. **Noch nicht** vorhanden: Aufzeichnung von HA-Werten, Schema,
Backup-Funktionen, MCP (siehe [roadmap.md](roadmap.md)).

## Tech-Stack

| Schicht | Technologie | Warum |
|---|---|---|
| Datenbank | PostgreSQL 17.11 + TimescaleDB 2.30.1 | D-004 |
| Dashboards | Grafana 13.2.2 (OSS) | Plan, D-006 |
| Eingang | nginx (Debian-Paket) | trennt Ingress und LAN, D-006 |
| Verwaltungsdienst | Python 3.11, aiohttp, asyncpg | wie Skytech HEMS |
| Oberfläche | React 18 + TypeScript (`strict`) + Vite | eiserne Regel 8, [frontend.md](frontend.md) |
| Prozessaufsicht | s6-overlay v3 aus `ghcr.io/home-assistant/amd64-base-debian:bookworm` | D-005 |

Versionen sind im [`Dockerfile`](../Dockerfile) gepinnt.

## Dienste und Ports

```text
  HA-Supervisor ──Ingress──► nginx :8099 ──/──────────► app (aiohttp) 127.0.0.1:8100 ──socket──► postgres
  (172.30.32.2)                          └─/grafana/──► grafana 127.0.0.1:3001 ◄──┐
  LAN ─────────────────────► nginx :3000 ──<ingress_entry>/grafana/ ───────────────┘
                                          postgres 127.0.0.1:5432 + /run/postgresql
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
| `/data/grafana` | Grafana-Datenbank (SQLite), Plugins, Protokolle | ja |
| `/data/options.json` | Add-on-Optionen, vom Supervisor geschrieben, nur gelesen | ja |
| `/run/skytech/` | erzeugte Konfiguration (postgres, grafana, nginx) | nein, flüchtig |
| `/opt/skytech/app` | Verwaltungsdienst samt gebauter Oberfläche | nein, im Image |
| `/etc/grafana/provisioning` | Provisioning (M4) | nein, im Image |

## Lokaler Betrieb ohne Supervisor

Fehlt `SUPERVISOR_TOKEN`, läuft der Container im Testmodus (D-013): `ingress_entry` kommt aus
`SKYTECH_INGRESS_ENTRY` (Voreinstellung `/api/hassio_ingress/lokaltest`), der Ingress-Port ist
nicht auf den Supervisor beschränkt. Ablauf in [test-strategie.md](test-strategie.md).
