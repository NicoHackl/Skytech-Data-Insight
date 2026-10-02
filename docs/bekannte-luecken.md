# Bekannte Lücken

| # | Thema | Stand | Folge / nächster Schritt |
|---|---|---|---|
| L-001 | Test auf echter HA-Instanz | M0 vom User am 27.09.2026 bestätigt. M1 ist lokal gegen einen nachgebauten HA getestet (WebSocket über den Supervisor-Proxy noch nicht) | Nach dem Update: Übersicht „Aufzeichnung läuft", Sensoren anlegen, Werte in VSCode sehen |
| L-002 | Header `X-Remote-User-Name` des Supervisors | Name des Headers aus der Supervisor-Doku übernommen, nicht auf echter Instanz gesehen | Fehlt er, meldet nginx den festen Benutzer `homeassistant` an – funktioniert, aber ohne Zuordnung zum HA-Benutzer. Bei L-001 mitprüfen |
| L-003 | HA-Backup sichert `/data/pgdata` als Dateien | Mit 0.4.0 behoben (D-023) | – |
| L-004 | Kein Icon/Logo | `icon.png`/`logo.png` fehlen, HA zeigt ein Standardsymbol | Grafik liefern lassen |
| L-005 | Grafana-Warnungen „duplicate plugin" beim Start | harmlos, entstehen durch die mitgelieferten Plugins des Debian-Pakets | beobachten |
| L-006 | Ausfallzeiten über 10 Tage | Der Collector lädt höchstens 10 Tage aus dem HA-Verlauf nach. War das Add-on länger aus, gilt für die Lücke der letzte Wert fort (Minutenwerte), obwohl nichts bekannt ist | Altdaten-Import (M3b) für den Zeitraum ausführen; später Lücken markieren |
| L-007 | Minutenwerte nach Änderungen per SQL | Werden Rohwerte von Hand eingefügt oder geändert, rechnet der Collector die Minutenwerte nicht automatisch neu | Bis M3b: Neuberechnung nur über Neustart mit Lücke bzw. Import |
| L-008 | Neue Schemas von `skytech_admin` | Lesen darf `skytech_reader` neue Tabellen automatisch; bei einem neuen **Schema** fehlt ihm aber `USAGE`, wenn es nicht per Standardrecht vererbt wird | `GRANT USAGE ON SCHEMA … TO skytech_reader` mitschreiben |
| L-009 | `backup_exclude` auf echter HA-Instanz | Muster `pgdata`, `pgdata/*`, `pgdata/**` sind lokal nicht mit dem Supervisor prüfbar. Greift der Ausschluss nicht, enthält das Backup zusätzlich die Rohdateien (größer); die Wiederherstellung nutzt dann die Dateien statt des Dumps | Nach dem ersten HA-Backup Größe prüfen; Wiederherstellung einmal an einer Testinstanz durchspielen |
| L-010 | Dump und TimescaleDB-Version | Timescale unterstützt das Einspielen nur in dieselbe Erweiterungsversion. Bisher ist nur 2.30.1 im Umlauf | Vor dem ersten Versionswechsel: Version im Dump prüfen und beim Einspielen warnen |
| L-011 | Größe und Dauer bei vielen Daten | `backup_pre` läuft vor dem HA-Backup; bei Gigabyte-Datenbanken dauert der Dump Minuten. Ein Zeitlimit des Supervisors ist nicht dokumentiert. Uploads laufen über den Ingress – eine Größengrenze dort ist nicht bekannt | Bei großen Datenmengen beobachten; notfalls `pg_dump` über Port 5432 |
| L-012 | Stillstand der Minutenwerte am 27.09.2026 | Ursache dank Protokoll aus 0.4.1 gefunden: gleichzeitiges `flush()` beider Schleifen („pop from an empty deque"). Mit 0.4.2 behoben. Zwischen 27.09. und dem Update können vereinzelt Rohwerte fehlen, die während eines solchen Zusammentreffens eingingen | – |
