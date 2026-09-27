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

## Statische Auslieferung

| Pfad | Inhalt |
|---|---|
| `/`, `/index.html` | `app/static/index.html` (`Cache-Control: no-cache`); fehlt sie, `503` |
| `/assets/…` | gebautes Bundle |

## Grafana

`<ingress>/grafana/` wird von nginx an Grafana weitergereicht (D-006); die Grafana-HTTP-API liegt
unter `<ingress_entry>/grafana/api/…`.
