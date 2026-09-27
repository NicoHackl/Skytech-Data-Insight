# Sicherung und Wiederherstellung (M2)

Drei Wege, alle mit demselben Format (`pg_dump`, Format custom):

| Weg | Wann | Inhalt |
|---|---|---|
| **Home-Assistant-Backup** | bei jedem HA-Backup (automatisch, manuell, zeitgesteuert) | Datenbank-Dump + konsistente Kopie der Grafana-Datenbank |
| **Download in der Oberfläche** | „Sicherungen → Herunterladen" | `.tar` mit Datenbank, Grafana und Beschreibung – unabhängig von HA aufbewahrbar |
| **Lokale Sicherungen** | vor jeder schreibenden MCP-Aktion, vor jeder Wiederherstellung, „Jetzt sichern" | einzelne `.dump`-Dateien unter `/data/backup` |

Zusätzlich jederzeit: `pg_dump` über den LAN-Zugang (Port 5432, [datenbankzugang.md](datenbankzugang.md)).

## Home-Assistant-Backup (D-023)

- `backup_pre` (`/usr/bin/skytech-backup-pre`) schreibt vor dem Backup
  `/data/backup/ha_snapshot.dump` und `/data/backup/ha_snapshot_grafana.db`
  (SQLite-Online-Kopie). `backup_post` löscht beide wieder.
- Das Datenbankverzeichnis `/data/pgdata` ist ausgeschlossen (`backup_exclude`) – eine laufende
  Datenbank lässt sich als Dateien nicht verlässlich sichern. Ebenfalls ausgeschlossen sind die
  lokalen Sicherungen (`backup/mcp_*`, `backup/manuell_*`, …), damit HA-Backups klein bleiben.
- **Wiederherstellung:** HA stellt `/data` ohne `pgdata` wieder her. Beim nächsten Start erkennt
  `init-env` den Dump bei fehlendem Cluster, setzt die Grafana-Kopie ein, `init-postgres` legt den
  Cluster neu an und spielt den Dump ein (`restore-db.sh`). Der eingespielte Dump bleibt als
  `ha_wiederhergestellt_<zeit>.dump` liegen. Danach lädt der Collector die Lücke aus dem HA-Verlauf
  nach (bis 10 Tage).
- Scheitert das Einspielen, startet die Datenbank nicht; der Dump bleibt für einen weiteren Versuch
  unter `/data/backup/ha_snapshot.dump` liegen.

## Download und Einspielen in der Oberfläche

- **Herunterladen:** frischer Dump + Grafana-Kopie + `sicherung.json` (Add-on-Version, Zeitpunkt)
  als `skytech-data-insight_<JJJJ-MM-TT_hhmm>.tar`. Das Paket wird nach dem Senden gelöscht.
- **Einspielen:** `.tar` oder `.dump` hochladen → wird nur geprüft (`pg_restore --list` bzw.
  Paketinhalt) und beschrieben → erst nach Bestätigung eingespielt. Ablauf:
  1. Sicherung des aktuellen Stands (`vor_wiederherstellung_*.dump`),
  2. Aufzeichnung anhalten, Puffer schreiben, Verbindungen schließen,
  3. Datenbank `skytech` löschen und neu anlegen, `timescaledb_pre_restore()`, `pg_restore`,
     `timescaledb_post_restore()`, Rechte setzen (`/usr/lib/skytech/restore-db.sh`),
  4. bei `.tar` mit Grafana: Grafana anhalten, Datenbank tauschen, starten,
  5. Verwaltungsdienst und MCP-Server neu starten (Migrationen laufen, Collector lädt die Lücke nach).
  Ergebnis in `/data/backup/wiederherstellung.json` und im Änderungsprotokoll
  (`sicherung_wiederhergestellt`).
- Jede lokale Sicherung lässt sich herunterladen, einspielen oder löschen.

## Aufbewahrung lokaler Sicherungen

| Art (Präfix) | Behalten |
|---|---|
| `mcp_` | 20 |
| `manuell_` | 20 |
| `vor_wiederherstellung_` | 5 |
| `upload_` | 5 |
| `ha_wiederhergestellt_` | 3 |

## Grenzen

- Ein Dump lässt sich nur mit derselben TimescaleDB-Version sicher einspielen (Vorgabe von
  Timescale). Nach einem Add-on-Update mit neuer TimescaleDB-Version: ältere Dumps zuerst mit der
  alten Version einspielen oder auf die neue Version hinweisen lassen (siehe
  [bekannte-luecken.md](bekannte-luecken.md)).
- Grafana-Dashboards sind im HA-Backup und im Download-Paket enthalten, **nicht** in den
  einzelnen `.dump`-Dateien.
