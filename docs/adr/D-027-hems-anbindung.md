# D-027: SkytechHEMS schreibt über eine eigene Rolle und verwaltet seine Sensoren selbst

- **Datum:** 12.10.2026
- **Status:** Aktiv (Data-Insight-Seite umgesetzt am 12.10.2026, SkytechHEMS-Seite am 13.10.2026)
- **Betrifft:** künftig `app/sql/` (Migration), `rootfs/usr/share/skytech/` (Rolle, `pg_hba`),
  `config.yaml` (Option `hems_password`), `app/access_service.py` (Zugang `hems`),
  `app/sensor_service.py`, `app/mcp_tools.py`, Seiten „Sensoren“ und „Zugänge“; Schnittstelle:
  [Vertrag mit SkytechHEMS](../../contract/contract_hems_data_insight/contract_hems_data_insight.md)

## Kontext

Der Umsetzungsplan sah für M7 zwei Wege vor: Weg A (HEMS veröffentlicht einen Attribut-Sensor) und
Weg B (HEMS schreibt mit eigener Rolle `skytech_hems`). Für den dynamischen Strompreis (SkytechHEMS
D-065) braucht das HEMS mehr als Messwerte: Prognosekurven mit zwei Zeitachsen (erstellt / gültig
für), die Historie der Grundlast und eine verlässliche Zuordnung, welcher Sensor welche fachliche
Rolle hat, auch nach einem Wechsel von Home Assistant. Der User hat am 12.10.2026 festgelegt, dass
das HEMS die benötigten Sensoren hier selbst anlegt oder vorhandene übernimmt, und dass sie danach
nur noch über das HEMS verwaltet werden.

## Betrachtete Optionen

### Option A — Attribut-Sensor in Home Assistant (Weg A)

- Dafür: kein neuer Zugang zur Datenbank.
- Dagegen: Prognosekurven passen nicht in `messwert`; jede Kurve stünde zusätzlich im
  HA-Recorder. Sensoren und Rollen müssten von Hand gepflegt werden.

### Option B — Eigene Rolle mit eng begrenzten Rechten (Weg B, gewählt)

- Dafür: Prognose- und Preisläufe in eigenen Tabellen; das HEMS legt Sensoren selbst an und kann
  sie austauschen; Rechte, Row-Level-Security und ein Sperr-Trigger begrenzen, was es darf.
- Dagegen: neue Anmelderolle, neuer Zugang, mehr Schema.

## Entscheidung

Option B, ausgestaltet im
[Vertrag mit SkytechHEMS](../../contract/contract_hems_data_insight/contract_hems_data_insight.md)
(Version 0.2). Kernpunkte:

- Rolle `skytech_hems`, nur aus dem Add-on-Bereich `172.30.33.0/24`, Secret über die Seite
  „Zugänge“ (Schlüssel `hems`, Option `hems_password`).
- **Schreiben nur über Funktionen** (Vertrag 0.2, mit dem User am 12.10.2026 entschieden): Das HEMS
  schreibt den Mittelwert eines Slots erst nach dessen Ende, datiert auf den Slot-Beginn; die
  Minutenwerte sind dann schon gerechnet. Die Funktion meldet neue Werte per `NOTIFY`, der
  Collector rechnet nach. Nebenbei prüfen die Funktionen jede Eingabe und schreiben das Protokoll;
  die Rolle braucht keine Tabellenrechte.
- Spalte `sensor.verwaltet_von`. Vom HEMS angelegte oder übernommene Sensoren sind per Trigger
  gegen Änderungen anderer Rollen gesperrt und in Oberfläche, API (`409`) und MCP gekennzeichnet.
- `hems_zuordnung` (Rolle → Sensor mit Gültigkeitsbeginn) und Sichten je Rolle, damit ein
  Sensortausch die Historie nicht unterbricht.
- `prognose_lauf` und `prognose_wert` samt Sichten für Prognose gegen Ist und Prognosegüte.
- Data Insight rechnet keine Prognosen.

## Folgen

- **Positiv:** Prognosen, Preise und Ist-Werte liegen an einer Stelle; Grafana und MCP sehen sie
  ohne Umweg.
- **Negativ:** Ein Teil der Sensorliste ist hier nicht mehr frei bearbeitbar. Das ist gewollt, weil
  das HEMS sonst mit Sensoren rechnet, die jemand anders geändert hat.
- **Aufwand:** Migration, Rolle und `pg_hba`, Zugang `hems`, Sperre in Oberfläche, API und MCP,
  Tests gegen den TimescaleDB-Testcontainer.
- **Nachtrag 13.10.2026 (Vertrag 0.3, Migration 0004):** HEMS-Reihen werden nicht mehr
  fortgeführt – ein einmal geschriebener Grundlast-Wert lief sonst als Konstante weiter, und das
  HEMS hielt die Reihe für aktuell. Das HEMS schreibt seither je Minute; dazu kamen die Sicht
  `v_hems_rolle_1min` und das Zählerkennzeichen für Rollen wie Netzbezug oder PV-Ertrag.

## Rücknahmebedingung

Stellt sich heraus, dass die Sperre im Alltag stört, etwa weil verwaltete Sensoren regelmäßig
von Hand korrigiert werden müssen, wird die Verwaltung gelockert. Das geschieht über eine neue
Vertragsversion, nicht durch Umgehen des Triggers.
