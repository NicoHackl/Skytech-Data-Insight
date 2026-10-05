from suggestions import suggest, suggest_quantity


def test_power_sensor():
    result = suggest("sensor.pv_leistung", {"friendly_name": "PV Leistung", "device_class": "power",
                                            "unit_of_measurement": "W", "state_class": "measurement"})
    assert result["name"] == "PV Leistung"
    assert result["groesse"] == "leistung"
    assert result["einheit"] == "W"
    assert result["energie_zaehler"] is False
    assert result["kategorie"] == "sonstiges"


def test_energy_counter():
    result = suggest("sensor.pv_energie", {"device_class": "energy", "unit_of_measurement": "kWh",
                                           "state_class": "total_increasing"})
    assert result["groesse"] == "energie"
    assert result["energie_zaehler"] is True
    assert result["name"] == "sensor.pv_energie"


def test_quantity_fallbacks():
    assert suggest_quantity("switch", {}) == "zustand"
    assert suggest_quantity("binary_sensor", {"device_class": "running"}) == "zustand"
    assert suggest_quantity("sensor", {"unit_of_measurement": "kW"}) == "leistung"
    assert suggest_quantity("sensor", {"device_class": "battery", "unit_of_measurement": "%"}) == "ladezustand"
    assert suggest_quantity("sensor", {"unit_of_measurement": "€/kWh"}) == "preis"
    assert suggest_quantity("sensor", {"unit_of_measurement": "ct/kWh"}) == "preis"
    assert suggest_quantity("sensor", {"unit_of_measurement": "l/min"}) == "sonstiges"


def test_attribute_suggestion():
    result = suggest("climate.wp", {"friendly_name": "Wärmepumpe"}, "current_temperature")
    assert result["attribut"] == "current_temperature"
    assert result["name"] == "Wärmepumpe – current_temperature"
    assert result["energie_zaehler"] is False
