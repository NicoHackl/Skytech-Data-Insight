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

Für Skytech Data Insight ist in diesem Arbeitspaket kein eigener bilateraler
Vertrag vereinbart. Das Verzeichnis legt die gemeinsame Ablagestruktur fest. Die
vorhandenen HTTP-/MCP- und Datenbankschnittstellen bleiben in
[API-Referenz](../docs/api-referenz.md) und [Datenmodell](../docs/datenmodell.md) beschrieben.
