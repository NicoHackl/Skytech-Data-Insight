"""Verwaltung der Sensorliste (`skytech.sensor`) für die Oberfläche.

Prüft Eingaben, übersetzt Datenbankfehler in verständliche Feldfehler und
schreibt jede Änderung ins Änderungsprotokoll. Der Collector erfährt Änderungen
über den Trigger der Tabelle (NOTIFY), nicht über diesen Dienst.
"""

import json
import re
from typing import Any

import asyncpg

_ENTITY_ID = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
_EDITABLE = ("name", "kategorie", "groesse", "rolle", "soll_ist_paar", "einheit", "anlage", "energie_zaehler", "aktiv")
_MAX_TEXT = 120

SENSOR_LIST_SQL = """
SELECT s.id, s.entity_id, s.attribut, s.name, s.kategorie, s.groesse, s.rolle, s.soll_ist_paar,
       s.einheit, s.anlage, s.energie_zaehler, s.aktiv, s.quelle, s.erstellt_am,
       l.zeit AS letzte_zeit, l.wert AS letzter_wert, l.text_wert AS letzter_text
FROM skytech.sensor s
LEFT JOIN LATERAL (
    SELECT zeit, wert, text_wert FROM skytech.messwert m
    WHERE m.sensor_id = s.id ORDER BY zeit DESC LIMIT 1
) l ON true
ORDER BY s.kategorie, s.name
"""


