# Roadmap

Meilensteine laut [Umsetzungsplan](umsetzungsplan.md#meilensteine).

| Meilenstein | Inhalt | Stand |
|---|---|---|
| M0 Gerüst & Spike | Repo, Regeln, CI; Container mit Postgres + TimescaleDB, Grafana, nginx, Verwaltungsdienst unter s6; Grafana unter Ingress-Sub-Pfad | **umgesetzt 27.09.2026** — Test auf echter HA-Instanz offen (L-001) |
| M1 Datenbank & Collector | Schema, Migrationsrunner, Rollen, LAN-Zugang 5432, Collector, Aggregate, Retention | offen |
| M2 Backup | Dump vor HA-Backup, Auto-Restore, Download/Upload | offen |
| M3 Verwaltungsoberfläche | Sensoren, Aufbewahrung, Backups, Zugänge, Migrationen, Protokoll | offen |
| M3b Altdaten-Import | Recorder und Langzeitstatistik | offen |
| M4 Grafana | Datasource, Startdashboards | offen |
| M5 MCP | Server, Werkzeuge, Protokoll | offen |
| M6 Härtung & Release | Last, Restore-Probe, Release | offen |
| M7 HEMS-Anbindung | Attribut-Sensor oder direktes Schreiben | später |
