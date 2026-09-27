# Entwicklerrichtlinien

> Sprachregeln (Code englisch, Text deutsch) und Secrets-Verbot stehen in
> [`AGENTS.md`](../AGENTS.md) und werden hier **nicht** wiederholt. Hier steht nur, was darüber
> hinausgeht.

## Naming

| Element | Konvention | Beispiel |
|---|---|---|
| Variablen, Funktionen | `snake_case` in Python, `camelCase` in TypeScript | `calculate_total_power`, `fetchControls` |
| Klassen, Typen, React-Komponenten | PascalCase | `ControllableDevice`, `DeviceCard` |
| Konstanten | UPPER_SNAKE_CASE | `HARD_LOCKOUT_THRESHOLD_W` |
| Dateien / Module | `snake_case.py`, `PascalCase.tsx` für Komponenten, `kleinbuchstaben.ts` sonst | `ha_client.py`, `Layout.tsx`, `api.ts` |
| Booleans | Frage-Präfix `is_` / `has_` / `can_` | `is_enabled`, `has_permission` |

Abkürzungen nur, wenn sie in der Domäne etabliert sind. `cfg` statt `config` ist keine Ersparnis,
die den Verlust an Lesbarkeit rechtfertigt.

**Ausnahme mit Begründung:** Tabellen-, Spalten- und View-Namen der Datenbank sind deutsch
(`messwert`, `zeit`, `v_soll_ist`, siehe [datenmodell.md](datenmodell.md)). Sie sind der
Datenvertrag, den Anwender in SQL, Grafana und per MCP direkt benutzen (eiserne Regel 2).
Python-, TypeScript- und Shell-Code hält sich an die Tabelle oben.

## Projektstruktur

```text
Skytech-Data-Insight/
├── config.yaml, build.yaml, Dockerfile   # Add-on-Manifest und Image
├── rootfs/                               # wird ins Image-Wurzelverzeichnis kopiert
│   ├── etc/s6-overlay/s6-rc.d/           #   Dienste (init-*, postgres, grafana, app, nginx)
│   ├── usr/lib/skytech/                  #   Shell-Helfer (lib.sh, finish.sh)
│   └── usr/share/skytech/                #   Vorlagen und bootstrap.sql
├── app/                                  # Verwaltungsdienst (Python)
│   ├── main.py                           #   HTTP-Routen
│   ├── health.py                         #   Dienstprüfungen
│   └── static/                           #   gebautes SPA-Bundle (eingecheckt, D-007)
├── grafana/provisioning/                 # Grafana-Provisioning (ab M4)
├── web/                                  # Quellen der Oberfläche (React + TypeScript + Vite)
├── tests/                                # pytest, flach je Modul bzw. Aspekt
└── docs/                                 # diese Doku
```

Regel: Eine Datei hat **eine** Verantwortlichkeit. Wächst eine Datei über ~400 Zeilen, ist das ein
Hinweis auf eine fehlende Trennung — kein Automatismus, aber ein Prüfanlass.

Shell-Skripte unter `rootfs/` binden `lib.sh` ein, lesen Optionen nur über `skytech::option` und
schreiben Konfiguration nur über `skytech::render` aus einer Vorlage (D-013). Meldungen laufen über
`bashio::log.*` und sind deutsch.

## Kommentare

- Kommentare erklären das **Warum**, nicht das Was. `i = i + 1  # i um eins erhöhen` ist wertlos.
- Öffentliche Funktionen bekommen einen Docstring: Zweck, Parameter, Rückgabe, geworfene Fehler.
- Auskommentierter Code wird **gelöscht**, nicht aufbewahrt. Dafür gibt es Git.
- `TODO`-Kommentare bekommen einen Verweis: `# TODO(D-007): …` oder eine Issue-Nummer. Ein
  namenloses `TODO` verschwindet und wird nie erledigt.

## Fehlerbehandlung

- Fehler werden **nicht stillschweigend verschluckt**. Kein leerer `catch`/`except`-Block.
- Fehlermeldungen für den User: deutsch, konkret, mit Handlungsanweisung.
  Schlecht: „Fehler aufgetreten". Gut: „Konfigurationsdatei `config.yaml` nicht gefunden — erwartet
  im Repo-Root."
- Technische Details gehören ins Log, nicht in die UI.
- Externe Aufrufe (Netzwerk, Dateisystem, fremde APIs) bekommen ein explizites Timeout und
  definiertes Verhalten im Fehlerfall.

## Logging

| Level | Wofür |
|---|---|
| `DEBUG` | Entwicklungsdetails, im Normalbetrieb aus |
| `INFO` | Normale Zustandsübergänge, Start/Stop, abgeschlossene Vorgänge |
| `WARNING` | Unerwartet, aber automatisch behandelt |
| `ERROR` | Vorgang fehlgeschlagen, Eingriff nötig |

Nie geloggt werden: Passwörter, Tokens, API-Keys, personenbezogene Daten. Siehe
[sicherheit-datenschutz.md](sicherheit-datenschutz.md).

## Abhängigkeiten

- Neue Abhängigkeit nur, wenn sie mehr Aufwand spart, als sie an Wartung kostet. Eine
  10-Zeilen-Hilfsfunktion rechtfertigt kein zusätzliches Paket.
- Versionen werden gepinnt (`app/requirements.txt` und `web/package-lock.json`).
- Eine neue Laufzeit-Abhängigkeit ist eine Design-Entscheidung → Eintrag in
  [design-entscheidungen.md](design-entscheidungen.md).

## Formatierung

Formatierung erledigt das Tooling, nicht die Diskussion: `ruff check app tests`, für Shell ShellCheck. Manuelles Abweichen vom
Formatter ist kein zulässiger Diff-Inhalt — er verrauscht Reviews.
