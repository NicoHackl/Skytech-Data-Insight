# Datenmodell

Datenbank `skytech` (PostgreSQL 17 + TimescaleDB). Namen sind deutsch – sie sind der Datenvertrag
für SQL, Grafana und LLMs (eiserne Regel 2). Zeitstempel sind `timestamptz` und werden in UTC
gespeichert; in Abfragen für Menschen `AT TIME ZONE 'Europe/Berlin'` verwenden.

Das Schema entsteht über Migrationen (`app/sql/`, Runner `app/migration_runner.py`), Rollen und
Datenbank über `rootfs/usr/share/skytech/bootstrap*.sql`.

## Überblick

```text
skytech.kategorie ─┐   skytech.groesse ─┐
                   ▼                    ▼
               skytech.sensor ◄──────────────────────────────┐
                   │ id                                      │
      ┌────────────┴─────────────┐                           │
      ▼                          ▼                           │
skytech.messwert  ──(minute_values.py)──►  skytech.messwert_1min
 (jede Änderung)                            (je Minute, zeitgewichtet)
                                                 │ Continuous Aggregates
                               ┌─────────────────┼──────────────────┐
                               ▼                 ▼                  ▼
                        messwert_15min      messwert_1h       messwert_1d (Berliner Tag)
```

## Tabellen

### `skytech.sensor` — was aufgezeichnet wird

| Spalte | Bedeutung |
|---|---|
| `id` | Schlüssel, in allen Messwerttabellen `sensor_id` |
| `entity_id` | HA-Entität, z. B. `sensor.pv_leistung` |
| `attribut` | leer = Zustand der Entität, sonst Name des Attributs (z. B. `current_temperature`) |
| `name` | Anzeigename |
| `kategorie` | → `skytech.kategorie` (pv, speicher, netz, heizung, verbraucher, sonstiges) |
| `groesse` | → `skytech.groesse` (leistung, energie, ladezustand, temperatur, spannung, strom, zustand, preis, sonstiges) |
| `rolle` | `ist`, `soll` oder leer |
| `soll_ist_paar` | Paarname; je Paar höchstens ein Soll und ein Ist (D-016) |
| `einheit`, `anlage` | frei; `anlage` fasst Sensoren einer Anlage zusammen |
| `energie_zaehler` | Zählerstand (HA `state_class` total/total_increasing): Minutenwerte tragen den Zuwachs |
| `aktiv` | aus = keine neuen Werte, vorhandene bleiben |
| `quelle` | `ha` (aus Home Assistant), `hems` für Messreihen, die SkytechHEMS selbst schreibt, `extern` vorbereitet |
| `verwaltet_von` | leer oder `hems` (vom HEMS verwaltet und gesperrt, siehe unten) |

Eindeutig: je Entität der Zustand und jedes Attribut höchstens einmal. Jede Änderung an der
Tabelle meldet sich per `NOTIFY skytech_sensor` beim Collector – auch Änderungen per SQL wirken
sofort.

Kategorien und Größen sind Tabellen: neue Einträge per `INSERT`, ohne Schemaänderung (D-018).

### `skytech.messwert` — Rohwerte (Hypertable, Chunks 7 Tage)

| Spalte | Bedeutung |
|---|---|
| `zeit` | Zeitpunkt der Änderung (Zustand: `last_changed`, Attribut: `last_updated`) |
| `sensor_id` | → `sensor` |
| `wert` | Zahl; `on`/`off` als 1/0 (D-017); leer bei Text, `unknown`, `unavailable` |
| `text_wert` | Originaltext, wenn der Wert keine reine Zahl ist |

Geschrieben wird nur bei echter Änderung. Primärschlüssel `(sensor_id, zeit)`.

### `skytech.messwert_1min` — Minutenwerte (Hypertable, Chunks 30 Tage)

Berechnet in `app/minute_values.py` (D-015): jeder Rohwert gilt, bis der nächste kommt. Ausnahme
Reihen mit `quelle = 'hems'`: ihr Rohwert gilt nur für seine Minute, Lücken bleiben Lücken
(Vertrag 0.3).

