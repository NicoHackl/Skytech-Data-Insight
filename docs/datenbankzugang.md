# Datenbankzugang (VSCode und andere SQL-Werkzeuge)

## Voraussetzungen

1. In der Add-on-Konfiguration `db_password` (Vollzugriff) und/oder `db_readonly_password`
   (nur lesen) setzen, Add-on neu starten.
2. Port `5432` ist im Abschnitt „Netzwerk" der Add-on-Seite freigegeben (Voreinstellung).

## Verbindungsdaten

| Feld | Wert |
|---|---|
| Server | Adresse des Home-Assistant-Rechners im LAN |
| Port | `5432` (bzw. der im Abschnitt „Netzwerk" gewählte) |
| Datenbank | `skytech` |
| Benutzer | `skytech_admin` (Vollzugriff) oder `skytech_reader` (nur lesen) |
| SSL | aus (`sslmode=disable`) — nur im LAN nutzen |

Die Übersicht der Oberfläche zeigt dieselben Daten.

## VSCode

- **Erweiterung „PostgreSQL" (Microsoft):** Neue Verbindung → Parameter wie oben, bei
  „SSL mode" `disable` wählen.
- **SQLTools** mit Treiber „PostgreSQL": gleiche Angaben, `ssl` aus.

Verbindungszeichenkette:

```text
postgresql://skytech_reader:<passwort>@<ha-adresse>:5432/skytech?sslmode=disable
```

## Gut zu wissen

- Für Auswertungen die Sichten nutzen (`skytech.v_messwert_15min` usw.), siehe
  [datenmodell.md](datenmodell.md).
- Mit `skytech_admin` lassen sich Sensoren auch per SQL anlegen oder ändern; der Collector übernimmt
  das sofort.
- Eigene Tabellen dürfen angelegt werden. Dauerhafte Schemaänderungen besser als
  Anlagen-Migration unter `/data/migrations/` ablegen, damit sie nachvollziehbar bleiben.

> **Sicherheit:** Port 5432 nie per Portfreigabe ins Internet öffnen. Fernzugriff nur über VPN.
