# D-006: Grafana unter einem Sub-Pfad des Ingress, getrennt nach Ingress- und LAN-Eingang

- **Datum:** 27.09.2026
- **Status:** Aktiv
- **Betrifft:** `rootfs/usr/share/skytech/templates/nginx.conf`, `…/grafana.ini`,
  `rootfs/etc/s6-overlay/s6-rc.d/init-env`, `init-grafana`, `init-nginx`

## Kontext

Grafana soll (1) im HA-Seitenmenü ohne zweite Anmeldung erreichbar sein, (2) im LAN mit eigener
Anmeldung, und (3) im selben Ingress wie die Verwaltungsoberfläche liegen. Ein Add-on hat genau
**einen** Ingress-Port. Der Supervisor liefert Anfragen unter `/api/hassio_ingress/<token>/…`
aus und entfernt dieses Präfix, bevor er sie an das Add-on weitergibt. Grafana erzeugt alle
Verweise aus seiner `root_url` und muss das Präfix deshalb kennen.

## Betrachtete Optionen

### Option A — Antworten von Grafana mit `sub_filter` umschreiben

- Dafür: Grafana liefe unter `/`, LAN-Adressen blieben kurz.
- Dagegen: Grafana baut Pfade auch in JavaScript zusammen; Umschreiben von Antworten ist
  fehleranfällig und bricht bei Updates still.

### Option B — Grafana unter dem vollen Ingress-Pfad, nginx ergänzt das Präfix

- Dafür: Grafana weiß selbst, wo es liegt (`root_url` + `serve_from_sub_path`); nichts wird
  umgeschrieben. Das Vorgehen der verbreiteten Community-Add-ons.
- Dagegen: Die LAN-Adresse enthält ebenfalls das Präfix; `root_url` hängt am `ingress_entry`, der
  bei jedem Start vom Supervisor gelesen wird.

## Entscheidung

**Option B.**

| Eingang | Weg | Anmeldung |
|---|---|---|
| Ingress `8099` `/` | → Verwaltungsdienst `127.0.0.1:8100` | HA-Login (Ingress) |
| Ingress `8099` `/grafana/` | → Grafana `127.0.0.1:3001<ingress_entry>/grafana/` | `auth.proxy`: nginx setzt `X-WEBAUTH-USER` aus `X-Remote-User-Name` des Supervisors, sonst `homeassistant` |
| LAN `3000` `/` | Weiterleitung auf `<ingress_entry>/grafana/` | – |
| LAN `3000` `<ingress_entry>/grafana/` | → Grafana, Header `X-WEBAUTH-USER` wird **geleert** | Grafana-Login (`admin` + `grafana_admin_password`) |

Absicherung: Der Ingress-Server nimmt nur Verbindungen von `172.30.32.2` (Supervisor) an; Grafana
akzeptiert den Anmeldeheader nur von `127.0.0.1` (nginx). `allow_embedding = true`, weil HA das
Panel in einem iframe zeigt. Proxy-Benutzer bekommen die Organisationsrolle `Admin`: das Panel
sehen nur HA-Administratoren.

## Folgen

- **Positiv:** Im HA-Menü sofort angemeldet, im LAN eigener Login, keine Antwort wird umgeschrieben.
- **Negativ:** LAN-Adressen tragen das Ingress-Präfix (die Wurzel `http://<ha>:3000/` leitet dorthin
  weiter). Ändert sich der `ingress_entry` (Neuinstallation des Add-ons), ändern sich
  LAN-Lesezeichen.
- **Aufwand:** Zwei Vorlagen und drei Init-Skripte; Rauchtest in der CI.

## Rücknahmebedingung

Grafana-Updates brechen den Sub-Pfad-Betrieb, oder der Supervisor liefert den `ingress_entry`
nicht mehr stabil – dann Option A oder ein eigener Port ohne Ingress prüfen.
