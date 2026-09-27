"""Umsetzung von HA-Zuständen und -Attributen in Datenbankwerte.

Ein Messwert hat zwei Spalten: `wert` (Zahl) und `text_wert` (Originaltext,
wenn der Wert keine reine Zahl ist). on/off wird zusätzlich als 1/0 abgelegt,
damit Schaltzustände in Grafana als Kurve und als Zeitanteil nutzbar sind.
"""

import json
import math
from dataclasses import dataclass
from typing import Any

# Zustände, die Home Assistant für „kein Wert" meldet.
MISSING_STATES = frozenset({"unknown", "unavailable", "none", ""})
BOOLEAN_STATES = {"on": 1.0, "off": 0.0, "true": 1.0, "false": 0.0}


@dataclass(frozen=True)
class StoredValue:
    """Ein Wert so, wie er in `skytech.messwert` landet."""

    number: float | None
    text: str | None


def convert(raw: Any) -> StoredValue:
    """Setzt einen Zustand oder Attributwert in Zahl und Text um."""
    if raw is None:
        return StoredValue(None, None)
    if isinstance(raw, bool):
        return StoredValue(1.0 if raw else 0.0, "true" if raw else "false")
    if isinstance(raw, (int, float)):
        number = float(raw)
        return StoredValue(number, None) if math.isfinite(number) else StoredValue(None, str(raw))
    if isinstance(raw, (list, dict)):
        return StoredValue(None, json.dumps(raw, ensure_ascii=False, sort_keys=True))

    text = str(raw).strip()
    lowered = text.lower()
    if lowered in MISSING_STATES:
        return StoredValue(None, text or None)
    if lowered in BOOLEAN_STATES:
        return StoredValue(BOOLEAN_STATES[lowered], text)
    try:
        number = float(text)
    except ValueError:
        return StoredValue(None, text)
    # „nan" und „inf" sind für float() gültig, als Messwert aber unbrauchbar.
    return StoredValue(number, None) if math.isfinite(number) else StoredValue(None, text)


def is_numeric_attribute(raw: Any) -> bool:
    """Taugt ein Attributwert als eigene Messreihe? Ja, wenn er eine Zahl ergibt."""
    return convert(raw).number is not None
