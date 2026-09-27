# Test-Strategie

## Testarten

| Art | Werkzeug | Umfang |
|---|---|---|
| Unit-Tests Python | `pytest -q` | Anzeigezeit, Dienstprüfungen (auch gegen echten HTTP-Server), Status-API |
| Paketierung | `pytest` (`tests/test_packaging.py`) | Manifest, Übersetzungen, s6-Dienste und Abhängigkeiten, jeder Vorlagen-Platzhalter wird gesetzt, Ingress-Sperre und LAN-Header-Entfernung |
| Lint | `ruff check app tests`, ShellCheck (CI) | Python und Init-/Dienstskripte |
| Frontend | `cd web && npm run build` | Typprüfung und Bundle; CI prüft Drift des eingecheckten Bundles |
| Container-Rauchtest | CI-Job `image` | Image bauen, starten, alle Dienste gesund, Grafana über Ingress-Port, LAN-Login und Abwehr gefälschter Header |

## Lokaler Containertest (amd64)

Auf einem Mac mit Apple-Chip läuft der amd64-Container über Rosetta in Colima:

```bash
colima start --profile amd64 --vm-type vz --vz-rosetta --cpu 4 --memory 6
docker build --platform linux/amd64 --build-arg BUILD_VERSION=lokal -t skytech-data-insight .
docker volume create sdi-data
docker run --rm --platform linux/amd64 -v sdi-data:/data --entrypoint sh skytech-data-insight \
  -c 'echo "{\"log_level\":\"info\",\"grafana_admin_password\":\"lokal-test\"}" > /data/options.json'
docker run -d --name sdi --platform linux/amd64 -v sdi-data:/data -p 18099:8099 -p 13000:3000 skytech-data-insight
```

| Prüfung | Aufruf | Erwartung |
|---|---|---|
| Status | `curl http://127.0.0.1:18099/api/status` | beide Dienste `is_ok: true` |
| Grafana wie über Ingress | `curl -H "X-Remote-User-Name: test" http://127.0.0.1:18099/grafana/api/user` | Benutzer `test` |
| Grafana im LAN | Browser `http://127.0.0.1:13000/` | Weiterleitung, Grafana-Login |

Für einen Browsertest der Oberfläche unter dem vollen Ingress-Pfad genügt ein kleiner Proxy, der
`/api/hassio_ingress/lokaltest` entfernt und auf Port 18099 weiterreicht – so arbeitet der
Supervisor.

## Pflicht vor jedem Commit

`ruff check app tests` und `pytest -q` fehlerfrei; bei Änderungen an `web/` Build und Bundle
mitcommitten; bei Änderungen an `rootfs/` oder `Dockerfile` den lokalen Containertest.
