# MCP-Server (LLM-Zugang)

Über den MCP-Server kann ein LLM (Claude, ChatGPT oder jeder andere MCP-Client) die Datenbank
lesen und ändern, Sensoren anlegen und Grafana-Dashboards bauen. Vorgezogen aus M5 (D-021).

## Einrichten

1. Zufälliges Token erzeugen (mindestens 16 Zeichen), z. B. `openssl rand -base64 32`.
2. In der Add-on-Konfiguration als `mcp_token` eintragen, Add-on neu starten.
3. Port `8765` ist im Abschnitt „Netzwerk" freigegeben (Voreinstellung).

| Feld | Wert |
|---|---|
| URL | `http://<ha-adresse>:8765/mcp` |
| Transport | Streamable HTTP (zustandslos) |
| Anmeldung | Header `Authorization: Bearer <mcp_token>` |

### Claude Code

```bash
claude mcp add --transport http skytech-data-insight http://<ha-adresse>:8765/mcp \
  --header "Authorization: Bearer <mcp_token>"
```

### Claude Desktop / andere Clients

Als „Remote MCP Server" mit URL und Header eintragen. Clients ohne Header-Unterstützung lassen sich
über `mcp-remote` anbinden:

```json
{ "mcpServers": { "skytech-data-insight": {
    "command": "npx",
    "args": ["mcp-remote", "http://<ha-adresse>:8765/mcp", "--header", "Authorization: Bearer <mcp_token>"] } } }
```

## Werkzeuge

| Werkzeug | Art | Wirkung |
|---|---|---|
| `schema_anzeigen` | lesen | Tabellen, Sichten, Verdichtungen mit Spalten |
| `sql_abfrage` | lesen | SQL in schreibgeschützter Transaktion, 30 s Zeitlimit, bis 5 000 Zeilen |
| `statistik` | lesen | Größe, Einstellungen, je Sensor Anzahl und Zeitraum |
| `sensoren_auflisten`, `katalog_anzeigen` | lesen | Sensorliste; Kategorien, Größen, Anlagen, Paare |
| `backups_auflisten` | lesen | Sicherungen unter `/data/backup` |
| `grafana_datenquellen`, `grafana_dashboards_auflisten`, `grafana_dashboard_lesen` | lesen | Grafana |
| `sql_ausfuehren` | schreiben | beliebiges SQL in einer Transaktion |
| `migration_anlegen` | schreiben | dauerhafte Schemaänderung als `/data/migrations/1NNN_name.sql`; scheitert sie, bleibt nichts zurück |
| `sensoren_anlegen`, `sensor_aendern` | schreiben | Sensorliste (Aufzeichnung reagiert sofort) |
| `aufbewahrung_setzen` | schreiben | Aufbewahrung von Roh- und Minutenwerten |
| `backup_erstellen` | schreiben | Sicherung sofort anlegen |
| `grafana_dashboard_speichern`, `grafana_dashboard_loeschen` | schreiben | Dashboards im Ordner „Skytech" |

Der Server gibt dem Modell beim Verbinden eine Beschreibung von Datenmodell, Grafana-Datenquelle
(`uid: skytech-db`) und Regeln mit (`instructions` in `app/mcp_server.py`).

## Schutz trotz Vollzugriff

- **Automatische Sicherung** (`pg_dump`) vor jeder schreibenden Datenbank-Aktion; scheitert sie,
  läuft die Aktion nicht. Aufbewahrt werden die letzten 20 (`/data/backup/mcp_*.dump`).
- **Änderungsprotokoll:** jede schreibende Aktion mit Quelle `mcp` in
  `skytech_config.aenderungsprotokoll`.
- **Zeitlimits:** 30 s für Abfragen, 5 min für schreibendes SQL.
- Grafana-Dashboards stehen nicht im `pg_dump`; beim Überschreiben führt Grafana eine
  Versionsgeschichte, **Löschen ist endgültig**.
- Ohne `mcp_token` (oder mit weniger als 16 Zeichen) startet der Server nicht.

> **Sicherheitshinweis:** Das Token gewährt vollen Zugriff auf die Daten. Port 8765 nie ins
> Internet freigeben, Token nicht weitergeben; bei Verdacht in der Konfiguration ändern und neu
> starten.

## Technik

- Eigener s6-Dienst `mcp`, Prozess `app/mcp_server.py` (MCP-SDK 2.2, uvicorn), Datenbankrolle
  `skytech_admin` über den lokalen Socket.
- Grafana wird über den Auth-Proxy als Benutzer `skytech-mcp` angesprochen – nur aus dem Container
  möglich (D-006).
- Fachlogik ohne Protokoll in `app/mcp_tools.py`, Sicherung in `app/backup.py`.
