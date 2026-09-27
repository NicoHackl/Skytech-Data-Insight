# Bekannte Lücken

| # | Thema | Stand | Folge / nächster Schritt |
|---|---|---|---|
| L-001 | Test auf echter HA-Instanz | M0 vom User am 27.09.2026 bestätigt. M1 ist lokal gegen einen nachgebauten HA getestet (WebSocket über den Supervisor-Proxy noch nicht) | Nach dem Update: Übersicht „Aufzeichnung läuft", Sensoren anlegen, Werte in VSCode sehen |
| L-002 | Header `X-Remote-User-Name` des Supervisors | Name des Headers aus der Supervisor-Doku übernommen, nicht auf echter Instanz gesehen | Fehlt er, meldet nginx den festen Benutzer `homeassistant` an – funktioniert, aber ohne Zuordnung zum HA-Benutzer. Bei L-001 mitprüfen |
| L-003 | HA-Backup sichert `/data/pgdata` als Dateien | Solange M2 fehlt, ist eine Sicherung im laufenden Betrieb nicht garantiert konsistent | M2: Dump vor dem Backup, `pgdata` ausschließen |
| L-004 | Kein Icon/Logo | `icon.png`/`logo.png` fehlen, HA zeigt ein Standardsymbol | Grafik liefern lassen |
| L-005 | Grafana-Warnungen „duplicate plugin" beim Start | harmlos, entstehen durch die mitgelieferten Plugins des Debian-Pakets | beobachten |
| L-006 | Ausfallzeiten über 10 Tage | Der Collector lädt höchstens 10 Tage aus dem HA-Verlauf nach. War das Add-on länger aus, gilt für die Lücke der letzte Wert fort (Minutenwerte), obwohl nichts bekannt ist | Altdaten-Import (M3b) für den Zeitraum ausführen; später Lücken markieren |
| L-007 | Minutenwerte nach Änderungen per SQL | Werden Rohwerte von Hand eingefügt oder geändert, rechnet der Collector die Minutenwerte nicht automatisch neu | Bis M3b: Neuberechnung nur über Neustart mit Lücke bzw. Import |
| L-008 | Neue Schemas von `skytech_admin` | Lesen darf `skytech_reader` neue Tabellen automatisch; bei einem neuen **Schema** fehlt ihm aber `USAGE`, wenn es nicht per Standardrecht vererbt wird | `GRANT USAGE ON SCHEMA … TO skytech_reader` mitschreiben |

