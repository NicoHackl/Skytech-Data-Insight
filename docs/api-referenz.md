# API-Referenz

Der Verwaltungsdienst hört auf `127.0.0.1:8100` und ist nur über nginx erreichbar (Ingress).
Aus der Oberfläche werden alle Pfade **relativ** aufgerufen (D-008). Fehler kommen als
`{"error": "…"}`, Eingabefehler (`422`) zusätzlich mit `field_errors`
(`{"feld": "Meldung"}`, beim Anlegen mehrerer Sensoren `{"<index>.<feld>": "Meldung"}`).
`503` heißt: Datenbank bzw. Home Assistant noch nicht bereit.

Schreibende Aufrufe landen mit dem HA-Benutzer (Header `X-Remote-User-Display-Name` bzw.
`X-Remote-User-Name` des Supervisors) in `skytech_config.aenderungsprotokoll`.

## `GET api/status`

Zustand der Dienste und der Aufzeichnung. Antwortet immer mit `200`.

```json
{
  "version": "0.2.0",
  "services": [
    {"key": "database", "label": "Datenbank", "is_ok": true, "detail": "PostgreSQL 17.11 · TimescaleDB 2.30.1"},
    {"key": "grafana", "label": "Grafana", "is_ok": true, "detail": "Version 13.2.2"},
    {"key": "collector", "label": "Aufzeichnung", "is_ok": true, "detail": "8 Sensoren · 107 Werte/min"}
  ],
  "aufzeichnung": {
    "sensoren_aktiv": 8, "werte_letzte_minute": 107, "puffer": 0, "verworfen": 0,
    "letzte_schreibung": "27.09.2026 14:27:22", "minutenwerte_bis": "27.09.2026 14:27:00"
  },
  "datenbank_bytes": 10409651,
  "checked_at": "27.09.2026 14:27:23",
  "checked_at_iso": "2026-09-27T12:27:23.635826+00:00"
}
```

`aufzeichnung` ist `null`, solange der Collector startet. `collector.is_ok` ist `false`, wenn
Migrationen scheitern, keine HA-Verbindung besteht oder Schreiben fehlschlägt – `detail` nennt den
Grund.

## `GET api/catalog`

Auswahllisten: `kategorien` und `groessen` (`[{schluessel, bezeichnung}]`), vorhandene `anlagen`
und `paare` (Strings).

## `GET api/sensors`

`{"sensors": [...]}` – alle Sensoren mit allen Spalten aus `skytech.sensor` sowie `letzte_zeit`
(ISO), `letzte_zeit_text` (Berliner Zeit), `letzter_wert`, `letzter_text`.

## `POST api/sensors`

Legt einen oder mehrere Sensoren an – ganz oder gar nicht.

```json
{"sensors": [{"entity_id": "sensor.pv_leistung", "attribut": null, "name": "PV Leistung",
              "kategorie": "pv", "groesse": "leistung", "einheit": "W", "anlage": "Dach",
              "rolle": null, "soll_ist_paar": null, "energie_zaehler": false, "aktiv": true}]}
```

Antwort `201` `{"ids": [1]}`. Pflicht: `entity_id`, `name`, `kategorie`, `groesse`.

## `PUT api/sensors/{id}`

Ändert die übergebenen Felder (`name`, `kategorie`, `groesse`, `rolle`, `soll_ist_paar`,
`einheit`, `anlage`, `energie_zaehler`, `aktiv`). Entität und Attribut sind unveränderlich.

## `DELETE api/sensors/{id}`

Löscht den Sensor **samt allen Messwerten**. Zum bloßen Pausieren `aktiv: false` setzen.

## `GET api/ha/entities`

Alle HA-Entitäten aus dem Zustandsabbild des Collectors, je Entität mit `name`, `domain`,
`state`, `einheit`, `device_class`, `state_class`, `erfasst` (Zustand bereits aufgezeichnet),
`vorschlag` (vorbefüllter Sensor) und `attribute` (nur Attribute mit Zahlenwert, je mit `erfasst`
und `vorschlag`). `503` ohne HA-Verbindung.

## Speicher und Aufbewahrung (M3)