| Spalte | Bedeutung |
|---|---|
| `zeit` | Beginn der Minute |
| `mittel` | zeitgewichtetes Mittel über die Sekunden mit bekanntem Wert |
| `minimum`, `maximum`, `letzter` | über die Minute (inklusive des fortgeltenden Werts) |
| `zuwachs` | nur Zähler: Zuwachs in der Minute; sinkt der Zähler, gilt das als Neustart ab 0 |
| `anzahl` | Rohwerte, die in der Minute eingingen |
| `abdeckung_s` | Sekunden mit bekanntem Zahlenwert (0–60); Minuten ohne Zahlenwert entfallen |

Für Schaltzustände ist `mittel` der Einschaltanteil (0,4 = 24 s an).

### Verdichtungen (Continuous Aggregates)

`skytech.messwert_15min`, `skytech.messwert_1h`, `skytech.messwert_1d` mit denselben Spalten.
`mittel` ist nach `abdeckung_s` gewichtet, `zuwachs` summiert, `letzter` der letzte Minutenwert.
Tage laufen nach Berliner Kalendertag. Aktualisierung automatisch (15 min: alle 5 min, 1 h: alle
15 min, 1 d: stündlich) über ein Fenster von 30 Tagen; jüngere, noch nicht verdichtete Minuten
werden bei Abfragen live ergänzt (`materialized_only = false`).

### Kompression und Aufbewahrung

`messwert` und `messwert_1min` werden nach 7 Tagen spaltenweise komprimiert (nach `sensor_id`).
Aufbewahrung steht in `skytech_config.einstellung` und wird von
`skytech_config.aufbewahrung_anwenden()` umgesetzt (beim Start des Add-ons; nach einer Änderung per
SQL die Funktion selbst aufrufen):

| Schlüssel | Voreinstellung | Bedeutung |
|---|---|---|
| `aufbewahrung_rohwerte_tage` | `365` | Rohwerte älter als das werden gelöscht; `null` = nie |
| `aufbewahrung_minutenwerte_tage` | `null` | Minutenwerte; mindestens 31, weil die Verdichtungen 30 Tage rückwirkend aktualisiert werden |

Die Verdichtungen werden nie gelöscht.

## Sichten

| Sicht | Inhalt |
|---|---|
| `v_messwert`, `v_messwert_1min`, `v_messwert_15min`, `v_messwert_1h`, `v_messwert_1d` | Werte der jeweiligen Stufe mit Name, Entität, Kategorie, Größe, Rolle, Einheit, Anlage |
| `v_pv`, `v_speicher`, `v_netz`, `v_heizung`, `v_verbraucher` | Minutenwerte je Kategorie |
| `v_soll_ist` | je Minute und Paar: `soll`, `ist`, `abweichung` (= Ist − Soll) |

Beispiel (Tagesenergie der PV im September, Berliner Tage):

```sql
SELECT zeit AT TIME ZONE 'Europe/Berlin' AS tag, name, zuwachs AS kwh
FROM skytech.v_messwert_1d
WHERE kategorie = 'pv' AND groesse = 'energie'
  AND zeit >= '2026-09-01 00:00 Europe/Berlin'
ORDER BY tag;
```

## Anbindung von SkytechHEMS (Migrationen 0003 und 0004, D-027)

Für den dynamischen Strompreis schreibt SkytechHEMS über die Rolle `skytech_hems` – ausschließlich
über die Funktionen `hems_sensor_sichern`, `hems_sensor_stilllegen`, `hems_zuordnen`,
`hems_messwerte_schreiben` und `hems_lauf_schreiben`. Dazu gehören:

| Objekt | Inhalt |
|---|---|
| `sensor.verwaltet_von` | `hems` = vom HEMS angelegt oder übernommen; ein Trigger sperrt Änderungen und Löschen für alle anderen (SQLSTATE `SKY01`) |
| `hems_zuordnung`, `v_hems_zuordnung` | HEMS-Rolle (z. B. `hausverbrauch`) → Sensor mit Gültigkeit; die erste Zuordnung gilt ab `-infinity` |
| `v_hems_rolle_1min`, `v_hems_rolle_15min` | Minuten- bzw. 15-min-Werte je Rolle, über Sensorwechsel hinweg (1min seit Migration 0004) |
| `prognose_lauf`, `prognose_wert` (Hypertable) | Preis-, PV-, Verbrauchs- und Auswertungsläufe |
| `v_prognose_aktuell`, `v_prognose_vortag`, `v_preis`, `v_prognose_vs_ist`, `v_prognose_guete_tag` | Prognosen, Endpreis, Prognose gegen Ist, Prognosegüte je Berliner Tag |
| `v_hems_vertrag` | erfüllte Vertragsversion |

