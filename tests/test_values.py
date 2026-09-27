import pytest

from values import StoredValue, convert, is_numeric_attribute


@pytest.mark.parametrize("raw, expected", [
    ("1234.5", StoredValue(1234.5, None)),
    ("-3", StoredValue(-3.0, None)),
    (" 7 ", StoredValue(7.0, None)),
    (42, StoredValue(42.0, None)),
    ("on", StoredValue(1.0, "on")),
    ("off", StoredValue(0.0, "off")),
    (True, StoredValue(1.0, "true")),
    ("unavailable", StoredValue(None, "unavailable")),
    ("unknown", StoredValue(None, "unknown")),
    ("", StoredValue(None, None)),
    (None, StoredValue(None, None)),
    ("heat", StoredValue(None, "heat")),
    ("nan", StoredValue(None, "nan")),
    (float("inf"), StoredValue(None, "inf")),
    ([1, 2], StoredValue(None, "[1, 2]")),
])
def test_convert(raw, expected):
    assert convert(raw) == expected


def test_numeric_attributes():
    assert is_numeric_attribute(21.5)
    assert is_numeric_attribute("3")
    assert is_numeric_attribute(False)
    assert not is_numeric_attribute("Automatik")
    assert not is_numeric_attribute({"a": 1})