| Aufruf | Wirkung |
|---|---|
| `GET api/storage` | `{datenbank_bytes, tabellen: [{name, bytes, chunks, komprimiert}], rohwerte_je_tag: [{tag, rohwerte, heute}], rohwerte_tag_mittel, rohwerte_bytes_jahr}` – `tabellen` in fester Reihenfolge Roh-, Minutenwerte, Verdichtungen; `tag` als `TT.MM.JJJJ` (Berliner Tag, die letzten 7 Tage plus heute); die Hochrechnung pro Jahr ist unkomprimiert |
| `GET api/retention` | `{rohwerte_tage, minutenwerte_tage}` – Tage, `null` = nie löschen |
| `PUT api/retention` | Body mit **beiden** Schlüsseln (fehlt einer: `400`). Rohwerte ≥ 1, Minutenwerte ≥ 31 Tage oder `null`; sonst `422` mit `field_errors`. Legt vorher eine Sicherung `vor_aenderung_*.dump` an, wendet die Aufbewahrung sofort an und protokolliert `aufbewahrung_geaendert`. Antwort mit `sicherung` |

Dieselbe Logik nutzt das MCP-Werkzeug `aufbewahrung_setzen` (`app/settings_service.py`).

## `GET api/log` (M3)

Änderungsprotokoll, neueste zuerst. Parameter: `quelle` (`ui`, `mcp`, `system`; leer = alle),
`vor` (id – nur ältere Einträge), `limit` (1–200, Standard 50). Antwort
`{"eintraege": [{id, zeit, zeit_text, quelle, benutzer, aktion, details}], "weitere": bool}`;
`zeit_text` in Berliner Zeit. `400` bei unbekannter Quelle oder nicht numerischen Parametern.

## Migrationen (M3, nur lesend)

| Aufruf | Wirkung |
|---|---|
| `GET api/migrations` | `{"migrationen": [{version, name, quelle, status, angewendet_am}], "fehler"}` – Dateien (System und `/data/migrations`) mit `skytech_config.migration` abgeglichen. `status`: `angewendet`, `ausstehend`, `geaendert` (Datei nach dem Anwenden verändert – Start der Aufzeichnung scheitert), `datei_fehlt` (angewendet, Datei nicht mehr da). `angewendet_am` in Berliner Zeit. `fehler`: Startfehler, der eine Migration betrifft |
| `GET api/migrations/{version}` | `{version, datei, sql}`; `404`, wenn die Datei fehlt |

## Sicherungen (M2)

| Aufruf | Wirkung |
|---|---|
| `GET api/backups` | `{sicherungen: [{datei, art, art_text, groesse_bytes, erstellt, erstellt_iso}], wiederherstellung, laeuft}` – `wiederherstellung` ist der Zustand der letzten Wiederherstellung (`laeuft`, `erfolgreich`, `fehlgeschlagen`, `unklar`) |
| `POST api/backups` | Sicherung sofort anlegen (`manuell_*.dump`), `201` |
| `GET api/backups/download` | Komplettpaket `.tar` (Dump, Grafana, `sicherung.json`) |
| `GET api/backups/{datei}` | einzelne Sicherung herunterladen |
| `DELETE api/backups/{datei}` | Sicherung löschen |
| `PUT api/backups/upload?name=<original>` | Datei als Rohdaten im Body; wird geprüft und als `upload_*` abgelegt. `201` mit Beschreibung, `422` bei ungültiger Datei |
| `POST api/backups/{datei}/restore` | Body `{"bestaetigung": "WIEDERHERSTELLEN"}`; startet die Wiederherstellung im Hintergrund (`202`). Der Dienst startet danach neu – Ergebnis über `GET api/backups` |

Dateinamen werden nur akzeptiert, wenn sie dem Muster `<art>_<JJJJMMTT>_<hhmmss>[_n].(dump|tar)`
entsprechen – Pfade sind ausgeschlossen.

## Statische Auslieferung

| Pfad | Inhalt |
|---|---|
| `/`, `/index.html` | `app/static/index.html` (`Cache-Control: no-cache`); fehlt sie, `503` |
| `/assets/…` | gebautes Bundle |

## Grafana

`<ingress>/grafana/` wird von nginx an Grafana weitergereicht (D-006); die Grafana-HTTP-API liegt
unter `<ingress_entry>/grafana/api/…`.
