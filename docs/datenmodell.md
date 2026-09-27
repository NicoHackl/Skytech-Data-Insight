# Datenmodell

> Stand M0: nur die Grundobjekte. Das fachliche Schema (Sensor-Stammdaten, Hypertable
> `messwert`, Aggregate, Views) entsteht mit M1 über den Migrationsrunner – Entwurf im
> [Umsetzungsplan](umsetzungsplan.md#datenmodell-schema-skytech).

## Grundobjekte (`rootfs/usr/share/skytech/bootstrap.sql`)

Werden bei **jedem** Start idempotent sichergestellt.

| Objekt | Zweck |
|---|---|
| Rolle `skytech_app` | Verwaltungsdienst; Anmeldung nur über den lokalen Socket (D-012) |
| Datenbank `skytech` (Besitzer `skytech_app`, UTF-8) | alle Anwendungsdaten |
| Extension `timescaledb` in `skytech` | wird angelegt und bei jedem Start auf die Version des Images aktualisiert |

## Anmeldung (`pg_hba.conf`, `pg_ident.conf`)

| Verbindung | Betriebssystem-Benutzer → Rolle |
|---|---|
| lokaler Socket, `peer` | `postgres` → `postgres` (Init-Skripte) |
| lokaler Socket, `peer` | `root` → `skytech_app` (Verwaltungsdienst) |

TCP-Verbindungen sind in M0 nicht zugelassen; Postgres lauscht nur auf `localhost`.

## Zeit

Gespeichert wird in UTC (`timezone = 'UTC'`); für Menschen wird in Berliner Zeit ausgegeben
(eiserne Regel 9). Grafana zeigt standardmäßig `Europe/Berlin`.

## Hauptversion

Der Cluster merkt sich seine PostgreSQL-Hauptversion (`PG_VERSION`). Passt sie nicht zum Image,
bricht `init-postgres` mit einer deutschen Meldung ab – ein Wechsel geht nur über Dump und
Wiederherstellung (M2).
