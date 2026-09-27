# Roadmap

Meilensteine laut [Umsetzungsplan](umsetzungsplan.md#meilensteine).

| Meilenstein | Inhalt | Stand |
|---|---|---|
| M0 Gerüst & Spike | Repo, Regeln, CI; Container mit Postgres + TimescaleDB, Grafana, nginx, Verwaltungsdienst unter s6; Grafana unter Ingress-Sub-Pfad | **umgesetzt 27.09.2026**, auf echter HA-Instanz bestätigt |
| M1 Datenbank & Collector | Schema, Migrationsrunner, Rollen, LAN-Zugang 5432, Collector mit Nachladen, Minutenwerte, Verdichtungen, Aufbewahrung; dazu die komplette Sensorverwaltung aus M3 (D-019) | **umgesetzt 27.09.2026** — Test auf echter HA-Instanz offen |
| M2 Backup | Dump vor HA-Backup, Auto-Restore, Download/Upload, Seite „Sicherungen" | **umgesetzt 27.09.2026** (0.4.0) |
| M3 Verwaltungsoberfläche | Aufbewahrung, Zugänge, Migrationen, Protokoll (Sensoren in M1, Sicherungen in M2) | offen |
| M3b Altdaten-Import | Recorder und Langzeitstatistik | offen |
| M4 Grafana | Datasource (vorgezogen in 0.3.0, D-022), Startdashboards | teilweise |
| M5 MCP | Server, Werkzeuge, Protokoll, automatische Sicherung | **umgesetzt 27.09.2026** (vorgezogen, D-021) |
| M6 Härtung & Release | Last, Restore-Probe, Release | offen |
| M7 HEMS-Anbindung | Attribut-Sensor oder direktes Schreiben | später |
