# D-025: Passwörter und MCP-Token werden in der Oberfläche neu erzeugt und ohne Neustart wirksam

- **Datum:** 06.10.2026
- **Status:** Aktiv
- **Betrifft:** `config.yaml` (`hassio_role`), `app/access_service.py`, `app/supervisor_client.py`,
  `rootfs/usr/share/skytech/set_password.sql`, `rootfs/etc/s6-overlay/s6-rc.d/mcp/run`, Seite „Zugänge“

## Kontext

M3 sieht eine Seite „Zugänge“ vor. Der User hat entschieden (06.10.2026), dass dort Passwörter
und das MCP-Token nicht nur angezeigt, sondern auch geändert werden. Die Werte sind
Add-on-Optionen (`db_password`, `db_readonly_password`, `grafana_admin_password`, `mcp_token`)
und werden bisher nur beim Start angewendet. Der Supervisor schreibt `/data/options.json` erst
beim nächsten Start des Add-ons neu. Das Schreiben der eigenen Optionen erlaubt er erst ab der
Rolle `manager`.

## Betrachtete Optionen

### Option A — Optionen schreiben und das ganze Add-on neu starten

- Dafür: wenig eigener Code, gleicher Weg wie beim Speichern auf der Konfigurationsseite.
- Dagegen: jede Rotation unterbricht Aufzeichnung, Grafana und MCP für etwa 20 s.

### Option B — Secrets in einer eigenen Datei unter `/data` statt in den Optionen

- Dafür: keine Supervisor-Rolle nötig.
- Dagegen: zwei Wahrheiten. Die Konfigurationsseite zeigt dann einen anderen Wert als den
  wirksamen.

### Option C — Optionen schreiben, Änderung gezielt live anwenden

- Dafür: eine Wahrheit (Optionen), kein Neustart des Add-ons, Aufzeichnung läuft weiter.
- Dagegen: Rolle `manager`. Für jeden Zugang ein eigener Anwendeweg.

## Entscheidung

**Option C.** Ein neues Secret erzeugt der Server (`secrets.token_urlsafe(24)`). Er speichert
es in den vollständigen Optionen, nachdem der Supervisor sie geprüft hat, und wendet es dann an:

- **Datenbank:** `psql` als `postgres` mit `set_password.sql`; Rolle und Passwort gehen über die
  Umgebung.
- **Grafana:** `grafana cli admin reset-admin-password` über die Standardeingabe.
- **MCP:** nur der Dienst `mcp` startet neu und liest das Token über die Supervisor-API
  (`bashio::config`), weil `/data/options.json` noch den alten Wert hat.

Das Secret steht genau einmal in der HTTP-Antwort (`Cache-Control: no-store`). Es erscheint nie
in einer Kommandozeile, einem Log oder dem Protokoll.

Scheitert das Anwenden, nachdem die Optionen schon gespeichert sind, zeigt die Oberfläche das
Secret trotzdem und warnt dauerhaft, dass es erst nach einem Neustart des Add-ons gilt.
Andernfalls wäre der Zugang nach dem nächsten Start verloren.

## Folgen

- **Positiv:** Rotation in Sekunden, ohne Unterbrechung der Aufzeichnung. Konfigurationsseite und
  Oberfläche zeigen denselben Stand.
- **Negativ:**
  - Das Add-on bekommt die Supervisor-Rolle `manager`. Damit darf es mehr, als es heute braucht,
    etwa andere Add-ons verwalten. Genutzt werden nur `/addons/self/*` und `/network/info`.
  - Die Ausgabe von `psql` und `grafana cli` wird verworfen, weil sie das Passwort wiederholen
    könnte. Fehler sind dadurch schwerer zu diagnostizieren.
- **Aufwand:** Supervisor-Client (aus Skytech HEMS übernommen), SQL-Datei, Anpassung von
  `mcp/run`, Tests mit nachgebautem Supervisor.

## Rücknahmebedingung

- Verweigert der Supervisor die Rolle für Add-ons aus Drittquellen oder warnt Home Assistant
  sichtbar davor, gilt Option A ohne Rolle: Optionen nur anzeigen und auf die
  Konfigurationsseite verweisen.
- Bleibt ein Secret nach „Neu erzeugen“ trotz Erfolgsmeldung unwirksam (Anmeldung schlägt fehl),
  fällt die Lösung auf Option A zurück.
