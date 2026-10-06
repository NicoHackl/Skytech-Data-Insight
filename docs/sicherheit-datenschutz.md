# Sicherheit und Datenschutz

## Zugänge (Stand 0.5.0)

| Zugang | Schutz |
|---|---|
| Verwaltungsoberfläche | nur über HA-Ingress (HA-Login); nginx nimmt auf 8099 nur Verbindungen vom Supervisor `172.30.32.2` an |
| Grafana über Ingress | Anmeldung per `auth.proxy` mit dem HA-Benutzernamen; Grafana akzeptiert den Header nur von `127.0.0.1` (D-006) |
| Grafana im LAN (3000) | Grafana-Login `admin`; der Anmeldeheader wird von nginx entfernt, ein gefälschter Header führt zu `401` (in der CI geprüft). Ohne gesetztes Passwort ist die Anmeldung gesperrt (D-011) |
| PostgreSQL im Container | Verwaltungsdienst und Collector über den lokalen Socket mit `peer` (D-012), je Aufgabe eigene Rolle |
| PostgreSQL im LAN (5432) | nur `skytech_admin`/`skytech_reader`, nur Datenbank `skytech`, nur mit Passwort (SCRAM); ohne Passwort gesperrt. Unverschlüsselt – nur im LAN nutzen |
| MCP-Server (8765) | nur mit `mcp_token` (Bearer, Vergleich in konstanter Zeit); ohne Token aus. **Vollzugriff** auf Daten und Dashboards, deshalb Sicherung vor jeder Änderung und Protokoll, [mcp.md](mcp.md) |
| Grafana-Datenquelle | interne Rolle `skytech_grafana` (nur lesen, nur 127.0.0.1), Passwort erzeugt in `/data/secrets` |
| Home Assistant | WebSocket-API über den Supervisor mit dessen Token; das Add-on liest nur (Zustände, Verlauf) und schreibt nichts nach HA |
| Supervisor | Rolle `manager` (D-025), genutzt ausschließlich für `/addons/self/info`, `/addons/self/options` (prüfen, speichern) und `/network/info` – für die Seite „Zugänge“ |

Proxy-Benutzer bekommen in Grafana die Rolle `Admin`, weil nur HA-Administratoren das
Ingress-Panel sehen.

> **Wichtig:** Port 3000, 5432 und 8765 nie per Portfreigabe ins Internet öffnen.
> Fernzugriff nur über VPN.

## Secrets

- Keine Secrets in Vorlagen, erzeugten Konfigurationsdateien, Logs oder im Repo.
- Das Grafana-Passwort gelangt nur per Standardeingabe an `grafana cli`, die Datenbank-Passwörter
  nur über die Umgebung eines einzelnen `psql`-Aufrufs.
- Sicherungen enthalten **alle** aufgezeichneten Daten und die Grafana-Datenbank (inklusive
  Grafana-Benutzer). Download und Einspielen sind nur über den Ingress möglich (HA-Administratoren);
  heruntergeladene Pakete entsprechend aufbewahren.
- Beim Einspielen werden nur die bekannten Einträge eines Pakets als Dateien gelesen – Pfade im
  Archiv werden nie ausgepackt.
- Das Änderungsprotokoll speichert den HA-Benutzernamen zu jeder Änderung über die Oberfläche.
- **Seite „Zugänge“ (D-025):** Neue Passwörter und Token erzeugt der Server; sie stehen genau
  einmal in der HTTP-Antwort (`Cache-Control: no-store`) und danach nur noch in den
  Add-on-Optionen. Gespeicherte Werte gibt die API nie aus, nur „gesetzt/gesperrt“. Nach der
  Speicherung gelangen sie über die Umgebung (`psql`) bzw. die Standardeingabe
  (`grafana cli`) an ihr Ziel; deren Ausgabe wird verworfen, weil sie die Anweisung samt Passwort
  wiederholen könnte. Das Protokoll vermerkt nur Zugang und Benutzer.

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
