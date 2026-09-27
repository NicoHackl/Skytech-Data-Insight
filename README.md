# Skytech Data Insight

Home-Assistant-Add-on der Skytech-Produktfamilie für die Langzeitablage und Auswertung von
Energiedaten: **TimescaleDB** (PostgreSQL) für Leistungs-, Energie- und Soll/Ist-Werte,
**Grafana** für Dashboards, Verwaltung über ein eigenes Web-UI im HA-Seitenmenü.

> **Stand: Version 0.4.0** — Aufzeichnung ausgewählter HA-Werte mit Minutenwerten und
> Verdichtungen, Sensorverwaltung, Datenbankzugang aus dem LAN, Grafana mit Datenquelle,
> MCP-Server für LLMs, Sicherung und Wiederherstellung (HA-Backup und Download).
> Altdaten-Import und fertige Startdashboards folgen, siehe
> [docs/roadmap.md](docs/roadmap.md) und den [Umsetzungsplan](docs/umsetzungsplan.md).

## Installation

1. In Home Assistant: **Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories** und
   `https://github.com/nicohackl/Skytech-Data-Insight` hinzufügen.
2. **Skytech Data Insight** installieren (nur `amd64`). Das Image wird auf dem HA-Host gebaut;
   die erste Installation dauert einige Minuten.
3. Optional in der Konfiguration setzen: `grafana_admin_password` (Grafana im LAN, Port 3000),
   `db_password` / `db_readonly_password` (Datenbank im LAN, Port 5432, z. B. VSCode),
   `mcp_token` (MCP-Server für Claude, ChatGPT & Co., Port 8765).
4. Starten und über **Data Insight** im Seitenmenü öffnen.
5. Unter **Sensoren → Sensoren hinzufügen** die Entitäten (und bei Bedarf Attribute) wählen, die
   aufgezeichnet werden sollen.

## Zugänge

| Was | Wo | Anmeldung |
|---|---|---|
| Verwaltung | HA-Seitenmenü „Data Insight" | HA-Login |
| Grafana | HA-Seitenmenü → „Grafana" | automatisch mit dem HA-Benutzer |
| Grafana im LAN | `http://<ha-adresse>:3000/` | Benutzer `admin`, Passwort aus der Konfiguration |
| MCP für LLMs | `http://<ha-adresse>:8765/mcp` | Header `Authorization: Bearer <mcp_token>` – [Anleitung](docs/mcp.md) |
| Datenbank im LAN | `<ha-adresse>:5432`, Datenbank `skytech` | `skytech_admin` bzw. `skytech_reader`, Passwort aus der Konfiguration – [Anleitung](docs/datenbankzugang.md) |

Ports werden im Abschnitt „Netzwerk" der Add-on-Seite freigegeben oder abgeschaltet.
**Nie ins Internet freigeben.**

## Entwicklung

Regeln: [AGENTS.md](AGENTS.md). Doku: [docs/README.md](docs/README.md).
Lokaler Containertest ohne Home Assistant: [docs/test-strategie.md](docs/test-strategie.md).
