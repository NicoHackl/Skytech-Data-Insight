import pytest

from sensor_service import ValidationError, normalize


def valid(**overrides):
    data = {"entity_id": "sensor.pv_leistung", "name": " PV ", "kategorie": "pv", "groesse": "leistung"}
    data.update(overrides)
    return data


def test_normalize_trims_and_keeps_known_fields():
    result = normalize(valid(unbekannt="x", einheit=" W "), creating=True)
    assert result["name"] == "PV"
    assert result["einheit"] == "W"
    assert "unbekannt" not in result
    assert result["attribut"] is None


@pytest.mark.parametrize("overrides, field", [
    ({"entity_id": "PV Leistung"}, "entity_id"),
    ({"name": "  "}, "name"),
    ({"kategorie": ""}, "kategorie"),
    ({"rolle": "vielleicht"}, "rolle"),
    ({"soll_ist_paar": "Heizstab"}, "rolle"),
    ({"aktiv": "ja"}, "aktiv"),
    ({"name": "x" * 121}, "name"),
])
def test_normalize_rejects(overrides, field):
    with pytest.raises(ValidationError) as info:
        normalize(valid(**overrides), creating=True)
    assert field in info.value.field_errors


def test_update_only_checks_given_fields():
    assert normalize({"aktiv": False}, creating=False) == {"aktiv": False}
    with pytest.raises(ValidationError):
        normalize({"name": ""}, creating=False)
