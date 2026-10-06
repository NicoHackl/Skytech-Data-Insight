# D-026: Port 3000 optional per https mit dem HA-Zertifikat

- **Datum:** 06.10.2026
- **Status:** Aktiv
- **Betrifft:** `config.yaml` (`map: ssl`, Optionen `grafana_tls*`), `init-nginx/init.sh`,
  `templates/nginx.conf`

## Kontext

HA läuft beim User über https mit eigener Domain. Die Karte „Website“ bettet Grafana von
`http://<ha>:3000` ein; der Browser blockt das als Mixed Content.

## Betrachtete Optionen

### Option A — TLS auf Port 3000 mit dem HA-Zertifikat (gewählt)

- Dafür: kleine Änderung, Grafana bleibt unverändert, funktioniert im LAN mit der Zertifikatsdomain.
- Dagegen: Adresse muss die Domain tragen (nicht die IP); Zertifikatserneuerung wirkt erst nach
  Neustart des Add-ons.

### Option B — Selbstsigniertes Zertifikat

- Dagegen: Browser lehnen es im iframe ab, solange es nicht installiert ist.

### Option C — Einbettung über den Ingress-Pfad

- Dagegen: Ingress-Sitzung hängt am HA-Login; als Karteninhalt nicht stabil.

## Entscheidung

Option A. Standardmäßig aus; fehlende Dateien lassen den Start nicht scheitern, sondern fallen
auf http zurück (Warnung im Protokoll).
