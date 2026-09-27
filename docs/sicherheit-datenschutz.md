# Sicherheit und Datenschutz

## Zugänge (Stand M0)

| Zugang | Schutz |
|---|---|
| Verwaltungsoberfläche | nur über HA-Ingress (HA-Login); nginx nimmt auf 8099 nur Verbindungen vom Supervisor `172.30.32.2` an |
| Grafana über Ingress | Anmeldung per `auth.proxy` mit dem HA-Benutzernamen; Grafana akzeptiert den Header nur von `127.0.0.1` (D-006) |
| Grafana im LAN (3000) | Grafana-Login `admin`; der Anmeldeheader wird von nginx entfernt, ein gefälschter Header führt zu `401` (in der CI geprüft). Ohne gesetztes Passwort ist die Anmeldung gesperrt (D-011) |
| PostgreSQL | nur lokaler Socket mit `peer` (D-012); kein TCP-Zugang aus dem LAN |

Proxy-Benutzer bekommen in Grafana die Rolle `Admin`, weil nur HA-Administratoren das
Ingress-Panel sehen.

> **Wichtig:** Port 3000 (und später 5432 und 8765) nie per Portfreigabe ins Internet öffnen.
> Fernzugriff nur über VPN.

## Secrets

- Keine Secrets in Vorlagen, erzeugten Konfigurationsdateien, Logs oder im Repo.
- Das Grafana-Passwort gelangt nur per Standardeingabe an `grafana cli`.

## Externe Dienste

| Dienst | Zweck | Abgeschaltet durch |
|---|---|---|
| Grafana-Nutzungsstatistik, Update- und Plugin-Prüfung, News-Feed | – | `grafana.ini` (`reporting_enabled`, `check_for_updates`, `check_for_plugin_updates`, `news_feed_enabled`) |
| TimescaleDB-Telemetrie | – | `timescaledb.telemetry_level = off` |
| Paketquellen (PGDG, Timescale, Grafana) | nur beim Bauen des Images | – |

Zur Laufzeit baut das Add-on von sich aus keine Verbindung ins Internet auf.

## Personenbezogene Daten

Energiedaten lassen Rückschlüsse auf Anwesenheit und Gewohnheiten zu. Sie verlassen das Gerät
nur über die bewusst freigegebenen Zugänge (LAN-Ports, Backups, später MCP).
