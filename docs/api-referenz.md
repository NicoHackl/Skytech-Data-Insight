# API-Referenz

Der Verwaltungsdienst hört auf `127.0.0.1:8100` und ist nur über nginx erreichbar (Ingress).
Aus der Oberfläche werden alle Pfade **relativ** aufgerufen (D-008).

## `GET api/status`

Zustand der Dienste. Antwortet immer mit `200`, auch wenn ein Dienst gestört ist; `503` nur,
solange der Dienst selbst startet.

```json
{
  "version": "0.1.0",
  "services": [
    {"key": "database", "label": "Datenbank", "is_ok": true, "detail": "PostgreSQL 17.11 · TimescaleDB 2.30.1"},
    {"key": "grafana", "label": "Grafana", "is_ok": true, "detail": "Version 13.2.2"}
  ],
  "checked_at": "27.09.2026 13:27:00",
  "checked_at_iso": "2026-09-27T11:27:00.998121+00:00"
}
```

| Feld | Bedeutung |
|---|---|
| `services[].key` | `database` \| `grafana`, Reihenfolge fest |
| `services[].is_ok` | Datenbank: Verbindung und TimescaleDB vorhanden. Grafana: `/api/health` meldet `database: ok` |
| `checked_at` | für Menschen, Berliner Zeit ohne Offset |
| `checked_at_iso` | Maschinenformat, UTC |

Jede Prüfung hat ein Timeout von 3 s.

## Statische Auslieferung

| Pfad | Inhalt |
|---|---|
| `/`, `/index.html` | `app/static/index.html`; fehlt sie, `503` mit Hinweis auf den Build |
| `/assets/…` | gebautes Bundle |

## Grafana

`<ingress>/grafana/` ist kein Endpunkt des Verwaltungsdienstes, sondern wird von nginx an Grafana
weitergereicht (D-006). Die Grafana-HTTP-API liegt entsprechend unter
`<ingress_entry>/grafana/api/…`.
