# Projektübergreifende Verträge

Die Verträge folgen der gemeinsamen Struktur der Skytech-Projekte:

```text
contract/
├── README.md
└── contract_<projektpaar>/
    ├── <vertragsdatei>.md
    └── <zugehoerige-plaene>.md  # falls vorhanden
```

Jedes Projektpaar besitzt einen eigenen Ordner. Der gemeinsame Vertrag liegt unter
demselben relativen Pfad und wortgleich in beiden beteiligten Repositories. Änderungen
an der Schnittstelle werden im selben Arbeitspaket in beiden Kopien nachgezogen.

Der Status im Vertrag unterscheidet implementierten Austausch, bekannte Grenzen
und Entwürfe. Ein Plan oder eine Dokumentationsänderung allein implementiert keine
Schnittstelle. Lokale Dokumentation verlinkt den Vertrag, statt eine abweichende
Beschreibung der gemeinsamen Felder zu führen.

## Grundsatz: eine Schnittstellen-Entität je Einheit

Seit 20.10.2026 (Entscheidung des Users) gilt für den Austausch über Home Assistant: Jede Einheit,
die anderen Teilnehmern etwas mitteilt, veröffentlicht dafür genau **eine** Entität
`sensor.<einheit>_schnittstelle` mit allen Informationen für alle anderen Teilnehmer. Werte stehen
als Attribute, je Gerät mit dessen Präfix vorne; der State nennt die Präfixe, durch Komma getrennt.
Sollwerte des HEMS laufen weiter über seine `input_*`-Ausgabehelfer.

| Einheit | Schnittstellen-Entität | Inhalt | Leser |
|---|---|---|---|
| SkytechHEMS | `sensor.hems_schnittstelle` | Lebenszeichen, Istwerte der Speicher | Battery-Provider, Wallbox-Provider |
| Battery-Provider | `sensor.battery_provider_schnittstelle` | Lade-/Entladefreigabe und Sperrgrund je Speicher | SkytechHEMS |
| Wallbox-Provider | `sensor.wallbox_provider_schnittstelle` | Freigabe und Sperrgrund je Wallbox | SkytechHEMS |
| Energy Pilot | `sensor.energy_pilot_schnittstelle` | Vorschläge je Gerät mit Gültigkeitsfenster | SkytechHEMS |

Dokumentierte Ausnahmen:

- **Powerflow-Card:** `sensor.skytech_hems_flow_config` und `sensor.skytech_hems_flow_status`
  bleiben getrennt. Sie sind Anzeigedaten für eine Karte, und die große Konfiguration soll nur bei
  Änderung geschrieben werden. Die Karte selbst veröffentlicht nichts.
- **Anzeige-Entitäten** für Nutzer und Dashboards bleiben einzeln, z. B.
  `sensor.ems_<prefix>_lade_limit_w`, `sensor.ems_notabschaltung_aktiv`, `sensor.ems_dyn_*`,
  `sensor.ep_plan_status`, `sensor.ep_hems_verbindung` und die EP-Zusatz-Vorschläge
  `sensor.ep_<obj>_vorschlag`.
- **HEMS → Energy Pilot** bleibt REST (`/api/device_controls_schema`, `/api/status`): groß und nur
  bei Bedarf gelesen.
- **Data Insight** tauscht über die Datenbank aus (Funktionen und Sichten), nicht über
  HA-Entitäten; der Grundsatz betrifft diesen Weg nicht.

| Gegenstelle | Vertrag | Stand / Hinweise |
|---|---|---|
| SkytechHEMS | [contract_hems_data_insight.md](contract_hems_data_insight/contract_hems_data_insight.md) | Version 0.3: Rolle `skytech_hems`, Schreiben über geprüfte Funktionen, vom HEMS verwaltete Sensoren, Rollen-Zuordnung, Prognose- und Preisläufe (D-027). In beiden Projekten implementiert (HEMS-Phasen P4 und P5). |

Die übrigen HTTP-/MCP- und Datenbankschnittstellen sind kein bilateraler Vertrag und bleiben in
[API-Referenz](../docs/api-referenz.md) und [Datenmodell](../docs/datenmodell.md) beschrieben.
