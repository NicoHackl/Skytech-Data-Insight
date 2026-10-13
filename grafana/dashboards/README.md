# Versionierte Grafana-Dashboards

Quelle der Dashboards, die zu einer Skytech-Funktion gehören. Sie werden **nicht** ins Image
provisioniert, sondern über den MCP-Server gespeichert (`grafana_dashboard_speichern`, Ordner
„Skytech“) und bleiben in Grafana editierbar. Wer ein Dashboard in Grafana ändert, holt die
Änderung mit `grafana_dashboard_lesen` zurück in diese Datei – sonst überschreibt das nächste
Speichern aus dem Repo sie.

| Datei | uid | Inhalt |
|---|---|---|
| `skytech-dynamischer-strompreis.json` | `skytech-dynamischer-strompreis` | Preis, PV- und Verbrauchsprognose gegen Ist, Speicher, Netzlade-Freigabe, Prognosegüte und Rückblick „ideales Netzladen gestern“ (SkytechHEMS D-065, Data Insight D-027) |

Regeln:

- Datenquelle immer `{"type": "grafana-postgresql-datasource", "uid": "skytech-db"}`, Zeitzone
  `Europe/Berlin`, Datum in Texten als `TT.MM.JJJJ`.
- Zeitfilter auf **jede** Seite einer Abfrage setzen: `v_prognose_vs_ist` und
  `v_prognose_guete_tag` reichen ihn nicht an Vortagsprognose und Ist durch
  ([L-017](../../docs/bekannte-luecken.md)). Das Dashboard liest deshalb `v_prognose_aktuell`,
  `v_prognose_vortag` und `v_hems_rolle_15min` je eigens gefiltert.
- `tests/test_dashboards.py` prüft Aufbau und führt jede Abfrage (Panels, Anmerkungen, Variablen)
  gegen ein frisch migriertes Schema mit der Rolle `skytech_reader` aus.