class ValidationError(ValueError):
    """Eingaben ungültig; `field_errors` ordnet Meldungen den Feldern zu."""

    def __init__(self, message: str, field_errors: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.field_errors = field_errors or {}


class NotFoundError(LookupError):
    pass


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize(data: dict[str, Any], *, creating: bool) -> dict[str, Any]:
    """Prüft und bereinigt einen Sensor-Datensatz. Wirft ValidationError."""
    errors: dict[str, str] = {}
    result: dict[str, Any] = {}

    if creating:
        entity_id = _clean_text(data.get("entity_id"))
        if not entity_id or not _ENTITY_ID.match(entity_id):
            errors["entity_id"] = "Entität fehlt oder hat kein gültiges Format (z. B. sensor.pv_leistung)."
        result["entity_id"] = entity_id
        result["attribut"] = _clean_text(data.get("attribut"))

    for key in _EDITABLE:
        if key not in data:
            continue
        if key in ("energie_zaehler", "aktiv"):
            if not isinstance(data[key], bool):
                errors[key] = "Ja oder Nein erwartet."
            result[key] = data[key]
            continue
        value = _clean_text(data[key])
        if value is not None and len(value) > _MAX_TEXT:
            errors[key] = f"Höchstens {_MAX_TEXT} Zeichen."
        result[key] = value

    if creating or "name" in result:
        if not result.get("name"):
            errors["name"] = "Name fehlt."
    for key in ("kategorie", "groesse"):
        if (creating or key in result) and not result.get(key):
            errors[key] = "Bitte auswählen."
    if "rolle" in result and result["rolle"] not in (None, "ist", "soll"):
        errors["rolle"] = "Nur „Ist“, „Soll“ oder leer."
    if result.get("soll_ist_paar") and not result.get("rolle"):
        errors["rolle"] = "Für ein Soll/Ist-Paar muss die Rolle gesetzt sein."

    if errors:
        raise ValidationError("Eingaben prüfen.", errors)
    return result


def _translate(exc: asyncpg.PostgresError) -> ValidationError:
    """Übersetzt Verletzungen von Schlüsseln und Prüfungen in Feldfehler."""
    constraint = getattr(exc, "constraint_name", None) or ""
    if isinstance(exc, asyncpg.UniqueViolationError):
        if constraint == "sensor_paar_eindeutig":
            return ValidationError("Soll/Ist-Paar belegt.", {"soll_ist_paar": "Dieses Paar hat bereits einen Sensor mit dieser Rolle."})
        return ValidationError("Bereits erfasst.", {"entity_id": "Diese Entität bzw. dieses Attribut wird bereits aufgezeichnet."})
    if isinstance(exc, asyncpg.ForeignKeyViolationError):
        field = "groesse" if "groesse" in constraint else "kategorie"
        return ValidationError("Unbekannter Katalogwert.", {field: "Unbekannter Wert – bitte aus der Liste wählen."})
    if isinstance(exc, asyncpg.CheckViolationError):
        return ValidationError(f"Eingabe verletzt die Regel „{constraint}“.")
    return ValidationError(f"Datenbank lehnt die Änderung ab: {exc}")


async def log_change(connection: asyncpg.Connection, user: str | None, action: str, details: dict[str, Any],
                     source: str = "ui") -> None:
    """Schreibt einen Eintrag ins Änderungsprotokoll (Quelle `ui`, `mcp` oder `system`)."""
    await connection.execute(
        "INSERT INTO skytech_config.aenderungsprotokoll (quelle, benutzer, aktion, details) VALUES ($1, $2, $3, $4::jsonb)",
        source, user, action, json.dumps(details, ensure_ascii=False, default=str),
    )


async def list_sensors(connection: asyncpg.Connection) -> list[dict[str, Any]]:
    return [dict(row) for row in await connection.fetch(SENSOR_LIST_SQL)]


async def catalog(connection: asyncpg.Connection) -> dict[str, Any]:
    kategorien = await connection.fetch("SELECT schluessel, bezeichnung FROM skytech.kategorie ORDER BY reihenfolge, bezeichnung")
    groessen = await connection.fetch("SELECT schluessel, bezeichnung FROM skytech.groesse ORDER BY reihenfolge, bezeichnung")
    anlagen = await connection.fetch("SELECT DISTINCT anlage FROM skytech.sensor WHERE anlage IS NOT NULL ORDER BY 1")
    paare = await connection.fetch("SELECT DISTINCT soll_ist_paar FROM skytech.sensor WHERE soll_ist_paar IS NOT NULL ORDER BY 1")
    return {
        "kategorien": [dict(row) for row in kategorien],
        "groessen": [dict(row) for row in groessen],
        "anlagen": [row["anlage"] for row in anlagen],
        "paare": [row["soll_ist_paar"] for row in paare],
    }


async def create_sensors(connection: asyncpg.Connection, items: list[dict[str, Any]], user: str | None,
                         source: str = "ui") -> list[int]:
    """Legt mehrere Sensoren in einer Transaktion an – ganz oder gar nicht."""
    if not items:
        raise ValidationError("Keine Sensoren übergeben.")
    normalized = []
    for index, item in enumerate(items):
        try:
            normalized.append(normalize(item, creating=True))
        except ValidationError as exc:
            raise ValidationError(f"Sensor {index + 1}: {exc}", {f"{index}.{k}": v for k, v in exc.field_errors.items()}) from exc
    ids = []
    try:
        async with connection.transaction():
            for index, sensor in enumerate(normalized):
                columns = [key for key in sensor]
                placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
                try:
                    sensor_id = await connection.fetchval(
                        f"INSERT INTO skytech.sensor ({', '.join(columns)}) VALUES ({placeholders}) RETURNING id",
                        *sensor.values(),
                    )
                except asyncpg.PostgresError as exc:
                    error = _translate(exc)
                    raise ValidationError(
                        f"{sensor['entity_id']}: {error}",
                        {f"{index}.{k}": v for k, v in error.field_errors.items()},
                    ) from exc
                ids.append(sensor_id)
            await log_change(connection, user, "sensoren_angelegt", {"ids": ids, "sensoren": normalized}, source)
    except ValidationError:
        raise
    return ids


async def update_sensor(connection: asyncpg.Connection, sensor_id: int, data: dict[str, Any], user: str | None,
                        source: str = "ui") -> None:
    changes = normalize(data, creating=False)
    if not changes:
        raise ValidationError("Keine Änderung übergeben.")
    assignments = ", ".join(f"{key} = ${i + 2}" for i, key in enumerate(changes))
    async with connection.transaction():
        try:
            result = await connection.execute(
                f"UPDATE skytech.sensor SET {assignments} WHERE id = $1", sensor_id, *changes.values()
            )
        except asyncpg.PostgresError as exc:
            raise _translate(exc) from exc
        if result == "UPDATE 0":
            raise NotFoundError(sensor_id)
        await log_change(connection, user, "sensor_geaendert", {"id": sensor_id, "aenderungen": changes}, source)


async def delete_sensor(connection: asyncpg.Connection, sensor_id: int, user: str | None) -> None:
    """Löscht den Sensor samt allen Messwerten."""
    async with connection.transaction():
        row = await connection.fetchrow("DELETE FROM skytech.sensor WHERE id = $1 RETURNING entity_id, attribut, name", sensor_id)
        if row is None:
            raise NotFoundError(sensor_id)
        await log_change(connection, user, "sensor_geloescht", {"id": sensor_id, **dict(row)})
