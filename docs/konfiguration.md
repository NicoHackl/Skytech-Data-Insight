# Konfiguration

## Add-on-Optionen

Gepflegt auf der Add-on-Seite in Home Assistant (Reiter „Konfiguration"). Fachliche Einstellungen
(Sensorauswahl, Aufbewahrung) kommen mit M1 in die Datenbank, nicht hierher (Plan).

| Option | Typ | Voreinstellung | Wirkung |
|---|---|---|---|
| `log_level` | `debug` \| `info` \| `warning` \| `error` | `info` | Protokollstufe von Init-Skripten und Verwaltungsdienst. Grafana protokolliert erst ab `debug` ausführlich, sonst nur Warnungen |
| `grafana_admin_password` | Passwort, optional | leer | Passwort des Grafana-Benutzers `admin` für die Anmeldung im LAN. Leer = bei jedem Start ein Zufallspasswort, LAN-Anmeldung damit gesperrt (D-011). Wird bei jedem Start gesetzt – eine Änderung wirkt nach dem Neustart des Add-ons |

## Ports

Freigabe, Umlegen oder Abschalten im Abschnitt „Netzwerk" der Add-on-Seite (D-009).

| Port | Standard | Zweck | Seit |
|---|---|---|---|
| `8099/tcp` | nur Ingress | Verwaltungsoberfläche und Grafana im HA-Seitenmenü | M0 |
| `3000/tcp` | `3000` | Grafana im LAN: `http://<ha-adresse>:3000/` | M0 |
| `5432/tcp` | – | PostgreSQL für VSCode | M1 (geplant) |
| `8765/tcp` | – | MCP-Server | M5 (geplant) |

## Umgebungsvariablen

Werden von `init-env` gesetzt bzw. im Image festgelegt – nicht von Hand.

| Variable | Quelle | Bedeutung |
|---|---|---|
| `SKYTECH_INGRESS_ENTRY` | Supervisor (`bashio::addon.ingress_entry`) | Ingress-Pfad ohne abschließenden Schrägstrich |
| `SKYTECH_LOG_LEVEL` | Option `log_level` | Protokollstufe |
| `SKYTECH_VERSION` | Build-Argument `BUILD_VERSION` | Anzeige in der Oberfläche |
| `PG_MAJOR` | `Dockerfile` | PostgreSQL-Hauptversion |
| `SUPERVISOR_TOKEN` | Supervisor | fehlt er, läuft der lokale Testmodus (D-013) |

## Secrets

Das Grafana-Passwort wird nur per Standardeingabe an `grafana cli` übergeben, nie in eine Datei
unter `/run` geschrieben und nie protokolliert. Vorlagen enthalten grundsätzlich keine Secrets.
