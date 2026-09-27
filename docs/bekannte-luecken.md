# Bekannte Lücken

| # | Thema | Stand | Folge / nächster Schritt |
|---|---|---|---|
| L-001 | Test auf echter HA-Instanz | M0 ist lokal und in der CI getestet, der Supervisor-Ingress wurde nachgestellt | Auf der HA-Instanz prüfen: Panel im Seitenmenü, Grafana eingebettet, angemeldeter Benutzer = HA-Benutzer |
| L-002 | Header `X-Remote-User-Name` des Supervisors | Name des Headers aus der Supervisor-Doku übernommen, nicht auf echter Instanz gesehen | Fehlt er, meldet nginx den festen Benutzer `homeassistant` an – funktioniert, aber ohne Zuordnung zum HA-Benutzer. Bei L-001 mitprüfen |
| L-003 | HA-Backup sichert `/data/pgdata` als Dateien | Solange M2 fehlt, ist eine Sicherung im laufenden Betrieb nicht garantiert konsistent | M2: Dump vor dem Backup, `pgdata` ausschließen |
| L-004 | Kein Icon/Logo | `icon.png`/`logo.png` fehlen, HA zeigt ein Standardsymbol | Grafik liefern lassen |
| L-005 | Grafana-Warnungen „duplicate plugin" beim Start | harmlos, entstehen durch die mitgelieferten Plugins des Debian-Pakets | beobachten |
