# D-026: Grafana per relativem Ingress-Pfad in HA-Karten einbetten

- **Datum:** 07.10.2026
- **Status:** Aktiv
- **Betrifft:** Doku (`docs/konfiguration.md`), Hinweis auf der Übersichtsseite; kein Code im Add-on

## Kontext

HA läuft beim User über https (Reverse Proxy mit eigenem Zertifikat). Die Karte „Webseite“ mit
`http://<ip>:3000` wird als Mixed Content geblockt.

## Betrachtete Optionen

### Option A — Relativer Ingress-Pfad `/api/hassio_ingress/<token>/grafana/…` (gewählt)

- Dafür: derselbe https-Origin wie HA, funktioniert lokal und extern, automatische Anmeldung per
  HA-Benutzer, keine Änderung am Add-on.
- Dagegen: braucht das Ingress-Sitzungs-Cookie (entsteht beim Öffnen eines Ingress-Panels).

### Option B — TLS auf Port 3000 mit dem Zertifikat aus `/ssl` (umgesetzt, wieder entfernt)

- Dagegen: Bei Reverse-Proxy-Setups liegt das Zertifikat nicht in `/ssl`; Port 3000 ist über die
  Domain nicht erreichbar. Zusätzlicher Code ohne Nutzen für diesen Fall.

### Option C — Eigener Proxy-Host mit https auf dem Reverse Proxy

- Dagegen: macht Grafana ggf. öffentlich erreichbar, Aufwand außerhalb des Add-ons.

## Entscheidung

Option A, dokumentiert. Option B wurde wieder zurückgenommen.
