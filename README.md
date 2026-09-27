# Skytech Data Insight

Home-Assistant-Add-on der Skytech-Produktfamilie für die Langzeitablage und Auswertung von
Energiedaten: **TimescaleDB** (PostgreSQL) für Leistungs-, Energie- und Soll/Ist-Werte,
**Grafana** für Dashboards, Verwaltung über ein eigenes Web-UI im HA-Seitenmenü.

> **Stand: Meilenstein M0** — Gerüst mit allen Diensten, Dienststatus und Grafana.
> Aufzeichnung, Backup-Funktionen, VSCode-Zugang und MCP folgen, siehe
> [docs/roadmap.md](docs/roadmap.md) und den [Umsetzungsplan](docs/umsetzungsplan.md).

## Installation

1. In Home Assistant: **Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories** und
   `https://github.com/nicohackl/Skytech-Data-Insight` hinzufügen.
2. **Skytech Data Insight** installieren (nur `amd64`). Das Image wird auf dem HA-Host gebaut;
   die erste Installation dauert einige Minuten.
3. Optional in der Konfiguration `grafana_admin_password` setzen – nur nötig, wenn Grafana auch im
   LAN unter Port 3000 genutzt werden soll.
4. Starten und über **Data Insight** im Seitenmenü öffnen.

## Zugänge

| Was | Wo | Anmeldung |
|---|---|---|
| Verwaltung | HA-Seitenmenü „Data Insight" | HA-Login |
| Grafana | HA-Seitenmenü → „Grafana" | automatisch mit dem HA-Benutzer |
| Grafana im LAN | `http://<ha-adresse>:3000/` | Benutzer `admin`, Passwort aus der Konfiguration |

Ports werden im Abschnitt „Netzwerk" der Add-on-Seite freigegeben oder abgeschaltet.
**Nie ins Internet freigeben.**

## Entwicklung

Regeln: [AGENTS.md](AGENTS.md). Doku: [docs/README.md](docs/README.md).
Lokaler Containertest ohne Home Assistant: [docs/test-strategie.md](docs/test-strategie.md).
