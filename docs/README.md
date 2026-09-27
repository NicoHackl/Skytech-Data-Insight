# Dokumentation — Skytech Data Insight

Ausführliche technische Referenz. Die **verbindlichen Regeln** stehen nicht hier, sondern in
[`AGENTS.md`](../AGENTS.md) im Repo-Root. Bei Widerspruch gilt `AGENTS.md`.

Diese Doku beschreibt den **tatsächlichen Stand des Codes**. Das Zielbild steht im
[Umsetzungsplan](umsetzungsplan.md), der Stand je Meilenstein in [roadmap.md](roadmap.md),
Abweichungen in [bekannte-luecken.md](bekannte-luecken.md).

## Schnellstart für neue Agenten und Entwickler

1. [`AGENTS.md`](../AGENTS.md) lesen — eiserne Regeln und Befehle.
2. [architektur.md](architektur.md) — Dienste im Container und wie sie zusammenhängen.
3. [git-workflow.md](git-workflow.md) — **bevor** irgendetwas committet wird.
4. [roadmap.md](roadmap.md) und [bekannte-luecken.md](bekannte-luecken.md) — was es schon gibt.

## Inhaltsverzeichnis

| Datei | Inhalt |
|---|---|
| [umsetzungsplan.md](umsetzungsplan.md) | Freigegebener Gesamtplan: Entscheidungen, Zielarchitektur, Meilensteine M0–M7 |
| [architektur.md](architektur.md) | Dienste, Ports, Startreihenfolge, Verzeichnisse, Tech-Stack |
| [entwicklerrichtlinien.md](entwicklerrichtlinien.md) | Naming, Projektstruktur, Fehlerbehandlung, Kommentarstil |
| [frontend.md](frontend.md) | Frontend-Stack, Struktur, Routing unter Ingress, API-Client |
| [design-system.md](design-system.md) | Designsprachen, Tokens, Klassenkatalog, Icons, Barrierefreiheit |
| [git-workflow.md](git-workflow.md) | Branch-Modell, Commit-Format, Versionierung, Release |
| [test-strategie.md](test-strategie.md) | Testarten, lokaler Containertest, CI |
| [design-entscheidungen.md](design-entscheidungen.md) | Entscheidungs-Log — Quelle der Wahrheit fürs „warum" |
| [adr/](adr/) | Ausführliche Entscheidungsdokumente |
| [konfiguration.md](konfiguration.md) | Add-on-Optionen, Ports, Umgebungsvariablen, Secrets |
| [datenmodell.md](datenmodell.md) | Tabellen, Sichten, Minutenwerte, Verdichtungen, Aufbewahrung, Migrationen, Rollen |
| [datenbankzugang.md](datenbankzugang.md) | Zugang aus VSCode und anderen SQL-Werkzeugen |
| [api-referenz.md](api-referenz.md) | HTTP-Endpunkte des Verwaltungsdienstes |
| [mcp.md](mcp.md) | MCP-Server für LLMs: Einrichtung, Werkzeuge, Schutz |
| [backup-restore.md](backup-restore.md) | HA-Backup, Download, Einspielen, lokale Sicherungen |
| [sicherheit-datenschutz.md](sicherheit-datenschutz.md) | Zugänge, Anmeldung, externe Dienste |
| [bekannte-luecken.md](bekannte-luecken.md) | Offene Punkte, Stolpersteine |
| [roadmap.md](roadmap.md) | Meilensteine und Umsetzungsstand |

## Pflegeregeln dieser Doku

- **Jede Information genau einmal.** Steht etwas in `AGENTS.md`, wird es hier verlinkt, nicht kopiert.
- Nicht zutreffende Dateien werden **gelöscht**, nicht mit Platzhaltertext stehengelassen.
- Änderungen an Verhalten und Doku gehören ins **selbe** Arbeitspaket.
