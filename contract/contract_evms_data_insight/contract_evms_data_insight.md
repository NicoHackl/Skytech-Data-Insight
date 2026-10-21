# Vertrag: Skytech EVMS ↔ Skytech Data Insight

**Version: 0.1 — 21.10.2026. Status: Entwurf auf beiden Seiten.**

Kein Schema, keine DB-Rolle und keine Schreibfunktion dieses Vertrags sind bereits
implementiert. Beide Kopien liegen wortgleich am selben relativen Pfad.

## Zuständigkeiten

EVMS besitzt Fahrzeugverwaltung, RFID-Zuordnung, Sitzungsbildung und fachliche
Bewertung. Data Insight übernimmt dauerhafte Ablage und Abfragemöglichkeiten.
Datenbankzugriffe liegen außerhalb der HEMS-/Wallbox-Regelkette.

## Geplanter Zugriff

Analog zur HEMS-Anbindung: eigene Rolle `skytech_evms`, Zugang nur im internen
Add-on-Netz, eigene Zugangsdaten, versionierte Vertragsansicht, Schreiben über
geprüfte Datenbankfunktionen und Lesen über freigegebene Sichten. Kein Admin-Zugang,
keine direkten Tabellenänderungen, keine durch EVMS ausgeführten Schemaänderungen.
Migrationen und Rechte werden im Data-Insight-Repository implementiert und getestet.
Konkrete SQL-Signaturen folgen erst nach Festlegung des Datenmodells.

## Fachliche Daten

- Fahrzeuge mit stabiler ID, Anzeigename und zeitlich nachvollziehbaren Änderungen.
- Physische Ladepunkte, Ladeziele und Fahrzeug-/RFID-Zuordnungen mit Gültigkeit.
- Ladevorgänge mit Fahrzeug- und Anschlussbezug, Anfang/Ende, Status und Datenqualität.
- Zeitlich begrenzte Energieabschnitte mit Messquelle und Kennzeichnung gemessen/geschätzt.
- Nachvollziehbare Korrekturen und Versionierung abgeschlossener Vorgänge.

Kein unbekanntes Fahrzeug im Erstumfang. Identitäten und zeitliche Zuordnung dürfen
nicht durch Umbenennen oder Archivieren eines Fahrzeugs verloren gehen.
Wiederholung gleicher Übertragungen ist idempotent; bestätigte Revisionen schützen
vor verspäteten älteren Updates. Vorgang und zugehörige Abschnitte müssen konsistent sein.

## Zeit und Energie

Maschinenzeitpunkte als eindeutig zonierte Zeitpunkte speichern. Monats-/Jahresauswertung
nach `Europe/Berlin`, einschließlich Zeitumstellung. Grenzüberschreitende Sitzungen
anhand zeitlicher Energieabschnitte aufteilen; keine gesamte Sitzung dem Startmonat zuweisen.
Wallboxzähler sind Ladeenergie am Messpunkt, nicht Batterieenergie.
PV-/Netz-/Speicheranteile und Kosten bleiben offen bis zur vereinbarten Berechnungsregel.

Zählerrücksprünge, Reset und Messlücken müssen ausdrücklich behandelt werden. Die bestehende
generische Data-Insight-Zählerverdichtung allein beweist keine korrekte EV-Sitzung.
Keine fehlende Fahrzeugzuordnung, Energie oder Quellenaufteilung erfinden.

## Ausfall, Aufbewahrung und Sicherung

Vorgesehen ist ein dauerhafter EVMS-Puffer mit bestätigter Übertragung und Wiederholung.
Größe, Überlaufverhalten und dauerhafter Konfigurationsbesitz sind noch abzustimmen.
Ein Data-Insight-Ausfall darf nicht in veraltete positive Ladefreigaben münden.
Backups müssen Fahrzeug-/Zuordnungsdaten und Sitzungen gemeinsam wiederherstellen.
Aufbewahrung so festlegen, dass Jahresauswertungen nach Rohwertlöschung nachvollziehbar bleiben.

## Noch zu entscheiden und zu testen

Ladezielmodell, Sitzungsgrenzen, Felder der Fahrzeugkonfiguration, Auswertungsumfang,
Puffergrenzen, Korrekturrechte, Aufbewahrung und konkrete Funktionssignaturen.
Tests: DB-Rechte, Versionsabweichung, Wiederholung, veraltete Revision, Teilfehler,
Ausfall/Wiederanlauf, Zeitumstellung, Monats-/Jahresgrenze und Wiederherstellung.