Spalten, Pflichtangaben und Rechte stehen verbindlich im
[Vertrag mit SkytechHEMS](../contract/contract_hems_data_insight/contract_hems_data_insight.md); diese Datei wiederholt sie nicht.
Sensoren mit `quelle = 'hems'` (`hems.<name>`) holt der Collector nicht aus HA; ihre Minutenwerte
rechnet er nach, sobald das HEMS Werte schreibt.

## Konfiguration und Protokoll (Schema `skytech_config`)

| Tabelle | Inhalt |
|---|---|
| `einstellung` | Schlüssel/Wert (JSON) mit Beschreibung, z. B. Aufbewahrung |
| `migration` | angewendete Migrationen: Nummer, Name, Quelle (`system`/`anlage`), Prüfsumme |
| `aenderungsprotokoll` | Änderungen über Oberfläche, MCP, System und SkytechHEMS (`ui`, `mcp`, `system`, `hems`): Zeit, Quelle, Benutzer, Aktion, Details |
| `nachlade_luecke` | Zeiträume ohne Aufzeichnung (Neustart von Data Insight oder HA), die der Collector aus dem HA-Verlauf nachlädt: `von` (rückt mit dem Fortschritt vor), `bis`, `erledigt_am`, `versuche`, `letzter_fehler` (Migration 0005) |

## Migrationen

- System-Migrationen: `app/sql/NNNN_name.sql` (im Image).
- Anlagen-Migrationen: `/data/migrations/NNNN_name.sql` (liegen im Backup). Nummern ab `1000`
  verwenden, damit sie nicht mit künftigen System-Migrationen kollidieren.
- Jede Datei läuft einmal, in einer Transaktion, als `skytech_app`. Eine nach dem Anwenden
  geänderte Datei stoppt den Start der Aufzeichnung mit Meldung auf der Übersicht.

## Rollen

| Rolle | Anmeldung | Rechte |
|---|---|---|
| `skytech_app` | Socket (`peer`, root) | Besitzer aller Objekte, Migrationen, Oberfläche |
| `skytech_collector` | Socket (`peer`, root) | liest `sensor`, schreibt `messwert` und `messwert_1min` |
| `skytech_admin` | LAN, Passwort `db_password`; Socket für den MCP-Server | Mitglied von `skytech_app`: alles lesen, schreiben, Schema ändern |
| `skytech_reader` | LAN, Passwort `db_readonly_password` | lesen in `skytech` und `skytech_config` |
| `skytech_grafana` | nur 127.0.0.1, erzeugtes Passwort | Mitglied von `skytech_reader`; Grafana-Datenquelle (D-022) |
| `skytech_hems` | nur Add-on-Netz `172.30.33.0/24`, Passwort `hems_password` | nur `EXECUTE` auf die `hems_*`-Funktionen und `SELECT` auf die Vertragsobjekte (D-027) |

Nur Datenbank `skytech`; ohne gesetztes Passwort ist die LAN-Anmeldung gesperrt. Was
`skytech_admin` neu anlegt, darf `skytech_reader` automatisch lesen. Zugang aus VSCode:
[datenbankzugang.md](datenbankzugang.md).

## Geplante EVMS-Anbindung

Der [Vertragsentwurf](../contract/contract_evms_data_insight/contract_evms_data_insight.md)
definiert die geplante Langzeitablage von Fahrzeugen, Zuordnungen, Ladevorgängen und
zeitlichen Energieabschnitten. EVMS übernimmt die Fachlogik. Noch keine neue Rolle,
Migration, Schreibfunktion oder Auswertung implementiert. Ladeziel-/Sitzungsmodell,
Auswertungsumfang und Wiederanlauf/Puffer sind vor Umsetzung zu entscheiden.
Data Insight wird keine Voraussetzung für die laufende HEMS-Leistungsregelung.
