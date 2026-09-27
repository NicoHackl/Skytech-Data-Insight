"""Vorschläge für neue Sensoren aus den Metadaten einer HA-Entität.

Die Oberfläche füllt damit das Formular vor; der Benutzer entscheidet.
Die Kategorie (PV, Heizung …) lässt sich aus HA nicht ableiten und bleibt
deshalb ein Vorschlag „sonstiges".
"""

from typing import Any

# HA-device_class → skytech.groesse
_DEVICE_CLASS_TO_QUANTITY = {
    "power": "leistung",
    "apparent_power": "leistung",
    "reactive_power": "leistung",
    "energy": "energie",
    "energy_storage": "energie",
    "battery": "ladezustand",
    "temperature": "temperatur",
    "voltage": "spannung",
    "current": "strom",
}
# Einheit als Rückfall, wenn keine device_class gesetzt ist.
_UNIT_TO_QUANTITY = {
    "W": "leistung", "kW": "leistung", "MW": "leistung",
    "Wh": "energie", "kWh": "energie", "MWh": "energie",
    "°C": "temperatur", "K": "temperatur",
    "V": "spannung", "A": "strom",
}
_STATE_DOMAINS = frozenset({"binary_sensor", "switch", "input_boolean", "light", "fan", "climate"})
_COUNTER_STATE_CLASSES = frozenset({"total", "total_increasing"})


def suggest_quantity(domain: str, attributes: dict[str, Any]) -> str:
    """Schlägt die Größe vor (`skytech.groesse`)."""
    device_class = attributes.get("device_class")
    if device_class in _DEVICE_CLASS_TO_QUANTITY:
        return _DEVICE_CLASS_TO_QUANTITY[device_class]
    if domain in _STATE_DOMAINS:
        return "zustand"
    return _UNIT_TO_QUANTITY.get(attributes.get("unit_of_measurement"), "sonstiges")


def is_counter(attributes: dict[str, Any]) -> bool:
    """Zählerstand (Energie über die Zeit)? Dann tragen Minutenwerte den Zuwachs."""
    return attributes.get("state_class") in _COUNTER_STATE_CLASSES


def suggest(entity_id: str, attributes: dict[str, Any], attribute: str | None = None) -> dict[str, Any]:
    """Vorschlag für einen neuen Sensor aus Entität und optionalem Attribut."""
    domain = entity_id.split(".", 1)[0]
    friendly_name = str(attributes.get("friendly_name") or entity_id)
    if attribute is not None:
        return {
            "entity_id": entity_id,
            "attribut": attribute,
            "name": f"{friendly_name} – {attribute}",
            "kategorie": "sonstiges",
            "groesse": "sonstiges",
            "einheit": None,
            "energie_zaehler": False,
        }
    return {
        "entity_id": entity_id,
        "attribut": None,
        "name": friendly_name,
        "kategorie": "sonstiges",
        "groesse": suggest_quantity(domain, attributes),
        "einheit": attributes.get("unit_of_measurement"),
        "energie_zaehler": is_counter(attributes),
    }
