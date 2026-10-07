# Konfiguration

## Add-on-Optionen

Gepflegt auf der Add-on-Seite in Home Assistant (Reiter „Konfiguration"). Fachliche Einstellungen
stehen nicht hier, sondern in der Datenbank: Sensorauswahl in `skytech.sensor` (Seite „Sensoren"),
Aufbewahrung in `skytech_config.einstellung` (Seite „Speicher“, siehe [datenmodell.md](datenmodell.md)).

Passwörter und MCP-Token lassen sich zusätzlich auf der Seite **„Zugänge“** neu erzeugen oder
sperren. Die Seite schreibt dieselben Optionen über die Supervisor-API und wendet sie ohne
Neustart an (D-025); auf der Konfigurationsseite erscheint danach derselbe Wert.

| Option | Typ | Voreinstellung | Wirkung |
|---|---|---|---|
| `log_level` | `debug` \| `info` \| `warning` \| `error` | `info` | Protokollstufe von Init-Skripten und Verwaltungsdienst. Grafana protokolliert erst ab `debug` ausführlich, sonst nur Warnungen |
| `grafana_admin_password` | Passwort, optional | leer | Passwort des Grafana-Benutzers `admin` für die Anmeldung im LAN. Leer = bei jedem Start ein Zufallspasswort, LAN-Anmeldung damit gesperrt (D-011). Wird bei jedem Start gesetzt – eine Änderung wirkt nach dem Neustart des Add-ons |
| `db_password` | Passwort, optional | leer | Passwort von `skytech_admin` (Vollzugriff aus dem LAN, z. B. VSCode). Leer = gesperrt. Wirkt nach Neustart, über „Zugänge“ sofort |
| `db_readonly_password` | Passwort, optional | leer | Passwort von `skytech_reader` (nur lesen). Leer = gesperrt. Wirkt nach Neustart, über „Zugänge“ sofort |
| `mcp_token` | Passwort, optional | leer | Token des MCP-Servers (mindestens 16 Zeichen). Leer = MCP-Server aus. Über „Zugänge“ neu erzeugt, startet nur der MCP-Server neu. [mcp.md](mcp.md) |

## Grafana in einem HA-Dashboard einbinden

Läuft HA über https, blockt der Browser http-iframes (`http://<ip>:3000`). Stattdessen in der
Karte „Webseite“ den **relativen Ingress-Pfad** eintragen, ohne Host und Port:

```yaml
type: iframe
url: /api/hassio_ingress/<ingress_token>/grafana/d/<dashboard-uid>?kiosk=true
```

`<ingress_token>` steht in der Adresse des Seitenmenüpunkts „Data Insight“. Die Karte liegt im
selben https-Origin wie HA und funktioniert deshalb auch über die externe Domain; Grafana meldet
den HA-Benutzer automatisch an. Zeigt die Karte 401 oder bleibt leer, fehlt das Ingress-Sitzungs-Cookie
(es entsteht beim Öffnen eines Ingress-Panels und gilt etwa eine Stunde): „Data Insight“ einmal
öffnen und neu laden. Entscheidung: [adr/D-026-grafana-einbettung.md](adr/D-026-grafana-einbettung.md).

## Ports

Freigabe, Umlegen oder Abschalten im Abschnitt „Netzwerk" der Add-on-Seite (D-009).

| Port | Standard | Zweck | Seit |
|---|---|---|---|
| `8099/tcp` | nur Ingress | Verwaltungsoberfläche und Grafana im HA-Seitenmenü | M0 |
| `3000/tcp` | `3000` | Grafana im LAN: `http://<ha-adresse>:3000/` | M0 |
| `5432/tcp` | `5432` | PostgreSQL im LAN, [datenbankzugang.md](datenbankzugang.md) | M1 |
| `8765/tcp` | `8765` | MCP-Server, [mcp.md](mcp.md) | 0.3.0 |

## Umgebungsvariablen

Werden von `init-env` gesetzt bzw. im Image festgelegt – nicht von Hand.

| Variable | Quelle | Bedeutung |
|---|---|---|
| `SKYTECH_INGRESS_ENTRY` | Supervisor (`bashio::addon.ingress_entry`) | Ingress-Pfad ohne abschließenden Schrägstrich |
| `SKYTECH_LOG_LEVEL` | Option `log_level` | Protokollstufe |
| `SKYTECH_VERSION` | Build-Argument `BUILD_VERSION` | Anzeige in der Oberfläche |
| `PG_MAJOR` | `Dockerfile` | PostgreSQL-Hauptversion |
| `SUPERVISOR_TOKEN` | Supervisor | fehlt er, läuft der lokale Testmodus (D-013); zugleich Token für die HA-WebSocket-API |
| `SKYTECH_HA_URL`, `SKYTECH_HA_TOKEN` | nur lokaler Test | WebSocket-URL und Token eines HA; haben Vorrang vor dem Supervisor |
| `SKYTECH_DB_HOST`, `SKYTECH_DB_PORT`, `SKYTECH_DB_NAME`, `SKYTECH_DB_TEST_PASSWORD` | nur Tests | Datenbankverbindung abweichend vom lokalen Socket |

## Secrets

Das Grafana-Passwort wird nur per Standardeingabe an `grafana cli` übergeben, die
Datenbank-Passwörter nur über die Umgebung genau eines `psql`-Aufrufs (`\getenv` in
`bootstrap.sql`). Keines wird in eine Datei unter `/run` geschrieben oder protokolliert. Vorlagen
enthalten grundsätzlich keine Secrets.
