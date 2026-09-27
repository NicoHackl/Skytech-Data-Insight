# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Die Add-on-Version in `config.yaml` wird bei jedem Merge nach `main` automatisch
um eine Patch-Stelle erhöht (siehe `.github/workflows/bump-version.yaml`).

## [Unreleased]

### Geändert

- **Abhängigkeiten aktualisiert** (ersetzt die Dependabot-PRs #1–#10): React 19, React Router 7,
  Vite 8, TypeScript 7, `@vitejs/plugin-react` 6, aiohttp 3.14.3, asyncpg 0.31.0; CI-Actions
  `checkout`, `setup-python`, `setup-node` auf v7, Node 22 im Frontend-Job (Vite 8 braucht
  mindestens 20.19). Oberfläche unverändert.

### Hinzugefügt

- **Meilenstein M0 – Gerüst.** Neues Add-on „Skytech Data Insight" (nur `amd64`): ein Container
  mit PostgreSQL 17.11 + TimescaleDB 2.30.1, Grafana 13.2.2, nginx und einem Verwaltungsdienst
  unter s6-overlay (D-004, D-005). Der Datenbank-Cluster entsteht beim ersten Start unter
  `/data/pgdata`; Datenbank `skytech` mit TimescaleDB wird bei jedem Start sichergestellt.
- **Verwaltungsoberfläche im HA-Seitenmenü** (Designsprache Home Assistant, Hell/Dunkel) mit der
  Seite „Übersicht": Zustand von Datenbank und Grafana samt Versionen, Weg zu Grafana.
- **Grafana im selben Ingress** unter „Grafana", automatisch mit dem HA-Benutzer angemeldet;
  zusätzlich im LAN unter Port 3000 mit eigenem Login `admin` (D-006). Ohne gesetztes
  `grafana_admin_password` ist die LAN-Anmeldung gesperrt (D-011). Grafana startet auf Deutsch
  mit Berliner Zeit und deutschen Datumsformaten; Telemetrie und Update-Abfragen sind aus.
- **Regelwerk und Doku** nach dem Muster von Skytech HEMS (`AGENTS.md`, `docs/`, Entscheidungs-Log
  D-001 bis D-014, ADR D-006) sowie der freigegebene Umsetzungsplan unter
  `docs/umsetzungsplan.md`.
- **CI:** Lint (Ruff, ShellCheck), Tests, Frontend-Build mit Drift-Prüfung und ein Rauchtest, der
  das Image baut, startet und Dienste, Ingress-Weg und LAN-Anmeldung prüft.
